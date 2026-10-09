#!/usr/bin/env python3
"""driver_floors.py - Run representative goldens on the exact documented driver floors (#241).

``scripts/check_dependency_floors.py`` keeps every recipe ``requirements.txt``
in line with the floors documented in ``SUPPORT_MATRIX.md``, but only as text:
CI otherwise installs the latest driver releases. This script installs each
documented floor exactly (``pycubrid==X`` / ``sqlalchemy-cubrid==Y``) into its
own virtual environment and runs the goldens of a representative set of example
directories against a live CUBRID on ``localhost:33000``, the same way
``make verify`` does (output piped through ``scripts/normalize_output.sh`` and
compared with ``expected/<name>.expected``).

The pins are read from the directories' own ``requirements.txt`` (their ``>=``
lower bound), so the lane installs exactly what a user following a recipe's
README could resolve to; ``check_dependency_floors.py`` in turn ties those
lower bounds to ``SUPPORT_MATRIX.md``. Directories without a
``requirements.txt`` (``NO_REQUIREMENTS_FLOORS``) are pycubrid-only examples and
run on the pycubrid floor ``SUPPORT_MATRIX.md`` documents for them.
``tests/test_dependency_floors.py`` fails when a documented floor is not exercised
by any set below.

Usage:
    python scripts/driver_floors.py plan
    python scripts/driver_floors.py run [--set NAME ...] [--workdir DIR]
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = REPO_ROOT / "SUPPORT_MATRIX.md"
NORMALIZE = REPO_ROOT / "scripts/normalize_output.sh"

_SPEC = importlib.util.spec_from_file_location(
    "check_dependency_floors", REPO_ROOT / "scripts/check_dependency_floors.py"
)
floors = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(floors)

# Golden directories that ship no requirements.txt; each imports only pycubrid
# and needs the global floor (None) or the documented higher floor
# (SUPPORT_MATRIX.md: 1.6.x returns CLOB values with escaped newlines).
NO_REQUIREMENTS_FLOORS: dict[str, str | None] = {
    "fundamentals/crud": None,
    "fundamentals/error-handling": None,
    "fundamentals/lob-handling": "1.7",
    "fundamentals/transactions": None,
}

# (name, example directories). Every directory in a set must declare the same
# driver floors; one virtual environment is created per set.
FLOOR_SETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "global",
        (
            "fundamentals/crud",
            "fundamentals/error-handling",
            "fundamentals/transactions",
            "fundamentals/json",
            "pitfalls/reserved-words",
            "migration/java-to-python",
            "quickstart/5min-sqlalchemy",
        ),
    ),
    ("advanced-sqlalchemy", ("fundamentals/pandas",)),
    ("async", ("fundamentals/async",)),
    ("1.7-line", ("fundamentals/lob-handling", "fundamentals/connect", "fundamentals/orm-basics")),
    ("1.9-line", ("fundamentals/pycubrid", "fundamentals/sqlalchemy")),
    ("alembic", ("fundamentals/alembic",)),
)

SCRIPT_TIMEOUT = 60
READY_TIMEOUT = 180


def directory_floors(root: Path, directory: str, matrix: str) -> dict[str, str]:
    """Driver lower bounds a directory declares (``{driver: version}``)."""
    req = root / directory / "requirements.txt"
    if not req.is_file():
        if directory not in NO_REQUIREMENTS_FLOORS:
            raise ValueError(f"{directory}: no requirements.txt and not in NO_REQUIREMENTS_FLOORS")
        floor = NO_REQUIREMENTS_FLOORS[directory]
        return {"pycubrid": floor or floors._global_floors(matrix)["pycubrid"]}
    found: dict[str, str] = {}
    for line in req.read_text(encoding="utf-8").splitlines():
        parsed = floors.parse_driver_requirement(line)
        if parsed is None:
            continue
        driver, rest = parsed
        match = floors.FLOOR_RE.match(rest)
        if not match:
            raise ValueError(f"{req.relative_to(root)}: no '>=' floor for {driver}: {line!r}")
        found[driver] = match.group(1)
    if not found:
        raise ValueError(f"{req.relative_to(root)}: declares no pycubrid/sqlalchemy-cubrid driver")
    return found


def plan(root: Path = REPO_ROOT, matrix: str | None = None) -> list[tuple[str, dict, tuple]]:
    """Return ``(name, {driver: floor}, directories)`` for every floor set."""
    if matrix is None:
        matrix = (root / "SUPPORT_MATRIX.md").read_text(encoding="utf-8")
    result = []
    for name, dirs in FLOOR_SETS:
        pins: dict[str, str] = {}
        for directory in dirs:
            for driver, version in directory_floors(root, directory, matrix).items():
                if pins.setdefault(driver, version) != version:
                    raise ValueError(
                        f"floor set {name!r}: {directory} declares {driver}>={version}, "
                        f"another directory declares {driver}>={pins[driver]}"
                    )
        result.append((name, pins, dirs))
    return result


def same_release(installed: str, floor: str) -> bool:
    """``1.7`` and ``1.7.0`` are the same release (PEP 440 zero padding).

    >>> same_release("1.7.0", "1.7"), same_release("1.0.0", "1.0"), same_release("1.7.1", "1.7")
    (True, True, False)
    """

    def key(version: str) -> tuple[int, ...]:
        parts = [int(p) for p in version.split(".")]
        while parts and parts[-1] == 0:
            parts.pop()
        return tuple(parts)

    return key(installed) == key(floor)


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def _install(venv: Path, pins: dict[str, str], dirs: tuple[str, ...]) -> Path:
    _run([sys.executable, "-m", "venv", str(venv)])
    python = venv / "bin/python"
    constraints = venv / "floor-constraints.txt"
    constraints.write_text("".join(f"{d}=={v}\n" for d, v in sorted(pins.items())))
    reqs = []
    for directory in dirs:
        req = REPO_ROOT / directory / "requirements.txt"
        if req.is_file():
            reqs += ["-r", str(req)]
    env = {k: v for k, v in os.environ.items() if not k.startswith("PIP_")}
    _run([str(python), "-m", "pip", "install", "-q", "--upgrade", "pip"], env=env)
    _run(
        [str(python), "-m", "pip", "install", "-q", "-c", str(constraints), *reqs]
        + [f"{d}=={v}" for d, v in sorted(pins.items())],
        env=env,
    )
    return python


def _installed(python: Path) -> dict[str, str]:
    """Versions of every driver in the venv (absent drivers are omitted)."""
    code = (
        "import importlib.metadata as m, sys\n"
        "for d in sys.argv[1:]:\n"
        "    try: print(d, m.version(d))\n"
        "    except m.PackageNotFoundError: pass\n"
    )
    out = _run([str(python), "-c", code, *floors.DRIVERS], capture_output=True).stdout
    return dict(line.split(" ", 1) for line in out.splitlines())


def floor_problems(installed: dict[str, str], pins: dict[str, str]) -> list[str]:
    """Pinned drivers must be at their floor and no other driver may be installed.

    An unpinned driver (even a transitive one such as the ``pycubrid`` that
    ``sqlalchemy-cubrid`` depends on) would float to the latest release.

    >>> floor_problems({"pycubrid": "1.7.0"}, {"pycubrid": "1.7"})
    []
    >>> floor_problems({"pycubrid": "1.9.0", "sqlalchemy-cubrid": "1.5"}, {"sqlalchemy-cubrid": "1.5"})
    ['pycubrid 1.9.0 is installed but not pinned (it would float)']
    >>> floor_problems({}, {"pycubrid": "1.7"})
    ['pycubrid installed None, floor 1.7']
    """
    problems = [
        f"{d} installed {installed.get(d)}, floor {v}"
        for d, v in sorted(pins.items())
        if not same_release(installed.get(d, "0"), v)
    ]
    problems += [
        f"{d} {v} is installed but not pinned (it would float)"
        for d, v in sorted(installed.items())
        if d not in pins
    ]
    return problems


def _wait_ready(python: Path) -> None:
    code = (
        "import pycubrid\n"
        "pycubrid.connect(host='localhost', port=33000, database='testdb',"
        " user='dba', password='').close()\n"
    )
    deadline = time.monotonic() + READY_TIMEOUT
    while subprocess.run([str(python), "-c", code], capture_output=True).returncode != 0:
        if time.monotonic() > deadline:
            raise RuntimeError(f"CUBRID on localhost:33000 not ready after {READY_TIMEOUT}s")
        time.sleep(3)


def _run_golden(python: Path, script: Path, expected: Path) -> list[str]:
    """Return problems (empty when the normalized output matches the golden)."""
    try:
        proc = subprocess.run(
            [str(python), str(script)],
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=SCRIPT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return [f"timed out after {SCRIPT_TIMEOUT}s"]
    normalized = subprocess.run(
        ["bash", str(NORMALIZE)], input=proc.stdout, stdout=subprocess.PIPE, check=True
    ).stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        return [f"script exited {proc.returncode}", normalized[-4000:]]
    # make verify compares $(...) captures, which drop trailing newlines.
    actual = normalized.rstrip("\n")
    wanted = expected.read_text(encoding="utf-8").rstrip("\n")
    if actual == wanted:
        return []
    diff = difflib.unified_diff(
        wanted.splitlines(), actual.splitlines(), str(expected), "actual", lineterm=""
    )
    return ["output differs from golden", "\n".join(diff)]


def run(selected: list[str], workdir: Path) -> int:
    sets = [s for s in plan() if not selected or s[0] in selected]
    unknown = set(selected) - {name for name, _, _ in plan()}
    if unknown:
        print(f"Unknown floor set(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    rows = []
    failed = 0
    ready = False
    for name, pins, dirs in sets:
        print(f"::group::floor set {name}: " + ", ".join(f"{d}=={v}" for d, v in pins.items()))
        installed: dict[str, str] = {}
        problems: list[str] = []
        passed = 0
        total = 0
        try:
            python = _install(workdir / name, pins, dirs)
            installed = _installed(python)
            problems = floor_problems(installed, pins)
            if not ready:
                _wait_ready(python)
                ready = True
            for directory in dirs:
                for expected in sorted((REPO_ROOT / directory / "expected").glob("*.expected")):
                    total += 1
                    script = expected.parent.parent / f"{expected.stem}.py"
                    label = script.relative_to(REPO_ROOT).as_posix()
                    issues = (
                        _run_golden(python, script, expected)
                        if script.is_file()
                        else ["no matching script"]
                    )
                    if issues:
                        problems.append(f"{label}: {issues[0]}")
                        print(f"  FAIL {label}: " + "\n".join(issues))
                    else:
                        passed += 1
                        print(f"  PASS {label}")
            if total == 0:
                problems.append("no goldens found")
        except subprocess.CalledProcessError as exc:
            problems.append(f"command failed ({exc.returncode}): {' '.join(map(str, exc.cmd))}")
        print("::endgroup::")
        for problem in problems:
            print(f"::error::floor set {name}: {problem}")
        failed += bool(problems)
        rows.append(
            f"| `{name}` | "
            + ", ".join(f"`{d}=={v}`" for d, v in sorted(pins.items()))
            + " | "
            + ", ".join(f"`{d} {v}`" for d, v in sorted(installed.items()))
            + f" | {passed}/{total} | {'pass' if not problems else 'FAIL'} |"
        )
    summary = [
        "### Documented driver floors (exact install, live CUBRID)",
        "",
        "| Floor set | Pinned | Installed | Goldens | Result |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    print("\n".join(summary))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write("\n".join(summary) + "\n")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="print every floor set, its pins and directories")
    run_parser = sub.add_parser("run", help="install each floor set and run its goldens")
    run_parser.add_argument("--set", action="append", default=[], dest="sets")
    run_parser.add_argument("--workdir", type=Path)
    args = parser.parse_args(argv)
    if args.command == "plan":
        for name, pins, dirs in plan():
            print(f"{name}: " + " ".join(f"{d}=={v}" for d, v in sorted(pins.items())))
            for directory in dirs:
                print(f"  {directory}")
        return 0
    if args.workdir:
        return run(args.sets, args.workdir)
    with tempfile.TemporaryDirectory(prefix="driver-floors-") as tmp:
        return run(args.sets, Path(tmp))


if __name__ == "__main__":
    sys.exit(main())
