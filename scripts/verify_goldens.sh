#!/usr/bin/env bash
# Golden-output comparison behind `make verify-goldens`, and so behind the goldens
# lane of the full `make verify` (scripts/live_gate.py). Moved out of the Makefile
# recipe without behavior changes (#437).
#
# Usage: bash scripts/verify_goldens.sh ROOT [ROOT ...]
#
# Every ROOT/**/expected/NAME.expected golden is compared with the normalized
# output of the sibling NAME.py script. Environment:
#   PYTHON          interpreter for the scripts and helpers (default: python3)
#   NORMALIZE       output normalizer command (default: bash scripts/normalize_output.sh)
#   VERIFY_TIMEOUT  wall-clock limit in seconds per script (default: 60)
#   VERIFY_RESULTS  optional file that receives one STATUS<TAB>target line per
#                   golden; scripts/live_gate.py reads it
#   GITHUB_ACTIONS  when set, failures are also printed as ::error annotations
#
# One line per golden (PASS, MISMATCH, EXEC-ERROR, TIMEOUT, NORMALIZE-ERROR,
# READ-ERROR or SKIP), then "Results: P passed, F failed, S skipped (...)", which
# scripts/agent_eval.py also parses. Exits 0 only when at least one golden passed
# and none failed or was skipped. Run it from the repository root.

set -o pipefail

PYTHON=${PYTHON:-python3}
NORMALIZE=${NORMALIZE:-bash scripts/normalize_output.sh}
VERIFY_TIMEOUT=${VERIFY_TIMEOUT:-60}

echo "Verifying example outputs in: $* (timeout ${VERIFY_TIMEOUT}s per script)"
roots=( "$@" )
if [ "${#roots[@]}" -eq 0 ]; then echo "ERROR: VERIFY_PATHS must name a directory" >&2; exit 1; fi
for root in "${roots[@]}"; do
	if [ ! -d "$root" ]; then echo "ERROR: Verify root is not a directory: $root" >&2; exit 1; fi
done
$PYTHON scripts/example_requirements.py --check "${roots[@]}" || exit 1
if ! expected_files=$(find "${roots[@]}" -path '*/expected/*.expected' | sort); then
	echo "ERROR: Golden discovery failed" >&2; exit 1
fi
if [ -z "$expected_files" ]; then echo "ERROR: No golden targets found" >&2; exit 1; fi
raw=$(mktemp "${TMPDIR:-/tmp}/verify.XXXXXX") || exit 1
trap 'rm -f "$raw"' EXIT

annotate() {
	if [ -n "$GITHUB_ACTIONS" ]; then echo "::error file=${2#./},title=make verify $1::$3"; fi
}
record() {
	if [ -n "${VERIFY_RESULTS:-}" ]; then printf '%s\t%s\n' "$1" "$2" >> "$VERIFY_RESULTS"; fi
}

PASS=0; MISMATCH=0; EXEC=0; TIMEOUT=0; NORMALIZE_ERRORS=0; READ=0; SKIP=0
while IFS= read -r expected; do
	dir=$(dirname "$(dirname "$expected")")
	base=$(basename "$expected" .expected)
	script="$dir/$base.py"
	if [ ! -f "$script" ]; then
		echo "  ? SKIP $expected (no matching script)"
		record SKIP "$expected"
		SKIP=$((SKIP + 1))
		continue
	fi
	$PYTHON scripts/run_example.py --timeout "$VERIFY_TIMEOUT" -- $PYTHON "$script" < /dev/null > "$raw" 2>&1
	status=$?
	last=$(tail -n 1 "$raw")
	if [ $status -eq 124 ] && [ "${last#run_example: timed out after }" != "$last" ]; then
		echo "  ⏱ TIMEOUT $script (over ${VERIFY_TIMEOUT}s); last 20 lines:"
		tail -n 20 "$raw" | sed 's/^/      /'
		annotate TIMEOUT "$script" "exceeded VERIFY_TIMEOUT=${VERIFY_TIMEOUT}s"
		record TIMEOUT "$script"
		TIMEOUT=$((TIMEOUT + 1))
		continue
	fi
	if [ $status -ne 0 ]; then
		echo "  ✗ EXEC-ERROR $script (exit $status); last 20 lines:"
		tail -n 20 "$raw" | sed 's/^/      /'
		annotate EXEC-ERROR "$script" "script exited with status $status"
		record EXEC-ERROR "$script"
		EXEC=$((EXEC + 1))
		continue
	fi
	if ! actual=$($NORMALIZE < "$raw"); then
		echo "  ✗ NORMALIZE-ERROR $script (output normalizer failed)"
		annotate NORMALIZE-ERROR "$script" "output normalizer failed"
		record NORMALIZE-ERROR "$script"
		NORMALIZE_ERRORS=$((NORMALIZE_ERRORS + 1))
		continue
	fi
	if ! expected_content=$(cat "$expected"); then
		echo "  ✗ READ-ERROR $expected (golden read error)"
		annotate READ-ERROR "$expected" "golden read error"
		record READ-ERROR "$expected"
		READ=$((READ + 1))
		continue
	fi
	if [ "$actual" = "$expected_content" ]; then
		echo "  ✓ PASS $script"
		record PASS "$script"
		PASS=$((PASS + 1))
	else
		echo "  ✗ MISMATCH $script"
		diff <(echo "$actual") <(echo "$expected_content") || true
		annotate MISMATCH "$script" "output differs from $expected"
		record MISMATCH "$script"
		MISMATCH=$((MISMATCH + 1))
	fi
done <<< "$expected_files"

FAIL=$((MISMATCH + EXEC + TIMEOUT + NORMALIZE_ERRORS + READ))
echo ""
echo "Results: $PASS passed, $FAIL failed, $SKIP skipped" \
	"($MISMATCH mismatch, $EXEC exec-error, $TIMEOUT timeout," \
	"$NORMALIZE_ERRORS normalize-error, $READ read-error)"
[ "$PASS" -gt 0 ] && [ "$FAIL" -eq 0 ] && [ "$SKIP" -eq 0 ]
