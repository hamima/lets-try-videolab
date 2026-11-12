#!/usr/bin/env python3
"""
scripts/migrate_workspaces_to_users.py — one-time migration from the old
workspace/<domain>/<run_id>/ layout to the new workspace/<user>/<domain>/<run_id>/
layout (see docs/authentication.md).

This is a standalone, one-off tool — it is not imported or called by
tasks.py / automate.py, and ships no permanent migration logic in the app.

Usage:
    python scripts/migrate_workspaces_to_users.py                 # dry run (default)
    python scripts/migrate_workspaces_to_users.py --apply          # actually move files
    python scripts/migrate_workspaces_to_users.py --apply --owner someone.else

By default, every existing workspace/<domain>/<run_id>/ folder is attributed
to "hamidreza.maghbooli" (the one real user as of this migration). Pass
--owner to attribute them to a different user-id instead.
"""

import argparse
import re
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
WORKSPACE_ROOT = BASE_DIR / "workspace"
RUN_ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{6}")

DEFAULT_OWNER = "hamidreza.maghbooli"


def find_old_layout_runs() -> list[tuple[str, str, Path]]:
    """Return (domain, run_id, path) for every workspace/<domain>/<run_id>/
    folder still in the old (pre-user) layout — i.e. a domain folder
    containing timestamp-named run folders directly."""
    found = []
    if not WORKSPACE_ROOT.exists():
        return found

    for domain_dir in sorted(WORKSPACE_ROOT.iterdir()):
        if not domain_dir.is_dir():
            continue
        for run_dir in sorted(domain_dir.iterdir()):
            if run_dir.is_dir() and RUN_ID_RE.match(run_dir.name):
                found.append((domain_dir.name, run_dir.name, run_dir))

    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually move the folders (default: dry run, prints only).")
    parser.add_argument("--owner", default=DEFAULT_OWNER, help=f"user-id to attribute existing runs to (default: {DEFAULT_OWNER}).")
    args = parser.parse_args()

    runs = find_old_layout_runs()
    if not runs:
        print("No old-layout workspace/<domain>/<run_id>/ folders found — nothing to migrate.")
        return

    print(f"Found {len(runs)} run(s) in the old layout. {'Moving' if args.apply else 'Would move'} to workspace/{args.owner}/<domain>/<run_id>/:\n")

    for domain, run_id, src in runs:
        dest = WORKSPACE_ROOT / args.owner / domain / run_id
        print(f"  workspace/{domain}/{run_id}/  ->  workspace/{args.owner}/{domain}/{run_id}/")
        if args.apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                raise SystemExit(f"Refusing to overwrite existing destination: {dest}")
            shutil.move(str(src), str(dest))

    if not args.apply:
        print("\nDry run only — nothing was moved. Re-run with --apply to perform the move.")
    else:
        print(f"\nMigrated {len(runs)} run(s) to workspace/{args.owner}/.")
        # Clean up now-empty old domain folders.
        for domain_dir in sorted(WORKSPACE_ROOT.iterdir()):
            if domain_dir.is_dir() and domain_dir.name != args.owner and not any(domain_dir.iterdir()):
                domain_dir.rmdir()


if __name__ == "__main__":
    main()
