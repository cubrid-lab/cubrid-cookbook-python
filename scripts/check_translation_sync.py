#!/usr/bin/env python3
"""Fail a PR when README.md changes without any of its translations changing.

Translations live at docs/README.<lang>.md. Escape hatch: the
`translations-deferred` PR label (the workflow job skips when present).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SOURCE = Path("README.md")

def changed_files() -> set[str]:
    base = os.environ.get("BASE_REF", "origin/main")
    out = subprocess.run(
        ["git", "diff", "--name-only", f"origin/{base}...HEAD"]
        if not base.startswith("origin/")
        else ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}

def main() -> int:
    translations = sorted(p.name for p in Path("docs").glob("README.*.md"))
    if not translations:
        print("no translations present — nothing to sync")
        return 0
    changed = changed_files()
    if SOURCE.as_posix() not in changed:
        print(f"{SOURCE} unchanged in this PR — translation sync OK")
        return 0
    touched = sorted(t for t in translations if f"docs/{t}" in changed)
    if not touched:
        print(
            f"::error::{SOURCE} changed but none of its translations did "
            f"({', '.join('docs/' + t for t in translations)}). Update them in "
            "this PR, or add the `translations-deferred` label if the gap is "
            "intentional."
        )
        return 1
    print(f"translation sync OK: {SOURCE} + {', '.join(touched)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
