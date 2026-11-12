#!/usr/bin/env python3
"""Sync the skill folder from the single source of truth.

The scripts and rule texts live at the repo root so the npm entry point can run
them and the tests can read them. `skills add` only copies `skills/<name>/`, so
that folder needs its own copy.

Two copies drift. Rather than hope both get edited, this script copies from the
root into the skill folder and is the only supported way to update it. `npm test`
runs it in check mode, so a forgotten sync fails the build instead of shipping a
stale skill.

    python3 sync.py            # copy root -> skills/crew
    python3 sync.py --check    # exit 1 if they differ
"""
import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT / "skills" / "crew"

SCRIPT_FILES = ("starixs.py", "gate.py", "gate_install.py", "paths.py")


def pairs():
    """(source, destination) for everything that must be mirrored."""
    out = []
    for name in SCRIPT_FILES:
        out.append((ROOT / "scripts" / name, SKILL / "scripts" / name))
    for source in sorted((ROOT / "references" / "rules").glob("*.md")):
        out.append((source, SKILL / "references" / "rules" / source.name))
    out.append((ROOT / "config.json", SKILL / "config.json"))
    return out


def check() -> int:
    problems = []
    for source, dest in pairs():
        if not source.is_file():
            problems.append("missing source: " + str(source))
            continue
        if not dest.is_file():
            problems.append("not synced: " + str(dest))
        elif not filecmp.cmp(source, dest, shallow=False):
            problems.append("differs: " + str(dest))
    extra = []
    for found in sorted((SKILL / "scripts").glob("*.py")):
        if found.name not in SCRIPT_FILES:
            extra.append("unexpected file in skill folder: " + str(found))
    problems.extend(extra)
    if problems:
        print("skill folder is out of sync with the repo root:")
        for problem in problems:
            print("  " + problem)
        print("\nRun: python3 sync.py")
        return 1
    print("skill folder matches the repo root (%d files)" % len(pairs()))
    return 0


def sync() -> int:
    for source, dest in pairs():
        if not source.is_file():
            print("missing source: " + str(source))
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        print("synced " + str(dest.relative_to(ROOT)))
    # remove files in the skill folder that no longer exist at the root
    for found in sorted((SKILL / "scripts").glob("*.py")):
        if found.name not in SCRIPT_FILES:
            found.unlink()
            print("removed stale " + str(found.relative_to(ROOT)))
    return 0


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="Sync skills/crew from the repo root.")
    parser.add_argument("--check", action="store_true", help="fail if they differ")
    args = parser.parse_args(argv)
    return check() if args.check else sync()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
