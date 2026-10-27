#!/usr/bin/env python3
"""Copy the self-contained local skill into a client's standard discovery folder.

The repository root stays the source of truth. Existing installations are never
overwritten; Git clones can still be installed/updated with git clone / git pull.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
SKILL_NAME = "ue-repo-reader"
PROJECT_DIRS = {"codex": ".agents", "claude": ".claude", "copilot": ".github"}
USER_DIRS = {"codex": ".agents", "claude": ".claude", "copilot": ".agents"}


def install(client: str, root: Path, *, personal: bool = False) -> Path:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("installation root must be an existing directory")
    folder = (USER_DIRS if personal else PROJECT_DIRS)[client]
    destination = root / folder / "skills" / SKILL_NAME
    # Do not follow a pre-existing link/junction in the discovery path, including
    # dangling links. No deletion or replacement of existing installations occurs.
    for part in (destination, destination.parent, destination.parent.parent):
        if os.path.lexists(part):
            info = part.lstat()
            if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"skill installation path contains a link/junction: {part}")
    if destination.exists():
        raise FileExistsError(f"skill already exists: {destination}; update a Git clone with git pull, "
                              "or move the previous snapshot before installing again")

    files = [SOURCE / "SKILL.md", *sorted((SOURCE / "scripts").glob("*.py"))]
    # Carry license/notice files if the source distribution provides them.
    files += [p for pattern in ("LICENSE*", "NOTICE*") for p in SOURCE.glob(pattern) if p.is_file()]
    required = {"ue_repo_digest.py", "bp_reader.py", "data_reader.py", "map_reader.py"}
    if not (SOURCE / "SKILL.md").is_file() or not required <= {p.name for p in files}:
        raise ValueError("source skill is incomplete; run this script from a complete checkout or skill")
    if any(p.is_symlink() for p in files):
        raise ValueError("source skill files must be regular files, not links")

    destination.mkdir(parents=True, exist_ok=False)
    for source in files:
        relative = source.relative_to(SOURCE)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=PROJECT_DIRS, required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--user", action="store_true", help="install into the current user's home")
    scope.add_argument("--project", type=Path, help="install into an existing local project directory")
    args = parser.parse_args(argv)
    try:
        destination = install(args.client, Path.home() if args.user else args.project, personal=args.user)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Installed local skill: {destination}")
    print(f"Entry point: {destination / 'SKILL.md'}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
