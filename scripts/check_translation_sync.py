#!/usr/bin/env python3
"""Translation-drift policy for cubrid-lab (hybrid, per Oracle review 2026-09).

- 한국어 (docs/README.ko.md) is REQUIRED for contest readiness: a PR that
  changes README.md without it FAILS (escape hatch: `translations-deferred`).
- Other languages are community translations: drift emits a warning
  annotation only; the maintainers' AI agent opens follow-up resync PRs.
- English is canonical. The Korean hard gate is time-boxed until the
  2026 contest finals and should be relaxed to advisory afterwards.
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
            + ". Update it in this PR, or add the `translations-deferred` label if deferring is intentional."
        )
        return 1
    print("translation sync OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
