"""THIRD_PARTY_LICENSES.md covers every dependency declaration (#217).

Standard library only, like the other repository-tooling tests. The inventory is
a dated snapshot, so version bumps inside a requirements file do not fail this
check; adding or removing a requirements file, changing a file's declared
packages, or installing a new package directly from a workflow does.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github" / "workflows"


def _load(name: str):  # noqa: ANN202
    spec = importlib.util.spec_from_file_location(f"_{name}", ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


build = _load("build_license_inventory")
generator = _load("generate_third_party_licenses")


def generated() -> str:
    return DOC[DOC.index(build.BEGIN) : DOC.index(build.END)]


def rows(heading: str, width: int) -> list[list[str]]:
    text = generated()
    start = text.index(heading)
    end = text.find("\n### ", start + 1)
    found = []
    for line in text[start : len(text) if end == -1 else end].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == width and cells[0] not in {"Set", "Name"} and set(cells[0]) - {"-"}:
            found.append(cells)
    return found


def set_table() -> dict[str, tuple[list[str], list[str]]]:
    table = {}
    for set_id, files, declared in rows("### Requirement sets", 3):
        paths = re.findall(r"`([^`]+)`", files)
        table[set_id] = (paths, [n.strip() for n in declared.split(",") if n.strip()])
    return table


def package_table() -> list[dict[str, str]]:
    keys = ("name", "versions", "license", "category", "url", "sets")
    return [dict(zip(keys, cells)) for cells in rows("### Packages", 6)]


def workflow_installs() -> set[str]:
    """Package names that workflows ``pip install`` directly (not via ``-r``)."""
    names = set()
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#") or "pip install" not in line:
                continue
            tokens = line.split("pip install", 1)[1].split()
            skip_next = False
            for token in tokens:
                if skip_next:
                    skip_next = False
                    continue
                if token in {"-r", "--requirement", "-c", "--constraint"}:
                    skip_next = True
                    continue
                if token.startswith("-") or token in {"&&", "pip"}:
                    continue
                match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", token)
                if match:
                    names.add(build.canonical(match.group(0)))
    return names


class RequirementCoverage(unittest.TestCase):
    def test_every_requirements_file_is_in_exactly_one_set(self) -> None:
        listed = [p for paths, _ in set_table().values() for p in paths]
        self.assertEqual(len(listed), len(set(listed)), "a file is listed in two sets")
        on_disk = {f.relative_to(ROOT).as_posix() for f in build.requirement_files()}
        self.assertEqual(
            set(listed),
            on_disk,
            "requirements files changed; run scripts/build_license_inventory.py --write",
        )

    def test_each_file_declares_the_packages_of_its_set(self) -> None:
        for set_id, (paths, declared) in set_table().items():
            for path in paths:
                lines = build.requirement_lines(ROOT / path)
                self.assertEqual(build.declared_names(lines), declared, f"{path} ({set_id})")

    def test_tooling_set_matches_the_build_script(self) -> None:
        self.assertEqual(set_table()["TOOLING"][1], build.declared_names(build.TOOLING))

    def test_workflow_installs_are_inventoried(self) -> None:
        names = {build.canonical(p["name"]) for p in package_table()}
        missing = sorted(workflow_installs() - names)
        self.assertFalse(missing, f"installed by a workflow but not inventoried: {missing}")

    def test_every_set_contributes_packages_and_every_reference_exists(self) -> None:
        sets = set(set_table())
        used = {s.strip() for p in package_table() for s in p["sets"].split(",")}
        self.assertEqual(used, sets)


class LicenseClassification(unittest.TestCase):
    def test_every_category_matches_the_generator(self) -> None:
        for package in package_table():
            with self.subTest(package=package["name"]):
                self.assertEqual(generator.category(package["license"]), package["category"])

    def test_every_review_and_mpl_row_is_explained(self) -> None:
        categories = DOC[DOC.index("## License categories") : DOC.index("## How the inventory")]
        reviewed = categories[categories.index("### Reviewed entries") :]
        for package in package_table():
            name = build.canonical(package["name"])
            if package["category"] == "Needs review":
                self.assertRegex(reviewed, rf"(?i)\*\*{re.escape(name)}\*\*")
            elif package["category"].startswith("Weak copyleft"):
                self.assertIn(f"`{name}`", categories, f"MPL package {name} not named")
            else:
                self.assertEqual(package["category"], "Permissive", package)

    def test_no_blanket_permissive_claim(self) -> None:
        for stale in ("No dependency is copyleft", "All listed dependencies are distributed under"):
            self.assertNotIn(stale, DOC)

    def test_generation_inputs_are_recorded(self) -> None:
        record = DOC[DOC.index("## How the inventory was generated") :]
        self.assertRegex(record, r"commit `[0-9a-f]{40}`")
        self.assertRegex(record, r"CPython 3\.\d+\.\d+ on Linux")
        self.assertIn("scripts/build_license_inventory.py --python 3.12 --write", record)


if __name__ == "__main__":
    unittest.main()
