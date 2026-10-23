#!/usr/bin/env bash
# Run PHP 5.6 PHPT tests in parallel, keeping logs and checking unexpected failures.
# Usage: from a built PHP source directory:
#   bash /work/tests/run-parallel.sh 2 Zend/tests ext/session/tests tests/basic
set -euo pipefail

JOBS="${1:-2}"
if (($#)); then shift; fi
if ! [[ "$JOBS" =~ ^[1-9][0-9]*$ ]]; then
  echo "Invalid parallel job count: $JOBS" >&2; exit 2
fi
DIRS=("$@")
if ((${#DIRS[@]} == 0)); then DIRS=(Zend/tests ext/session/tests tests/basic); fi

export NO_INTERACTION=1 SKIP_SLOW_TESTS=1 SKIP_ONLINE_TESTS=1
export TEST_PHP_EXECUTABLE="$PWD/sapi/cli/php"

LOG_DIR="$PWD/ci-test-logs"
mkdir -p "$LOG_DIR"
find "${DIRS[@]}" -type f -name '*.phpt' | sort > "$LOG_DIR/all.list"
TOTAL=$(wc -l < "$LOG_DIR/all.list")
if ((TOTAL == 0)); then echo "No test cases found" >&2; exit 2; fi
if ((JOBS > TOTAL)); then JOBS=$TOTAL; fi
split --numeric-suffixes=0 -n "l/$JOBS" "$LOG_DIR/all.list" "$LOG_DIR/batch-"
echo "Running $TOTAL PHPT cases in $JOBS batches"

pids=()
for list in "$LOG_DIR"/batch-[0-9]*; do
  "$TEST_PHP_EXECUTABLE" run-tests.php -l "$list" > "$list.log" 2>&1 &
  pids+=("$!")
done

had_exit_error=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then had_exit_error=1; fi
done

# PHP 5.6's runner prints failures in the FAILED TEST SUMMARY section.
: > "$LOG_DIR/actual-failures.txt"
for log in "$LOG_DIR"/batch-[0-9]*.log; do
  if ! grep -q 'TEST RESULT SUMMARY' "$log"; then
    echo "Incomplete/aborted test run: $log" >&2
    tail -40 "$log" >&2
    exit 1
  fi
  awk '/FAILED TEST SUMMARY/{in_fails=1; next} in_fails && /^=/{in_fails=0} in_fails{print}' "$log" |
    grep -oE '\[(Zend|ext|tests)/[^]]+\.phpt\]' >> "$LOG_DIR/actual-failures.txt" || true
done
sort -u -o "$LOG_DIR/actual-failures.txt" "$LOG_DIR/actual-failures.txt"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED="${EXPECTED_FAILURES_FILE:-$SCRIPT_DIR/expected-failures.txt}"
if [[ ! -f "$EXPECTED" ]]; then
  echo "Expected failure list not found: $EXPECTED" >&2; exit 2
fi
sort -u "$EXPECTED" > "$LOG_DIR/expected-failures-sorted.txt"
comm -23 "$LOG_DIR/actual-failures.txt" "$LOG_DIR/expected-failures-sorted.txt" > "$LOG_DIR/unexpected-failures.txt"
comm -13 "$LOG_DIR/actual-failures.txt" "$LOG_DIR/expected-failures-sorted.txt" > "$LOG_DIR/expected-but-passing.txt"

echo '==== Actual failures ===='
cat "$LOG_DIR/actual-failures.txt"
echo '==== Unexpected failures ===='
cat "$LOG_DIR/unexpected-failures.txt"
echo '==== Previously expected but now passing ===='
cat "$LOG_DIR/expected-but-passing.txt"
if [[ -s "$LOG_DIR/unexpected-failures.txt" ]]; then exit 1; fi
if ((had_exit_error)); then
  # A nonzero runner exit is normal for known failures, but no recorded failures
  # means an infrastructure error rather than an expected PHPT failure.
  if [[ ! -s "$LOG_DIR/actual-failures.txt" ]]; then
    echo 'One or more test runners failed without any PHPT failure summary' >&2
    exit 1
  fi
fi
echo 'PHPT test matrix completed without unexpected failures.'
