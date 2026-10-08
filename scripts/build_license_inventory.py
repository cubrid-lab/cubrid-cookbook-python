"""Regenerate the dependency/license inventory in THIRD_PARTY_LICENSES.md (#217).

Every ``requirements*.txt`` in the repository is a separately installable
example, so the requirement files are grouped by their normalised contents and
each distinct set is installed into its own fresh ``uv`` virtual environment;
nothing is flattened into one shared install. The CI and docs tooling that the
workflows install directly (``TOOLING``) is one more set. In every environment
``scripts/generate_third_party_licenses.py`` (standard library only) reports the
installed distributions, and the results are consolidated with the sets that
pulled each one in. The generated section between the markers in
THIRD_PARTY_LICENSES.md is replaced in place::

    python scripts/build_license_inventory.py --python 3.12 --write

Requires ``uv`` on PATH. Only the standard library is used.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "THIRD_PARTY_LICENSES.md"
GENERATOR = ROOT / "scripts" / "generate_third_party_licenses.py"
BEGIN = "<!-- BEGIN GENERATED INVENTORY: scripts/build_license_inventory.py -->"
END = "<!-- END GENERATED INVENTORY -->"

# Installed directly by .github/workflows (ci.yml, docs.yml, smoke-test.yml)
# rather than through a requirements file.
TOOLING = ("ruff==0.16.4", "mkdocs-material", "pymdown-extensions", "pytest", "pytest-asyncio")

SKIP_DIRS = {"node_modules", "site-packages", "__pycache__"}


@dataclass
class Package:
    name: str
    category: str
    url: str
    versions: set[str] = field(default_factory=set)
    sets: set[str] = field(default_factory=set)


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_files(root: Path = ROOT) -> list[Path]:
    """Every tracked-looking requirements file, skipping virtualenvs and dot-dirs."""
    found = []
    for path in root.rglob("requirements*.txt"):
        parts = path.relative_to(root).parts[:-1]
        if any(p.startswith(".") or p in SKIP_DIRS or "venv" in p for p in parts):
            continue
        found.append(path)
    return sorted(found)


def requirement_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return sorted(lines)


def declared_names(lines: list[str] | tuple[str, ...]) -> list[str]:
    names = set()
    for line in lines:
        match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if match:
            names.add(canonical(match.group(1)))
    return sorted(names)


def requirement_sets(root: Path = ROOT) -> list[tuple[str, list[str], list[Path]]]:
    """Group requirement files with identical normalised contents: (id, lines, files)."""
    groups: dict[tuple[str, ...], list[Path]] = {}
    for path in requirement_files(root):
        groups.setdefault(tuple(requirement_lines(path)), []).append(path)
    ordered = sorted(groups.items(), key=lambda item: str(item[1][0]))
    sets = [(f"S{i:02d}", list(lines), files) for i, (lines, files) in enumerate(ordered, 1)]
    sets.append(("TOOLING", list(TOOLING), []))
    return sets


def inventory(python: str, lines: list[str], workdir: Path) -> list[list[str]]:
    venv = workdir / "venv"
    reqs = workdir / "requirements.txt"
    reqs.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["uv", "venv", "-q", "-p", python, str(venv)], check=True)
    interpreter = venv / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "-q", "-p", str(interpreter), "-r", str(reqs)], check=True
    )
    out = subprocess.run(
        [str(interpreter), str(GENERATOR)], check=True, capture_output=True, text=True
    ).stdout
    rows = []
    for line in out.splitlines()[2:]:
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


def render(python: str) -> str:
    sets = requirement_sets()
    packages: dict[tuple[str, str], Package] = {}
    for set_id, lines, _ in sets:
        with tempfile.TemporaryDirectory() as tmp:
            for name, version, lic, cat, url in inventory(python, lines, Path(tmp)):
                entry = packages.setdefault((canonical(name), lic), Package(name, cat, url))
                entry.versions.add(version)
                entry.sets.add(set_id)
        print(f"{set_id}: done", file=sys.stderr)

    out = [BEGIN, "", "### Requirement sets", ""]
    out.append("| Set | Requirement files | Declared packages |")
    out.append("|---|---|---|")
    for set_id, lines, files in sets:
        where = (
            "<br>".join(f"`{f.relative_to(ROOT).as_posix()}`" for f in files)
            if files
            else "CI and docs workflows (the TOOLING constant in this script)"
        )
        out.append(f"| {set_id} | {where} | {', '.join(declared_names(lines))} |")
    out += ["", f"### Packages ({len(packages)} rows)", ""]
    out.append("| Name | Observed versions | License | Category | URL | Sets |")
    out.append("|---|---|---|---|---|---|")
    order = {"Permissive": 0, "Weak copyleft (MPL)": 1, "Needs review": 2}
    for (_, lic), e in sorted(packages.items(), key=lambda kv: (order[kv[1].category], kv[0][0])):
        versions = ", ".join(sorted(e.versions))
        used = ", ".join(sorted(e.sets))
        out.append(f"| {e.name} | {versions} | {lic} | {e.category} | {e.url} | {used} |")
    out += ["", END]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--python", default="3.12", help="interpreter for every environment")
    parser.add_argument("--write", action="store_true", help="update THIRD_PARTY_LICENSES.md")
    args = parser.parse_args(argv)
    section = render(args.python)
    if not args.write:
        print(section)
        return 0
    text = DOC.read_text(encoding="utf-8")
    start, end = text.index(BEGIN), text.index(END) + len(END)
    DOC.write_text(text[:start] + section + text[end:], encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
