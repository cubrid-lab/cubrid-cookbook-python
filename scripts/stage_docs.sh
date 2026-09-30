#!/usr/bin/env bash
# Stage repo docs into docs/ for the mkdocs site. Sources of truth stay at
# their repo locations; run before `mkdocs build` (CI docs.yml and `make docs`).
# The staging list and the relative-link rewriting live in stage_docs.py.

set -euo pipefail
exec python3 "$(dirname "$0")/stage_docs.py" "$@"
