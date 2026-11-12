#!/usr/bin/env python3
"""
scripts/migrate_workspaces_to_users.py — one-off CLI around
backend/workspace_migration.py's migrate_orphan_runs(), for migrating the
old workspace/<domain>/<run_id>/ layout to the new
workspace/<user>/<domain>/<run_id>/ layout (see docs/authentication.md).

The same migration also now runs automatically on every server start (see
tasks.py's startup hook), always attributing orphans to DEFAULT_OWNER. This
script remains useful for a dry run, or to attribute orphans to a different
owner than the default.

Usage:
    python scripts/migrate_workspaces_to_users.py                 # dry run (default)
    python scripts/migrate_workspaces_to_users.py --apply          # actually move files
    python scripts/migrate_workspaces_to_users.py --apply --owner someone.else
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
WORKSPACE_ROOT = BASE_DIR / "workspace"

sys.path.insert(0, str(BASE_DIR / "backend"))
from workspace_migration import DEFAULT_OWNER, migrate_orphan_runs  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually move the folders (default: dry run, prints only).")
    parser.add_argument("--owner", default=DEFAULT_OWNER, help=f"user-id to attribute existing runs to (default: {DEFAULT_OWNER}).")
    args = parser.parse_args()

    moved = migrate_orphan_runs(WORKSPACE_ROOT, owner=args.owner, apply=args.apply)
    if not moved:
        print("No old-layout workspace/<domain>/<run_id>/ folders found — nothing to migrate.")
        return

    print(f"Found {len(moved)} run(s) in the old layout. {'Moved' if args.apply else 'Would move'} to workspace/{args.owner}/<domain>/<run_id>/:\n")
    for domain, run_id, dest in moved:
        print(f"  workspace/{domain}/{run_id}/  ->  workspace/{args.owner}/{domain}/{run_id}/")

    if not args.apply:
        print("\nDry run only — nothing was moved. Re-run with --apply to perform the move.")
    else:
        print(f"\nMigrated {len(moved)} run(s) to workspace/{args.owner}/.")


if __name__ == "__main__":
    main()
