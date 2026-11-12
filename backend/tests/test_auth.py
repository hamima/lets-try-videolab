"""
backend/tests/test_auth.py — Regression tests for session/admin helpers in
auth.py: the admins.conf parser, the email -> user-id derivation, and the
admin `owner` query-param override used by every run-scoped endpoint.
"""

import auth


# ─────────────────────────────────────────────────────────────
# user_id_from_email
# ─────────────────────────────────────────────────────────────

def test_user_id_is_local_part_as_is():
    assert auth.user_id_from_email("hamidreza.maghbooli@gmail.com") == "hamidreza.maghbooli"


def test_user_id_handles_no_normalization():
    # No lowercasing/stripping beyond splitting on '@' — matches the plan's
    # "local-part as-is" decision.
    assert auth.user_id_from_email("Hamid.B@gmail.com") == "Hamid.B"


# ─────────────────────────────────────────────────────────────
# admins.conf parsing / is_admin
# ─────────────────────────────────────────────────────────────

def test_is_admin_matches_listed_email(tmp_path, monkeypatch):
    admins_file = tmp_path / "admins.conf"
    admins_file.write_text("hamidreza.maghbooli@gmail.com\n")
    monkeypatch.setattr(auth, "ADMINS_FILE", admins_file)

    assert auth.is_admin("hamidreza.maghbooli@gmail.com") is True
    assert auth.is_admin("someone.else@gmail.com") is False


def test_is_admin_ignores_comments_and_blank_lines(tmp_path, monkeypatch):
    admins_file = tmp_path / "admins.conf"
    admins_file.write_text(
        "# admins\n"
        "\n"
        "   \n"
        "admin.one@gmail.com  # trailing comment\n"
        "admin.two@gmail.com\n"
    )
    monkeypatch.setattr(auth, "ADMINS_FILE", admins_file)

    assert auth.is_admin("admin.one@gmail.com") is True
    assert auth.is_admin("admin.two@gmail.com") is True
    assert auth.is_admin("nobody@gmail.com") is False


def test_is_admin_case_insensitive(tmp_path, monkeypatch):
    admins_file = tmp_path / "admins.conf"
    admins_file.write_text("Admin@gmail.com\n")
    monkeypatch.setattr(auth, "ADMINS_FILE", admins_file)

    assert auth.is_admin("admin@gmail.com") is True


def test_is_admin_false_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "ADMINS_FILE", tmp_path / "does_not_exist.conf")
    assert auth.is_admin("anyone@gmail.com") is False


# ─────────────────────────────────────────────────────────────
# resolve_owner — the admin `owner` query-param escape hatch
# ─────────────────────────────────────────────────────────────

def test_resolve_owner_defaults_to_self():
    user = auth.CurrentUser(email="a@gmail.com", user_id="a", is_admin=False)
    assert auth.resolve_owner(user, None) == "a"


def test_resolve_owner_non_admin_cannot_override():
    user = auth.CurrentUser(email="a@gmail.com", user_id="a", is_admin=False)
    # A non-admin passing someone else's id is silently ignored, never honored.
    assert auth.resolve_owner(user, "someone-else") == "a"


def test_resolve_owner_admin_can_override():
    admin = auth.CurrentUser(email="admin@gmail.com", user_id="admin", is_admin=True)
    assert auth.resolve_owner(admin, "someone-else") == "someone-else"


def test_resolve_owner_admin_without_param_defaults_to_self():
    admin = auth.CurrentUser(email="admin@gmail.com", user_id="admin", is_admin=True)
    assert auth.resolve_owner(admin, None) == "admin"


# ─────────────────────────────────────────────────────────────
# Sessions
# ─────────────────────────────────────────────────────────────

def test_create_and_destroy_session():
    session_id = auth.create_session("someone@gmail.com")
    assert auth._get_session(session_id) == {"email": "someone@gmail.com", "user_id": "someone"}

    auth.destroy_session(session_id)
    assert auth._get_session(session_id) is None
