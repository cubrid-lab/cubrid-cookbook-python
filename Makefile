SHELL := /bin/bash
.PHONY: help up down status docker-clean clean deps verify verify-goldens demo lint format-check format \
	test test-offline check check-docs test-normalize check-coverage docs docs-check agent-eval-check \
	verify-quickstart verify-performance verify-web verify-django-celery verify-ai-agent verify-dashboard verify-templates

DOCKER_COMPOSE := docker compose
NORMALIZE := bash scripts/normalize_output.sh
PYTHON := python3
PIP := $(PYTHON) -m pip
RUFF := ruff
UP_TIMEOUT ?= 120
UP_PROBE_TIMEOUT ?= 5
UP_INTERVAL ?= 2

# Search roots for `make verify-goldens`. Defaults to the whole tree; CI narrows this
# to only the changed example directories on pull requests (see scripts/ci_scope.py).
VERIFY_PATHS ?= .
# Wall-clock limit in seconds for each verified script (scripts/run_example.py).
# The slowest golden took 7.2s on CUBRID 11.4 (2026-10-09); 60s leaves room for
# slower CI runners without letting a hang consume the job timeout.
VERIFY_TIMEOUT ?= 60
# make verify and the verify-* lanes (scripts/live_gate.py) fail closed by default:
# CUBRID_TEST_URL and CUBRID_DASHBOARD_TEST_URL must name dedicated, empty
# cubrid+pycubrid databases. CUBRID_LIVE_GATE=0 restores the suites' own skips
# and SQLite fallbacks for local exploration (never a PASS).
CUBRID_LIVE_GATE ?= 1
LIVE_GATE = CUBRID_LIVE_GATE=$(CUBRID_LIVE_GATE) $(PYTHON) scripts/live_gate.py

help: ## Show this help, grouped by purpose
	@awk 'BEGIN {FS = ":.*?## "} \
		/^##@ / {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
		/^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Database (local CUBRID lab, docker-compose.yml)

up: ## Start CUBRID database
	$(DOCKER_COMPOSE) up -d
	@echo "Waiting for CUBRID to be ready..."
	$(PYTHON) scripts/wait_for_cubrid.py --compose "$(DOCKER_COMPOSE)" \
		--timeout $(UP_TIMEOUT) --probe-timeout $(UP_PROBE_TIMEOUT) --interval $(UP_INTERVAL)

down: ## Stop CUBRID database (keeps its data)
	$(DOCKER_COMPOSE) down

status: ## Show container status
	$(DOCKER_COMPOSE) ps

docker-clean: ## DESTRUCTIVE: stop CUBRID and delete its containers and volumes, including all database data
	$(DOCKER_COMPOSE) down -v
	@echo "✓ Removed the CUBRID containers and volumes"

##@ Setup and cleanup

deps: ## Install the drivers, pytest, pytest-asyncio and every example's requirements, all that make verify needs (one pip call; honours PIP_CONSTRAINT)
	@set -f; \
	files=$$($(PYTHON) scripts/example_requirements.py --all) || exit 1; \
	if [ -z "$$files" ]; then \
		echo "ERROR: No example requirements.txt found; run make deps from the repository root" >&2; \
		exit 1; \
	fi; \
	set --; for file in $$files; do set -- "$$@" -r "$$file"; done; \
	echo "$(PIP) install pytest pytest-asyncio 'sqlalchemy-cubrid[pycubrid]' $$*"; \
	$(PIP) install pytest pytest-asyncio 'sqlalchemy-cubrid[pycubrid]' "$$@"

clean: ## Remove generated files, caches and test results (never Docker containers, volumes or data)
	$(PYTHON) -B -c 'import sys; sys.path.insert(0, "scripts"); from pathlib import Path; from stage_docs import STAGE; [Path(page).unlink(missing_ok=True) for _, page in STAGE]'
	rm -rf .live-evidence site .pytest_cache .ruff_cache
	find . \( -path ./.git -o -path ./.venv -o -path ./venv \) -prune -o \
		-type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune \
		-exec rm -rf {} +

##@ Offline tests (no database, no Docker)

test: ## Run every offline suite, each in its own process (suite list: scripts/run_offline_tests.py)
	$(PYTHON) scripts/run_offline_tests.py

test-offline: test ## Alias of make test

test-normalize: ## Run before/after unit checks for scripts/normalize_output.sh (also part of make test)
	bash scripts/test_normalize_output.sh

agent-eval-check: ## Validate the agent-evals tasks and re-grade their fixtures (offline; no model, no DB)
	$(PYTHON) scripts/agent_eval.py validate
	$(PYTHON) scripts/agent_eval.py check

