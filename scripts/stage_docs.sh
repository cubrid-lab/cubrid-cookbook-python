#!/usr/bin/env bash
# Stage repo docs into docs/ for the mkdocs site. Sources of truth stay at
# their repo locations; run before `mkdocs build` (CI docs.yml and `make docs`).

set -euo pipefail
cd "$(dirname "$0")/.."

stage() {
  src="$1"; dst="$2"
  if [ -f "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
  else
    echo "stage-docs: missing $src — skipping" >&2
  fi
}

stage README.md                                  docs/catalog.md
stage GETTING_STARTED.md                         docs/getting-started.md
stage SUPPORT_MATRIX.md                          docs/support-matrix.md
stage KNOWN_ISSUES.md                            docs/known-issues.md
stage CHANGELOG.md                               docs/changelog.md
stage fundamentals/README.md                     docs/fundamentals.md
stage fundamentals/pycubrid/README.md            docs/fundamentals-pycubrid.md
stage fundamentals/sqlalchemy/README.md          docs/fundamentals-sqlalchemy.md
stage fundamentals/pandas/README.md              docs/fundamentals-pandas.md
stage fundamentals/parameterized-queries/README.md docs/fundamentals-parameterized-queries.md
stage performance/README.md                      docs/performance.md
stage pitfalls/README.md                         docs/pitfalls.md
stage templates/api-service-fastapi/README.md    docs/template-api-service-fastapi.md
stage templates/async-worker/README.md           docs/template-async-worker.md
stage templates/batch-etl/README.md              docs/template-batch-etl.md
stage templates/dashboard/README.md              docs/template-dashboard.md
stage templates/django/README.md                 docs/template-django.md
stage templates/flask/README.md                  docs/template-flask.md
