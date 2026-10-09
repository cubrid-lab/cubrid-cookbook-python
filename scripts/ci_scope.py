#!/usr/bin/env python3
"""Classify a CI run into the validation lanes ``ci.yml`` must run (#222).

Reads changed paths (one per line) on stdin and prints ``key=value`` lines for
``$GITHUB_OUTPUT``. ``ci.yml`` starts only the lanes selected here and its
``ci-gate`` accepts a ``skipped`` lane only when this output is exactly
``false`` for it.

Tiers:

* ``docs`` - docs/metadata-only pull request: cheap checks only, no live CUBRID.
* ``pr``   - ordinary pull request: the live suite(s) of the touched recipe
  families on one representative CUBRID (11.4) and Python (3.12). Shared live
  infrastructure fans out to every suite plus the CUBRID 11.2 smoke lane;
  Python compatibility endpoints run only for compatibility-surface changes.
* ``full`` - a pull request that changes the CI policy itself: every lane, both
  CUBRID versions and the Python 3.11/3.14 endpoints.
* ``main`` - push, schedule or manual dispatch: Python 3.11-3.14 compatibility
  and CQRS on both CUBRID versions; the weekly schedule and manual runs also
  install the documented driver floors (``floors``, #241). ``smoke-test.yml`` owns the broad 11.2/11.4
  goldens and recipe suites on these events, so ``ci.yml`` does not repeat them.

Pull requests that change a documented driver floor (``FLOORS``) also run the
exact-floor lane (``scripts/driver_floors.py``) on CUBRID 11.4, even when the
change is otherwise docs-only (``SUPPORT_MATRIX.md``).

Unknown paths and unknown events fail closed to a wider tier.

The strict docs-site build (``make docs``) is not classified: ``ci.yml`` runs it on
every pull request because it is the guard for README links to deleted or renamed
examples (#154), which a deletion-only diff would otherwise skip.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from fnmatch import fnmatchcase
from pathlib import Path

REPRESENTATIVE_PYTHON = "3.12"
PYTHON_ENDPOINTS = ["3.11", "3.14"]
PYTHON_ALL = ["3.11", "3.12", "3.13", "3.14"]
DEFAULT_CUBRID = ["11.4"]
CUBRID_ENDPOINTS = ["11.2", "11.4"]

PR_EVENTS = {"pull_request"}
MAIN_EVENTS = {"push", "schedule", "workflow_dispatch"}
# Floors are fixed releases: re-checking them on every push adds nothing, but the
# weekly schedule catches a new release of a non-pinned dependency (SQLAlchemy,
# pandas, ...) breaking an old driver.
FLOOR_EVENTS = {"schedule", "workflow_dispatch"}

CQRS_ROOT = "templates/api-service-fastapi/recipes/10-cqrs-event-sourcing"

# fnmatch's ``*`` also crosses ``/``, so ``docs/*`` covers the whole tree.
# Docs/metadata only: never starts CUBRID (checked first, so a recipe README
# change does not start that recipe's live suite).
DOCS = (
    "*.md",
    "docs/*",
    "LICENSE",
    "NOTICE",
    "llms.txt",
    "mkdocs.yml",
    "*.gif",
    ".github/ISSUE_TEMPLATE/*",
)
# Changing the CI policy itself runs every lane so the change is self-tested.
SELF = (
    ".github/workflows/ci.yml",
    ".github/actions/*",
    "scripts/ci_scope.py",
    "tests/test_ci_scope.py",
)
# The release smoke workflow and the driver-selection code the PR smoke lane
# shares with it: both CUBRID smoke lanes, every golden.
RELEASE_SMOKE = (
    ".github/workflows/smoke-test.yml",
    "scripts/release_smoke.py",
    "scripts/mcp_smoke.py",
)
# Where the documented driver floors live (#241): the support contract, its
# checker, the floor lane, and the requirements of every directory the lane runs
# (scripts/driver_floors.py FLOOR_SETS; tests/test_dependency_floors.py keeps them in
# sync). Any floor change elsewhere must also edit SUPPORT_MATRIX.md or the
# checker, which selects the lane. Matched before DOCS.
FLOORS = (
    "SUPPORT_MATRIX.md",
    "scripts/check_dependency_floors.py",
    "scripts/driver_floors.py",
    "fundamentals/alembic/requirements.txt",
    "fundamentals/async/requirements.txt",
    "fundamentals/connect/requirements.txt",
    "fundamentals/json/requirements.txt",
    "fundamentals/orm-basics/requirements.txt",
    "fundamentals/pandas/requirements.txt",
    "fundamentals/pycubrid/requirements.txt",
    "fundamentals/sqlalchemy/requirements.txt",
    "migration/java-to-python/requirements.txt",
    "pitfalls/reserved-words/requirements.txt",
    "quickstart/5min-sqlalchemy/requirements.txt",
)
# Shared live infrastructure every live suite depends on: fan out to all of
# them, both CUBRID versions and the Python endpoints.
SHARED_LIVE = (
    "Makefile",
    "docker-compose.yml",
    ".env.example",
    "scripts/normalize_output.sh",
    "scripts/wait_for_cubrid.py",
    "scripts/check_expected_coverage.py",
    "scripts/verify_exclusions.txt",
)
# Python compatibility surface: the two goldens the compatibility lane runs.
COMPAT = ("fundamentals/pycubrid/*", "fundamentals/sqlalchemy/*")
# Recipe families with their own live pytest job (CQRS is matched first).
FAMILIES = (
    ("cqrs", (f"{CQRS_ROOT}/*",)),
    ("web", ("templates/flask/*", "templates/api-service-fastapi/*")),
    ("dashboard", ("templates/dashboard/*",)),
    ("async_worker", ("templates/async-worker/*",)),
    ("django", ("templates/django/*",)),
)
# AI-agent examples run inside the smoke lane (no expected/ goldens).
AI_AGENT = ("templates/ai-agent/*", "tests/test_ai_agent.py")
# Example directories with no live consumer (no goldens, no live suite); the
# offline checks cover them. Other files in example trees outside a golden root
# (e.g. a shared helper) fail closed to a full 11.4 verify.
NO_LIVE_CONSUMER = (
    "performance/*",
    "quickstart/5min-fastapi/*",
    "fundamentals/parameterized-queries/*",
)
EXAMPLE_TREES = (
    "fundamentals/*",
    "migration/*",
    "pitfalls/*",
    "quickstart/*",
    "templates/batch-etl/*",
)
# Offline tooling and metadata covered by the always-on cheap checks.
TOOLING = (
    "scripts/*",
    "tests/*",
    ".github/*",
    "demos/*",
    ".gitignore",
    "pyproject.toml",
)
# Same allowlist the former smoke-test.yml PR scoping used: no spaces or shell
# metacharacters reach $GITHUB_OUTPUT, make or find.
SAFE_ROOT = re.compile(r"[A-Za-z0-9._/-]+")


def _match(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def example_roots(root: Path) -> list[str]:
    """Directories that own an ``expected/`` folder (``make verify`` targets)."""
    roots = set()
    for expected in root.rglob("expected"):
        rel = expected.relative_to(root)
        if not expected.is_dir() or rel.parts[0] in {".git", "node_modules"}:
            continue
        if "node_modules" in rel.parts:
            continue
        roots.add(rel.parent.as_posix())
    return sorted(roots)


def classify(event: str, paths: Iterable[str], roots: Iterable[str]) -> dict[str, object]:
    files = sorted({p.strip() for p in paths if p.strip()})
    roots = sorted(roots)
    lanes = dict.fromkeys(
        ("web", "dashboard", "async_worker", "django", "cqrs", "compat", "smoke_114", "floors"),
        False,
    )
    full = broad = cqrs_dual = smoke_112 = full_verify = False
    verify = set()

    if event in MAIN_EVENTS:
        return {
            "tier": "main",
            "web": False,
            "dashboard": False,
            "async_worker": False,
            "django": False,
            "cqrs": True,
            "cqrs_cubrid": CUBRID_ENDPOINTS,
            "compat": True,
            "python": PYTHON_ALL,
            "smoke_114": False,
            "smoke_112": False,
            "verify_paths": "",
            "floors": event in FLOOR_EVENTS,
        }
    if event not in PR_EVENTS or not files:
        full = True  # unknown event or an unexpected empty diff: fail closed

    for path in files:
        if _match(path, FLOORS):
            lanes["floors"] = True
        if _match(path, DOCS):
            continue
        if _match(path, SELF):
            full = True
            continue
        if _match(path, RELEASE_SMOKE):
            lanes["smoke_114"] = smoke_112 = full_verify = True
            continue
        if _match(path, SHARED_LIVE):
            broad = True
            continue
        if _match(path, COMPAT):
            lanes["compat"] = True
        root = next((r for r in roots if path.startswith(f"{r}/")), None)
        if root is not None:
            lanes["smoke_114"] = True
            if SAFE_ROOT.fullmatch(root):
                verify.add(root)
            else:
                full_verify = True
        family = next((name for name, pats in FAMILIES if _match(path, pats)), None)
        if family is not None:
            lanes[family] = True
            if path == f"{CQRS_ROOT}/requirements.txt":
                cqrs_dual = True
        elif _match(path, AI_AGENT):
            lanes["smoke_114"] = full_verify = True
        elif root is not None or _match(path, COMPAT + NO_LIVE_CONSUMER + TOOLING):
            pass
        elif _match(path, EXAMPLE_TREES):
            # Outside every golden root, e.g. a helper goldens may import.
            lanes["smoke_114"] = full_verify = True
        else:
            # Unknown path: every PR lane on the representative versions.
            for name in ("web", "dashboard", "async_worker", "django", "cqrs", "smoke_114"):
                lanes[name] = True
            full_verify = True

    if broad or full:
        lanes = dict.fromkeys(lanes, True)
        cqrs_dual = smoke_112 = full_verify = True
    if full:
        tier = "full"
    elif any(lanes.values()):
        tier = "pr"
    else:
        tier = "docs"

    # CI-policy and shared-infrastructure PRs get the endpoints; 3.11-3.14 run
    # on the broad events above.
    if full or broad or lanes["compat"]:
        python = PYTHON_ENDPOINTS
    else:
        python = [REPRESENTATIVE_PYTHON]

    if not lanes["smoke_114"]:
        verify_paths = ""
    elif full_verify or not verify:
        verify_paths = "."
    else:
        verify_paths = " ".join(sorted(verify))

    return {
        "tier": tier,
        "web": lanes["web"],
        "dashboard": lanes["dashboard"],
        "async_worker": lanes["async_worker"],
        "django": lanes["django"],
        "cqrs": lanes["cqrs"],
        "cqrs_cubrid": CUBRID_ENDPOINTS if cqrs_dual else DEFAULT_CUBRID,
        "compat": lanes["compat"],
        "python": python,
        "smoke_114": lanes["smoke_114"],
        "smoke_112": smoke_112,
        "verify_paths": verify_paths,
        "floors": lanes["floors"],
    }


def render(scope: dict[str, object]) -> str:
    lines = []
    for key, value in scope.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, list):
            value = json.dumps(value, separators=(",", ":"))
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify CI validation lanes (#222)")
    parser.add_argument("--event", required=True, help="github.event_name")
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root")
    args = parser.parse_args(argv)
    roots = example_roots(args.root)
    sys.stdout.write(render(classify(args.event, sys.stdin.read().splitlines(), roots)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
