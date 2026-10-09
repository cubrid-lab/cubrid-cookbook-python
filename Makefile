SHELL := /bin/bash
.PHONY: help up down status clean deps verify demo lint test-offline check check-docs test-normalize check-coverage docs

DOCKER_COMPOSE := docker compose
NORMALIZE := bash scripts/normalize_output.sh
PYTHON := python3
PIP := $(PYTHON) -m pip
RUFF := ruff
UP_TIMEOUT ?= 120
UP_PROBE_TIMEOUT ?= 5
UP_INTERVAL ?= 2

# Search roots for `make verify`. Defaults to the whole tree; CI narrows this to
# only the changed example directories on pull requests (see scripts/ci_scope.py).
VERIFY_PATHS ?= .
# Wall-clock limit in seconds for each verified script (scripts/run_example.py).
# The slowest golden took 7.2s on CUBRID 11.4 (2026-10-09); 60s leaves room for
# slower CI runners without letting a hang consume the job timeout.
VERIFY_TIMEOUT ?= 60

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start CUBRID database
	$(DOCKER_COMPOSE) up -d
	@echo "Waiting for CUBRID to be ready..."
	$(PYTHON) scripts/wait_for_cubrid.py --compose "$(DOCKER_COMPOSE)" \
		--timeout $(UP_TIMEOUT) --probe-timeout $(UP_PROBE_TIMEOUT) --interval $(UP_INTERVAL)

down: ## Stop CUBRID database
	$(DOCKER_COMPOSE) down

status: ## Show container status
	$(DOCKER_COMPOSE) ps

clean: ## Stop and remove all data
	$(DOCKER_COMPOSE) down -v
	@echo "✓ Cleaned up all containers and volumes"

deps: ## Install the drivers, pytest and every golden-backed example's requirements (one pip call; honours PIP_CONSTRAINT)
	@set -f; \
	files=$$($(PYTHON) scripts/example_requirements.py) || exit 1; \
	if [ -z "$$files" ]; then \
		echo "ERROR: No golden-backed requirements.txt found; run make deps from the repository root" >&2; \
		exit 1; \
	fi; \
	set --; for file in $$files; do set -- "$$@" -r "$$file"; done; \
	echo "$(PIP) install pytest 'sqlalchemy-cubrid[pycubrid]' $$*"; \
	$(PIP) install pytest 'sqlalchemy-cubrid[pycubrid]' "$$@"

