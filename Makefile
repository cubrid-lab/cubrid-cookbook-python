SHELL := /bin/bash
.PHONY: help up down status clean verify demo lint test-offline check check-docs test-normalize check-coverage docs

DOCKER_COMPOSE := docker compose
NORMALIZE := bash scripts/normalize_output.sh
PYTHON := python3
RUFF := ruff
UP_TIMEOUT ?= 120
UP_PROBE_TIMEOUT ?= 5
UP_INTERVAL ?= 2

# Search roots for `make verify`. Defaults to the whole tree; CI narrows this to
# only the changed example directories on pull requests (see scripts/ci_scope.py).
VERIFY_PATHS ?= .

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

verify: check-coverage ## Verify example outputs against expected results (VERIFY_PATHS scopes the search roots)
	@echo "Verifying example outputs in: $(VERIFY_PATHS)"
	@set -o pipefail; \
	roots=( $(VERIFY_PATHS) ); \
	if [ "$${#roots[@]}" -eq 0 ]; then echo "ERROR: VERIFY_PATHS must name a directory" >&2; exit 1; fi; \
	for root in "$${roots[@]}"; do \
		if [ ! -d "$$root" ]; then echo "ERROR: Verify root is not a directory: $$root" >&2; exit 1; fi; \
	done; \
	if ! expected_files=$$(find "$${roots[@]}" -path '*/expected/*.expected' | sort); then \
		echo "ERROR: Golden discovery failed" >&2; exit 1; \
	fi; \
	if [ -z "$$expected_files" ]; then echo "ERROR: No golden targets found" >&2; exit 1; fi; \
	PASS=0; FAIL=0; SKIP=0; \
	while IFS= read -r expected; do \
		dir=$$(dirname "$$(dirname "$$expected")"); \
		base=$$(basename "$$expected" .expected); \
		script="$$dir/$$base.py"; \
		if [ ! -f "$$script" ]; then \
			echo "  ? SKIP $$expected (no matching script)"; \
			SKIP=$$((SKIP + 1)); \
			continue; \
		fi; \
		actual=$$(set -o pipefail; $(PYTHON) "$$script" 2>&1 | $(NORMALIZE)); \
		if [ $$? -ne 0 ]; then \
			echo "  ✗ FAIL $$script (script error)"; \
			FAIL=$$((FAIL + 1)); \
			continue; \
		fi; \
		if ! expected_content=$$(cat "$$expected"); then \
			echo "  ✗ FAIL $$expected (golden read error)"; FAIL=$$((FAIL + 1)); continue; \
		fi; \
		if [ "$$actual" = "$$expected_content" ]; then \
			echo "  ✓ PASS $$script"; \
			PASS=$$((PASS + 1)); \
		else \
			echo "  ✗ FAIL $$script"; \
			diff <(echo "$$actual") <(echo "$$expected_content") || true; \
			FAIL=$$((FAIL + 1)); \
		fi; \
	done <<< "$$expected_files"; \
	echo ""; \
	echo "Results: $$PASS passed, $$FAIL failed, $$SKIP skipped"; \
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
