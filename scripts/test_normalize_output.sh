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
assert "datetime with microseconds (space sep)" \
  "  order_no=1000 created_at_utc=2026-08-26 11:03:13.052000 total=10" \
  "  order_no=1000 created_at_utc={{DATETIME}} total=10"
assert "datetime on a whole second, zero-padded milliseconds (#189)" \
  "  sku=SKU-100  name=Keyboard  last_seen_utc=2026-08-26 11:03:13.000" \
  "  sku=SKU-100  name=Keyboard  last_seen_utc={{DATETIME}}"
for sep_name in "space:" "T:T"; do
  sep_label="${sep_name%%:*}"; sep="${sep_name#*:}"; sep="${sep:- }"
  assert "datetime whole second, no fraction (${sep_label} sep)" \
    "  at=2026-08-26${sep}11:03:13 end" "  at={{DATETIME}} end"
  assert "datetime milliseconds (${sep_label} sep)" \
    "  at=2026-08-26${sep}11:03:13.052 end" "  at={{DATETIME}} end"
  assert "datetime microseconds (${sep_label} sep)" \
    "  at=2026-08-26${sep}11:03:13.052000 end" "  at={{DATETIME}} end"
done
assert "keeps fixed whole-second zone-name value" \
  "  ts=2026-01-15 10:30:00 Asia/Seoul" "  ts={{DATE}} 10:30:00 Asia/Seoul"
assert "keeps fixed whole-second UTC-name value" \
  "  ts=2026-01-15 10:30:00 UTC" "  ts={{DATE}} 10:30:00 UTC"
assert "keeps whole-second Z-suffixed value" \
  "  ts=2026-01-15T10:30:00Z" "  ts={{DATE}}T10:30:00Z"
assert "datetime whole second at end of line" \
  "  at=2026-08-26 11:03:13" "  at={{DATETIME}}"
assert "logging comma-fraction stays TIMESTAMP" \
  "2026-08-26 11:03:13,052 INFO x" "{{TIMESTAMP}} INFO x"
assert "bulk-insert perf: execute(insert, rows)" \
  "execute(insert, rows): 0.0664s" \
  "execute(insert, rows): {{TIME}}s"
assert "bulk-insert perf: add_all" \
  "add_all: 0.4805s" \
  "add_all: {{TIME}}s"
assert "pandas string dtype -> canonical object (product_name)" \
  "product_name          str" \
  "product_name object"
assert "pandas string dtype -> canonical object (category_name)" \
  "category_name         string[python]" \
  "category_name object"
assert "pandas object dtype canonicalized to single space" \
  "product_name        object" \
  "product_name object"
assert "pandas int64 dtype line canonicalized (product_id)" \
  "product_id           int64" \
  "product_id int64"
assert "pandas int64 dtype line canonicalized (is_active)" \
  "is_active            int64" \
  "is_active int64"

# --- Guardrail: rules must NOT touch meaningful data ---
assert "keeps plain date followed by text" \
  "Date: 2026-08-26 is a Wednesday" \
  "Date: {{DATE}} is a Wednesday"
assert "keeps HH:MM:SS duration without a date" \
  "elapsed 01:02:03 total" \
  "elapsed 01:02:03 total"
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
assert "does not touch str outside dtypes columns" \
  "result str: hello world" \
  "result str: hello world"
assert "keeps non-01 dtype column unchanged (not column-anchored)" \
  "quantity            int64" \
  "quantity            int64"
assert "keeps a bare whole-second time with no fractional part (meaningful, e.g. a fixed timezone-demo timestamp)" \
  "  id=1 seoul-launch tz=2026-01-15 10:30:00+09:00" \
  "  id=1 seoul-launch tz={{DATE}} 10:30:00+09:00"

if [ "$fail_count" -ne 0 ]; then
  printf '\n%d check(s) failed\n' "$fail_count"
  exit 1
fi
printf '\nAll normalize checks passed\n'
