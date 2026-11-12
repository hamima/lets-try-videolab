"""
backend/tests/test_workspace_migration.py — regression tests for
workspace_migration.migrate_orphan_runs(), which moves pre-multi-user
workspace/<domain>/<run_id>/ folders under workspace/<owner>/<domain>/<run_id>/.
Exercised both by the standalone CLI (scripts/migrate_workspaces_to_users.py)
and tasks.py's startup hook.
"""

import workspace_migration as wm


def test_migrate_orphan_runs_dry_run_does_not_move(tmp_path):
    orphan = tmp_path / "political" / "2026-08-20_143022"
    orphan.mkdir(parents=True)
    (orphan / "research_dossier.md").write_text("TOPIC\n\nSomething")

    moved = wm.migrate_orphan_runs(tmp_path, owner="alice", apply=False)

    assert moved == [("political", "2026-08-20_143022", tmp_path / "alice" / "political" / "2026-08-20_143022")]
    assert orphan.exists()
    assert not (tmp_path / "alice").exists()


def test_migrate_orphan_runs_apply_moves_and_cleans_up(tmp_path):
    orphan = tmp_path / "political" / "2026-08-20_143022"
    orphan.mkdir(parents=True)
    (orphan / "research_dossier.md").write_text("TOPIC\n\nSomething")

    moved = wm.migrate_orphan_runs(tmp_path, owner="alice", apply=True)

    dest = tmp_path / "alice" / "political" / "2026-08-20_143022"
    assert moved == [("political", "2026-08-20_143022", dest)]
    assert dest.exists()
    assert (dest / "research_dossier.md").exists()
    assert not orphan.exists()
    # Now-empty old domain folder was cleaned up.
    assert not (tmp_path / "political").exists()


def test_migrate_orphan_runs_ignores_already_namespaced_runs(tmp_path):
    (tmp_path / "alice" / "political" / "2026-08-20_143022").mkdir(parents=True)

    moved = wm.migrate_orphan_runs(tmp_path, owner="alice", apply=True)

    assert moved == []
    assert (tmp_path / "alice" / "political" / "2026-08-20_143022").exists()


def test_migrate_orphan_runs_no_workspace_root_is_noop(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert wm.migrate_orphan_runs(missing, owner="alice", apply=True) == []


def test_migrate_orphan_runs_refuses_to_overwrite_existing_destination(tmp_path):
    (tmp_path / "political" / "2026-08-20_143022").mkdir(parents=True)
    (tmp_path / "alice" / "political" / "2026-08-20_143022").mkdir(parents=True)

    try:
        wm.migrate_orphan_runs(tmp_path, owner="alice", apply=True)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
