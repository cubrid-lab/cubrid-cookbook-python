#!/usr/bin/env python3
"""lint_changelog.py - Keep CHANGELOG.md ``###`` sections on the standard list.

Usage:
    python scripts/lint_changelog.py

In ``[Unreleased]`` and in every release newer than ``SECTION_POLICY_CUTOFF``,
each ``###`` heading must be one of ``ALLOWED_SECTIONS``, appear once, have
content and follow the standard order (AGENTS.md "GitHub Release Policy").
Fenced code blocks are content, never headings, and an unclosed fence is an
error because it would hide every later heading.

The historical ``### Previous Releases`` heading ends the checked part of its
release: it and every line after it are legacy notes that predate the
standard sections and are never rewritten.

Exit code 0 when the changelog is valid; 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Standard ``###`` headings, in order (AGENTS.md "GitHub Release Policy").
ALLOWED_SECTIONS = (
    "Upgrade notes",
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
    "Performance",
    "Documentation",
    "CI",
    "Tests",
)
# Latest release tag (v0.2.0) when the section policy was adopted. This release and
# every older one keep their historical headings; their notes are never rewritten.
SECTION_POLICY_CUTOFF = (0, 2, 0)
# Legacy heading inside [Unreleased]: everything from here to the end of the release
# is historical text kept as written.
HISTORICAL_HEADING = "Previous Releases"

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section_policy_applies(name: str) -> bool:
    """[Unreleased] and versions newer than the cutoff; unparsable names fail safe."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", name)
    if match is None:
        return True
    return tuple(int(n) for n in match.groups()) > SECTION_POLICY_CUTOFF


def parse(content: str) -> tuple[list[tuple[str, list[tuple[str, str]]]], bool]:
    """Split a changelog into releases of ``(### title, body)`` pairs.

    Returns the releases and whether a code fence is left open. Fenced lines are
    body content, never release or section headings. Sections from the historical
    heading onward are dropped.
    """
    releases: list[tuple[str, list[tuple[str, str]]]] = []
    in_fence = False
    historical = False
    for line in content.splitlines():
        release = None if in_fence else re.match(r"^## \[(\S+)\]", line)
        if release:
            releases.append((release.group(1), []))
            historical = False
            continue
        heading = None if in_fence else re.match(r"^###\s+(.+)$", line)
        if heading and releases:
            title = heading.group(1).strip()
            historical = historical or title == HISTORICAL_HEADING
            if not historical:
                releases[-1][1].append((title, ""))
        elif releases and releases[-1][1] and not historical:
            title, body = releases[-1][1][-1]
            releases[-1][1][-1] = (title, body + line + "\n")
        if line.startswith("```"):
            in_fence = not in_fence
    return releases, in_fence


def check_sections(name: str, sections: list[tuple[str, str]]) -> str | None:
    """Return the first section-policy violation of one release, or None."""
    last = -1
    for title, body in sections:
        if title not in ALLOWED_SECTIONS:
            return (
                f"Subsection '### {title}' in [{name}] is not a standard section "
                f"(allowed, in order: {', '.join(ALLOWED_SECTIONS)})"
            )
        if not body.strip():
            return f"Subsection '### {title}' in [{name}] is empty"
        index = ALLOWED_SECTIONS.index(title)
        if index == last:
            return f"Duplicate subsection '### {title}' in [{name}]"
        if index < last:
            return (
                f"Subsection '### {title}' in [{name}] must come before "
                f"'### {ALLOWED_SECTIONS[last]}'"
            )
        last = index
    return None


def main() -> int:
    if not CHANGELOG.exists():
        print(f"ERROR: {CHANGELOG} not found", file=sys.stderr)
        return 1

    releases, unclosed = parse(CHANGELOG.read_text(encoding="utf-8"))
    if unclosed:
        print("ERROR: Unclosed code fence in CHANGELOG.md", file=sys.stderr)
        return 1
    if not releases:
        print("ERROR: No version sections found (expected '## [Unreleased]')", file=sys.stderr)
        return 1

    for name, sections in releases:
        if section_policy_applies(name) and (error := check_sections(name, sections)):
            print(f"ERROR: {error}", file=sys.stderr)
            return 1

    print(f"OK: {len(releases)} release section(s) use the standard headings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
