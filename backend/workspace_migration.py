"""
backend/workspace_migration.py — moves "orphan" workspace/<domain>/<run_id>/
folders (the pre-multi-user layout, see docs/authentication.md) under a
given user's workspace/<user>/<domain>/<run_id>/ folder.

Shared by:
- scripts/migrate_workspaces_to_users.py — one-off CLI, supports a dry run
  and an arbitrary --owner.
- tasks.py's FastAPI startup hook — runs automatically every time the
  server boots, always applying, always attributing to DEFAULT_OWNER. Safe
  to call repeatedly: it's a no-op once nothing is left in the old layout.
"""

import re
import shutil
from pathlib import Path
from typing import List, Tuple

RUN_ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{6}")
DEFAULT_OWNER = "hamidreza.maghbooli"


def find_orphan_runs(workspace_root: Path) -> List[Tuple[str, str, Path]]:
    """Return (domain, run_id, path) for every workspace/<domain>/<run_id>/
    folder still in the old (pre-user) layout — i.e. a domain folder
    containing timestamp-named run folders directly, rather than nested
    under a user-id folder."""
    found = []
    if not workspace_root.exists():
        return found

    for domain_dir in sorted(workspace_root.iterdir()):
        if not domain_dir.is_dir():
            continue
        for run_dir in sorted(domain_dir.iterdir()):
            if run_dir.is_dir() and RUN_ID_RE.match(run_dir.name):
                found.append((domain_dir.name, run_dir.name, run_dir))

    return found


def migrate_orphan_runs(
    workspace_root: Path, owner: str = DEFAULT_OWNER, apply: bool = False
) -> List[Tuple[str, str, Path]]:
    """Move every orphan run under workspace/<owner>/<domain>/<run_id>/.

    Returns the (domain, run_id, dest) triples moved — or that would be
    moved, when apply=False. Raises if a destination already exists rather
    than silently overwriting it.
    """
    runs = find_orphan_runs(workspace_root)
    moved: List[Tuple[str, str, Path]] = []

    for domain, run_id, src in runs:
        dest = workspace_root / owner / domain / run_id
        moved.append((domain, run_id, dest))
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                raise RuntimeError(f"Refusing to overwrite existing destination: {dest}")
            shutil.move(str(src), str(dest))

    if apply and runs:
        # Clean up now-empty old domain folders (but never the owner's own).
        for domain_dir in sorted(workspace_root.iterdir()):
            if domain_dir.is_dir() and domain_dir.name != owner and not any(domain_dir.iterdir()):
                domain_dir.rmdir()

    return moved
