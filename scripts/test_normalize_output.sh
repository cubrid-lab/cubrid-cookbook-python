#!/usr/bin/env bash
# Unit-style before/after checks for scripts/normalize_output.sh.
#
# Each case feeds a raw line through the normalizer and asserts the expected
# normalized result. This locks in the presentation-only rules (timing, path,
# memory, ratio) and guards against a rule accidentally scrubbing meaningful
# data (SQL text, row contents, exception class, ordering).
#
# Usage: bash scripts/test_normalize_output.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NORMALIZE="bash ${SCRIPT_DIR}/normalize_output.sh"

fail_count=0

# assert <name> <raw-input> <expected-output>
assert() {
  local name="$1" raw="$2" want="$3" got
  got="$(printf '%s\n' "$raw" | ${NORMALIZE})"
  if [ "$got" = "$want" ]; then
    printf 'ok   - %s\n' "$name"
  else
    printf 'FAIL - %s\n      raw:  %s\n      want: %s\n      got:  %s\n' \
      "$name" "$raw" "$want" "$got"
    fail_count=$((fail_count + 1))
  fi
}

# --- Rules that SHOULD normalize (dynamic noise) ---
assert "timing seconds (float)" \
  "Report generated in 1.234 seconds" \
  "Report generated in {{TIME}}s"
assert "timing seconds (int)" \
  "Report generated in 5 seconds" \
  "Report generated in {{TIME}}s"
assert "absolute export path" \
  "CSV exported to: /home/runner/work/repo/fundamentals/pandas/sales.csv" \
  "CSV exported to: {{PATH}}/sales.csv"
assert "tracemalloc peak memory" \
  "  fetch_size=   10  peak_memory=   123.4 KB" \
  "  fetch_size=   10  peak_memory={{MEM}} KB"
assert "peak memory ratio" \
  "Peak memory ratio (largest / smallest): 12.3x" \
  "Peak memory ratio (largest / smallest): {{RATIO}}x"

# --- Guardrail: rules must NOT touch meaningful data ---
assert "keeps SQL text" \
  "Executing: SELECT id, name FROM users WHERE age > 30" \
  "Executing: SELECT id, name FROM users WHERE age > 30"
assert "keeps row contents / ids" \
  "Row: (1, 'Alice', 30)" \
  "Row: (1, 'Alice', 30)"
assert "keeps exception class" \
  "IntegrityError: UNIQUE violation" \
  "IntegrityError: UNIQUE violation"
assert "keeps static byte sizes" \
  "  icon.bin        (256 bytes)" \
  "  icon.bin        (256 bytes)"

if [ "$fail_count" -ne 0 ]; then
  printf '\n%d check(s) failed\n' "$fail_count"
  exit 1
fi
printf '\nAll normalize checks passed\n'