verify: check-coverage ## Verify example outputs against expected results (VERIFY_PATHS scopes the search roots, VERIFY_TIMEOUT limits each script)
	@echo "Verifying example outputs in: $(VERIFY_PATHS) (timeout $(VERIFY_TIMEOUT)s per script)"
	@set -o pipefail; \
	roots=( $(VERIFY_PATHS) ); \
	if [ "$${#roots[@]}" -eq 0 ]; then echo "ERROR: VERIFY_PATHS must name a directory" >&2; exit 1; fi; \
	for root in "$${roots[@]}"; do \
		if [ ! -d "$$root" ]; then echo "ERROR: Verify root is not a directory: $$root" >&2; exit 1; fi; \
	done; \
	$(PYTHON) scripts/example_requirements.py --check "$${roots[@]}" || exit 1; \
	if ! expected_files=$$(find "$${roots[@]}" -path '*/expected/*.expected' | sort); then \
		echo "ERROR: Golden discovery failed" >&2; exit 1; \
	fi; \
	if [ -z "$$expected_files" ]; then echo "ERROR: No golden targets found" >&2; exit 1; fi; \
	raw=$$(mktemp "$${TMPDIR:-/tmp}/verify.XXXXXX") || exit 1; \
	trap 'rm -f "$$raw"' EXIT; \
	annotate() { \
		if [ -n "$$GITHUB_ACTIONS" ]; then echo "::error file=$${2#./},title=make verify $$1::$$3"; fi; \
	}; \
	PASS=0; MISMATCH=0; EXEC=0; TIMEOUT=0; NORMALIZE=0; READ=0; SKIP=0; \
	while IFS= read -r expected; do \
		dir=$$(dirname "$$(dirname "$$expected")"); \
		base=$$(basename "$$expected" .expected); \
		script="$$dir/$$base.py"; \
		if [ ! -f "$$script" ]; then \
			echo "  ? SKIP $$expected (no matching script)"; \
			SKIP=$$((SKIP + 1)); \
			continue; \
		fi; \
		$(PYTHON) scripts/run_example.py --timeout $(VERIFY_TIMEOUT) -- $(PYTHON) "$$script" < /dev/null > "$$raw" 2>&1; \
		status=$$?; \
		last=$$(tail -n 1 "$$raw"); \
		if [ $$status -eq 124 ] && [ "$${last#run_example: timed out after }" != "$$last" ]; then \
			echo "  ⏱ TIMEOUT $$script (over $(VERIFY_TIMEOUT)s); last 20 lines:"; \
			tail -n 20 "$$raw" | sed 's/^/      /'; \
			annotate TIMEOUT "$$script" "exceeded VERIFY_TIMEOUT=$(VERIFY_TIMEOUT)s"; \
			TIMEOUT=$$((TIMEOUT + 1)); \
			continue; \
		fi; \
		if [ $$status -ne 0 ]; then \
			echo "  ✗ EXEC-ERROR $$script (exit $$status); last 20 lines:"; \
			tail -n 20 "$$raw" | sed 's/^/      /'; \
			annotate EXEC-ERROR "$$script" "script exited with status $$status"; \
			EXEC=$$((EXEC + 1)); \
			continue; \
		fi; \
		if ! actual=$$($(NORMALIZE) < "$$raw"); then \
			echo "  ✗ NORMALIZE-ERROR $$script (output normalizer failed)"; \
			annotate NORMALIZE-ERROR "$$script" "output normalizer failed"; \
			NORMALIZE=$$((NORMALIZE + 1)); \
			continue; \
		fi; \
		if ! expected_content=$$(cat "$$expected"); then \
			echo "  ✗ READ-ERROR $$expected (golden read error)"; \
			annotate READ-ERROR "$$expected" "golden read error"; \
			READ=$$((READ + 1)); \
			continue; \
		fi; \
		if [ "$$actual" = "$$expected_content" ]; then \
			echo "  ✓ PASS $$script"; \
			PASS=$$((PASS + 1)); \
		else \
			echo "  ✗ MISMATCH $$script"; \
			diff <(echo "$$actual") <(echo "$$expected_content") || true; \
			annotate MISMATCH "$$script" "output differs from $$expected"; \
			MISMATCH=$$((MISMATCH + 1)); \
		fi; \
	done <<< "$$expected_files"; \
	FAIL=$$((MISMATCH + EXEC + TIMEOUT + NORMALIZE + READ)); \
	echo ""; \
	echo "Results: $$PASS passed, $$FAIL failed, $$SKIP skipped" \
		"($$MISMATCH mismatch, $$EXEC exec-error, $$TIMEOUT timeout," \
		"$$NORMALIZE normalize-error, $$READ read-error)"; \
	[ "$$PASS" -gt 0 ] && [ "$$FAIL" -eq 0 ] && [ "$$SKIP" -eq 0 ]

lint: ## Check Python lint and formatting
	$(RUFF) check .
	$(RUFF) format --check .

test-offline: ## Run mocked/offline suites in separate processes (no database required)
	$(PYTHON) -m pytest quickstart/5min-fastapi/tests -q
	$(PYTHON) -m pytest tests/test_ai_agent_offline.py -q
	$(PYTHON) -m unittest discover -s tests -p 'test_release*.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_make_commands.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_wait_for_cubrid.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_support_matrix_counts.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_dependency_floors.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_dependabot_config.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_third_party_licenses.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_pr_title.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_ci_scope.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_workflow_timeouts.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_workflow_permissions.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_template_timestamps.py' -v

check-docs: ## Check documentation coverage and its doctests
	$(PYTHON) -m doctest scripts/check_docs_reason.py -v
	$(PYTHON) -m unittest discover -s tests -p 'test_docs_reason.py' -v
	$(PYTHON) -m doctest scripts/check_docs_sync.py -v
	$(PYTHON) -m unittest discover -s tests -p 'test_docs_sync.py' -v
	$(PYTHON) -m doctest scripts/stage_docs.py -v
	$(PYTHON) -m unittest discover -s tests -p 'test_stage_docs.py' -v
	$(PYTHON) scripts/check_docs_sync.py
	$(PYTHON) scripts/check_support_matrix_counts.py
	$(PYTHON) scripts/check_dependency_floors.py

check: lint test-offline check-docs check-coverage test-normalize ## Run offline contributor checks

test-normalize: ## Run before/after unit checks for scripts/normalize_output.sh
	bash scripts/test_normalize_output.sh

check-coverage: ## Fail if any opted-in example script lacks an .expected golden
	$(PYTHON) scripts/check_expected_coverage.py

demo: up verify ## Full demo: start DB, verify all examples
	@echo ""
	@echo "✓ Demo complete — all examples verified against CUBRID"

docs: ## Stage repo docs into docs/ and build the site locally (strict)
	bash scripts/stage_docs.sh
	mkdocs build --strict
