#!/usr/bin/env python3
"""Validate CHANGELOG.md structure.

Usage:
    python scripts/lint_changelog.py

Checks:
    1. First section is [Unreleased]
    2. Exactly one [Unreleased] section
    3. No duplicate version sections
    4. Released versions in descending semver order
    5. No duplicate ### subsection heading within one version section
    6. In [Unreleased] and releases newer than SECTION_POLICY_CUTOFF, every
       ``###`` heading is a standard section, appears once, has content and
       follows the standard order (AGENTS.md "GitHub Release Policy")

Exit codes:
    0 — changelog is valid
    1 — structural error found
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
# Latest release when the section policy was adopted. This release and every
# older one keep their historical headings; their notes are never rewritten.
SECTION_POLICY_CUTOFF = (0, 2, 0)


def section_policy_applies(name: str) -> bool:
    """[Unreleased] and versions newer than the cutoff; unparsable names fail safe."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", name)
    if match is None:
        return True
    return tuple(int(n) for n in match.groups()) > SECTION_POLICY_CUTOFF


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
    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    if not changelog.exists():
        print(f"ERROR: {changelog} not found", file=sys.stderr)
        return 1

    content = changelog.read_text(encoding="utf-8")
    headers = re.findall(r"^## \[(\S+)\]", content, re.MULTILINE)

    # Rule 5: No duplicate ### subsection heading within one version section
    # (fenced code blocks are ignored so example headings do not trip the check).
    # The same pass collects each release's ### sections and their bodies for rule 6;
    # fenced lines count as body content, never as headings.
    section = ""
    seen_subsections: set[tuple[str, str]] = set()
    releases: list[tuple[str, list[tuple[str, str]]]] = []
    in_fence = False
    for line in content.splitlines():
        if in_fence and line.startswith("## ["):
            print(
                "ERROR: Release header inside an open code fence in CHANGELOG.md",
                file=sys.stderr,
            )
            return 1
        section_match = None if in_fence else re.match(r"^## \[(\S+)\]", line)
        if section_match:
            section = section_match.group(1)
            releases.append((section, []))
            continue
        heading = None if in_fence else re.match(r"^###\s+(.+)$", line)
        if heading and releases:
            releases[-1][1].append((heading.group(1).strip(), ""))
        elif releases and releases[-1][1]:
            title, body = releases[-1][1][-1]
            releases[-1][1][-1] = (title, body + line + "\n")
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("### "):
            key = (section, line.strip())
            if key in seen_subsections:
                print(
                    f"ERROR: Duplicate subsection heading '{line.strip()}' in [{section}]",
                    file=sys.stderr,
                )
                return 1
            seen_subsections.add(key)
    if in_fence:
        print("ERROR: Unclosed code fence in CHANGELOG.md", file=sys.stderr)
        return 1

    # Rule 6: standard ### sections in [Unreleased] and releases after the cutoff.
    for name, sections in releases:
        if section_policy_applies(name) and (error := check_sections(name, sections)):
            print(f"ERROR: {error}", file=sys.stderr)
            return 1

    if not headers:
        print("ERROR: No version sections found (expected '## [X.Y.Z]')", file=sys.stderr)
        return 1

    # Rule 1: First header must be [Unreleased]
    if headers[0] != "Unreleased":
        print(
            f"ERROR: First section must be [Unreleased], got [{headers[0]}]",
            file=sys.stderr,
        )
        return 1

    # Rule 2: Exactly one [Unreleased] section
    unreleased_count = headers.count("Unreleased")
    if unreleased_count > 1:
        print(
            f"ERROR: Found {unreleased_count} [Unreleased] sections, expected exactly 1",
            file=sys.stderr,
        )
        return 1

    versions = [h for h in headers if h != "Unreleased"]

    if not versions:
        print("WARNING: No released versions in CHANGELOG (only [Unreleased])")
        return 0

    # Rule 3: No duplicate version sections
    seen: set[str] = set()
    for v in versions:
        if v in seen:
            print(f"ERROR: Duplicate version section [{v}]", file=sys.stderr)
            return 1
        seen.add(v)

    # Rule 4: Released versions in descending semver order
    # Validate per-version so one bad entry doesn't disable all checking.
    try:
        from packaging.version import InvalidVersion, Version

        prev_version: Version | None = None
        prev_name: str | None = None
        for v in versions:
            try:
                current = Version(v)
            except InvalidVersion:
                print(
                    f"WARNING: [{v}] is not valid PEP 440, skipping ordering check for this entry",
                    file=sys.stderr,
                )
                continue

            if prev_version is not None and current > prev_version:
                print(
                    f"ERROR: [{v}] should come before [{prev_name}] "
                    f"(versions must be in descending order)",
                    file=sys.stderr,
                )
                return 1
            prev_version = current
            prev_name = v
    except ImportError:
        print("NOTE: 'packaging' not installed, skipping semver ordering check")

    print(f"OK: {len(versions)} version(s), order valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