##@ Live verification (needs CUBRID, see CONTRIBUTING.md "Live verification")

# `make verify` is always the full live verification (scripts/live_gate.py all),
# always gated: an ambient CUBRID_LIVE_GATE=0 cannot turn it into a skip-tolerant
# run, and an exported VERIFY_PATHS does not narrow it. VERIFY_PATHS named on the
# command line is refused: the partial golden check is make verify-goldens (#437).
verify: ## Full live verification: every golden plus every live pytest suite, fail-closed
ifeq ($(origin VERIFY_PATHS),command line)
	@echo "ERROR: make verify always runs the full verification and takes no VERIFY_PATHS; for the partial golden check run: make verify-goldens VERIFY_PATHS=$(VERIFY_PATHS)" >&2; exit 2
endif
	CUBRID_LIVE_GATE=1 $(PYTHON) scripts/live_gate.py --gate all

verify-goldens: check-coverage ## Compare example outputs with their goldens (VERIFY_PATHS=<dirs> scopes the search roots, a partial check; VERIFY_TIMEOUT limits each script)
	@PYTHON="$(PYTHON)" NORMALIZE="$(NORMALIZE)" VERIFY_TIMEOUT="$(VERIFY_TIMEOUT)" bash scripts/verify_goldens.sh $(VERIFY_PATHS)

verify-quickstart: ## Live lane: FastAPI quickstart /health and CRUD on the make up database
	$(LIVE_GATE) quickstart

verify-performance: ## Live lane: 5 migration goldens + 3 benchmarks on the make up database
	$(LIVE_GATE) performance

verify-web: ## Live lane: Flask/FastAPI template suites on CUBRID_TEST_URL
	$(LIVE_GATE) web

verify-django-celery: ## Live lane: Django bridge and direct Celery task suites on CUBRID_TEST_URL
	$(LIVE_GATE) django-celery

verify-ai-agent: ## Live lane: AI agent state, MCP and RAG suite on CUBRID_TEST_URL
	$(LIVE_GATE) ai-agent

verify-dashboard: ## Live lane: dashboard AppTest suite on an isolated CUBRID_DASHBOARD_TEST_URL
	$(LIVE_GATE) dashboard

verify-templates: ## Live lanes: verify-web, verify-django-celery and verify-dashboard in order
	$(LIVE_GATE) web django-celery dashboard

demo: up verify-goldens ## Demo: start DB, compare every example with its golden
	@echo ""
	@echo "✓ Demo complete — all examples verified against CUBRID"

##@ Quality checks (no tests; make check test is the full offline gate)

check: lint format-check check-docs check-coverage ## Non-test quality gate: lint, format-check, check-docs, check-coverage

lint: ## Ruff lint check (does not modify files)
	$(RUFF) check .

format-check: ## Ruff formatting check (does not modify files)
	$(RUFF) format --check .

format: ## Apply Ruff lint fixes and formatting (the only target that rewrites source files)
	$(RUFF) check --fix .
	$(RUFF) format .

check-docs: ## Check documentation coverage and its doctests
	$(PYTHON) -m doctest scripts/check_docs_reason.py -v
	$(PYTHON) -m unittest discover -s tests -p 'test_docs_reason.py' -v
	$(PYTHON) -m doctest scripts/check_docs_sync.py -v
	$(PYTHON) -m unittest discover -s tests -p 'test_docs_sync.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_translation_sync.py' -v
	$(PYTHON) -m doctest scripts/stage_docs.py -v
	$(PYTHON) -m unittest discover -s tests -p 'test_stage_docs.py' -v
	$(PYTHON) scripts/check_docs_sync.py
	$(PYTHON) scripts/check_support_matrix_counts.py
	$(PYTHON) scripts/check_dependency_floors.py
	$(PYTHON) -m unittest discover -s tests -p 'test_lint_changelog.py' -v
	$(PYTHON) scripts/lint_changelog.py

check-coverage: ## Fail if any opted-in example script lacks an .expected golden
	$(PYTHON) scripts/check_expected_coverage.py

##@ Documentation

docs-check: ## Check Markdown links, anchors, fences and recipe commands (needs .github/requirements-docs-check.txt)
	$(PYTHON) -m pytest tests/test_check_docs_links.py -q
	$(PYTHON) scripts/check_docs_links.py

docs: ## Stage repo docs into docs/ and build the site locally (strict)
	bash scripts/stage_docs.sh
	mkdocs build --strict
