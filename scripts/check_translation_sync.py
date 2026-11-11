#!/usr/bin/env python3
"""Check README translation drift using the repository's documentation policy.

English README.md is canonical. Korean docs/README.ko.md must be updated when
the English README changes, unless a maintainer approves a documented
`translations-deferred` follow-up. Other language translations are advisory.
The independent Korean docs/ko structural checks remain required.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SOURCE = Path("README.md")
REQUIRED_LANGS = {"ko"}
LANGS = {"ko": "한국어", "de": "Deutsch", "hi": "हिन्दी", "ru": "Русский", "zh": "中文"}


def changed_files() -> set[str]:
    base = os.environ.get("BASE_REF", "main")
    ref = base if base.startswith("origin/") else f"origin/{base}"
    out = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{ref}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # --no-renames reports a rename as a deletion of the old path plus an addition
    # of the new one, so both sides are listed, one path per line. Plain
    # --name-only would print only the new path of a rename.
    return {line.strip() for line in out.splitlines() if line.strip()}


def main() -> int:
    present = sorted(p.stem.split(".")[1] for p in Path("docs").glob("README.*.md"))
    if not present:
        print("no translations present — nothing to sync")
        return 0
    changed = changed_files()
    if SOURCE.as_posix() not in changed:
        print(f"{SOURCE} unchanged in this PR — translation sync OK")
        return 0
    failures, warnings = [], []
    for lang in present:
        path = f"docs/README.{lang}.md"
        if path in changed:
            continue
        label = LANGS.get(lang, lang)
        if lang in REQUIRED_LANGS:
            failures.append(f"{path} ({label})")
        else:
            warnings.append(f"{path} ({label})")
    for w in warnings:
        print(
            f"::warning file=README.md::community translation drifted: {w} — maintainers will open a resync PR"
        )
    if failures:
        print(
            "::error::README.md changed but the required translation did not: "
            + ", ".join(failures)
            + ". Update it in this PR, or request maintainer approval for the `translations-deferred` label."
        )
        return 1
    print("translation sync OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
