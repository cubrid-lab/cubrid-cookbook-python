SHELL := /bin/bash
.PHONY: help up down status clean verify demo test-normalize

DOCKER_COMPOSE := docker compose
NORMALIZE := bash scripts/normalize_output.sh
PYTHON := python3

# Search roots for `make verify`. Defaults to the whole tree; CI narrows this to
# only the changed example directories on pull requests (see smoke-test.yml).
VERIFY_PATHS ?= .

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start CUBRID database
	$(DOCKER_COMPOSE) up -d
	@echo "Waiting for CUBRID to be ready..."
	@until $(DOCKER_COMPOSE) exec -T cubrid csql -u dba testdb -c "SELECT 1" > /dev/null 2>&1; do \
		sleep 2; \
	done
	@echo "✓ CUBRID is ready at localhost:33000"

down: ## Stop CUBRID database
	$(DOCKER_COMPOSE) down

status: ## Show container status
	$(DOCKER_COMPOSE) ps

clean: ## Stop and remove all data
	$(DOCKER_COMPOSE) down -v
	@echo "✓ Cleaned up all containers and volumes"

verify: ## Verify example outputs against expected results (VERIFY_PATHS scopes the search roots)
	@echo "Verifying example outputs in: $(VERIFY_PATHS)"
	@PASS=0; FAIL=0; SKIP=0; \
	for expected in $$(find $(VERIFY_PATHS) -path '*/expected/*.expected' | sort); do \
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
		expected_content=$$(cat "$$expected"); \
		if [ "$$actual" = "$$expected_content" ]; then \
			echo "  ✓ PASS $$script"; \
			PASS=$$((PASS + 1)); \
		else \
			echo "  ✗ FAIL $$script"; \
			diff <(echo "$$actual") <(echo "$$expected_content") || true; \
			FAIL=$$((FAIL + 1)); \
		fi; \
	done; \
	echo ""; \
	echo "Results: $$PASS passed, $$FAIL failed, $$SKIP skipped"; \
	[ "$$FAIL" -eq 0 ]

test-normalize: ## Run before/after unit checks for scripts/normalize_output.sh
	bash scripts/test_normalize_output.sh

demo: up verify ## Full demo: start DB, verify all examples
	@echo ""
	@echo "✓ Demo complete — all examples verified against CUBRID"
