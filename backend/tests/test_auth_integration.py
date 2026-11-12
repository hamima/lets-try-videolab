"""
backend/tests/test_auth_integration.py — End-to-end integration tests of the
auth flow through FastAPI's actual dependency injection: sign-in sets a
session cookie, /auth/me reflects it, run listing is scoped per-user, admins
see every user's runs (with an owner field) and can reach Settings, and a
non-owner/non-admin is refused with 404 even when explicitly asking for
another user's run via the `owner` param.

Google's token verification is mocked (no real network call) — these tests
exercise everything *after* a token is already trusted as valid.
"""

from fastapi.testclient import TestClient

import auth
import settings as settings_module
import tasks


def _client(monkeypatch, tmp_path, admin_email="admin@gmail.com"):
    monkeypatch.setattr(tasks, "BASE_DIR", tmp_path)
    monkeypatch.setattr(tasks, "WORKSPACE_ROOT", tmp_path / "workspace")
    admins_file = tmp_path / "admins.conf"
    admins_file.write_text(admin_email + "\n")
    monkeypatch.setattr(auth, "ADMINS_FILE", admins_file)
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", tmp_path / "settings.json")
    auth._sessions.clear()
    return TestClient(tasks.app)


def _sign_in(client, monkeypatch, email):
    monkeypatch.setattr(
        auth, "verify_google_id_token",
        lambda credential: {"email": email, "email_verified": True},
    )
    resp = client.post("/tasks/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _seed_run(tmp_path, user: str, domain: str, run_id: str) -> None:
    ws = tmp_path / "workspace" / user / domain / run_id
    ws.mkdir(parents=True)
    (ws / "pipeline_state.json").write_text(
        '{"completed": [], "failed": [], "domain": "%s", "voice_id": null}' % domain
    )


def test_sign_in_rejects_non_gmail(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        auth, "verify_google_id_token",
        lambda credential: {"email": "someone@work.com", "email_verified": True},
    )
    resp = client.post("/tasks/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 403


def test_sign_in_rejects_unverified_email(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        auth, "verify_google_id_token",
        lambda credential: {"email": "someone@gmail.com", "email_verified": False},
    )
    resp = client.post("/tasks/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 403


def test_sign_in_sets_session_and_me_reflects_it(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    user = _sign_in(client, monkeypatch, "regular.user@gmail.com")
    assert user == {"email": "regular.user@gmail.com", "user_id": "regular.user", "is_admin": False}

    me = client.get("/tasks/auth/me")
    assert me.status_code == 200
    assert me.json()["user_id"] == "regular.user"


def test_unauthenticated_requests_are_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/tasks/runs").status_code == 401
    assert client.get("/tasks/settings").status_code == 401


def test_runs_scoped_to_own_user_for_non_admin(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _seed_run(tmp_path, "alice", "political", "2026-01-01_120000")
    _seed_run(tmp_path, "bob", "political", "2026-01-02_120000")

    _sign_in(client, monkeypatch, "alice@gmail.com")
    resp = client.get("/tasks/runs")
    assert resp.status_code == 200
    assert {r["run_id"] for r in resp.json()} == {"2026-01-01_120000"}


def test_admin_sees_every_users_runs_with_owner_field(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, admin_email="admin@gmail.com")
    _seed_run(tmp_path, "alice", "political", "2026-01-01_120000")
    _seed_run(tmp_path, "bob", "political", "2026-01-02_120000")

    _sign_in(client, monkeypatch, "admin@gmail.com")
    resp = client.get("/tasks/runs")
    assert resp.status_code == 200
    assert {r["owner"] for r in resp.json()} == {"alice", "bob"}


def test_non_admin_cannot_access_another_users_run(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _seed_run(tmp_path, "bob", "political", "2026-01-02_120000")

    _sign_in(client, monkeypatch, "alice@gmail.com")
    # Explicitly asking for bob's run via `owner` is ignored for non-admins.
    resp = client.get("/tasks/runs/political/2026-01-02_120000", params={"owner": "bob"})
    assert resp.status_code == 404


def test_admin_can_access_another_users_run_via_owner_param(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, admin_email="admin@gmail.com")
    _seed_run(tmp_path, "bob", "political", "2026-01-02_120000")

    _sign_in(client, monkeypatch, "admin@gmail.com")
    resp = client.get("/tasks/runs/political/2026-01-02_120000", params={"owner": "bob"})
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "2026-01-02_120000"


def test_settings_requires_admin(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, admin_email="admin@gmail.com")
    _sign_in(client, monkeypatch, "regular.user@gmail.com")
    assert client.get("/tasks/settings").status_code == 403


def test_settings_accessible_to_admin(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, admin_email="admin@gmail.com")
    _sign_in(client, monkeypatch, "admin@gmail.com")
    assert client.get("/tasks/settings").status_code == 200


def test_logout_invalidates_session(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _sign_in(client, monkeypatch, "regular.user@gmail.com")

    assert client.get("/tasks/auth/me").status_code == 200
    assert client.post("/tasks/auth/logout").status_code == 200
    assert client.get("/tasks/auth/me").status_code == 401
