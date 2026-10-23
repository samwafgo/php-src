#!/bin/bash
# PHP 5.6 的 run-tests.php 不支持 -j 并行,用列表切分手动并行。
# 用法: bash tests/run-parallel.sh [并行度,默认3] [目录...]
# 必须在 php-src 源码树根目录、已完成编译后运行。
set -u
JOBS="${1:-3}"; shift 2>/dev/null || shift $#
DIRS=("$@"); [ ${#DIRS[@]} -eq 0 ] && DIRS=(Zend/tests ext/session/tests tests/basic)

export NO_INTERACTION=1 SKIP_SLOW_TESTS=1 SKIP_ONLINE_TESTS=1
export TEST_PHP_EXECUTABLE="$PWD/sapi/cli/php"

LIST=$(mktemp)
find "${DIRS[@]}" -name '*.phpt' | sort > "$LIST"
TOTAL=$(wc -l < "$LIST")
echo "[*] $TOTAL 个用例, $JOBS 路并行..."

split -n "l/$JOBS" -d "$LIST" /tmp/rt_chunk_
PIDS=()
for c in /tmp/rt_chunk_*; do
    sapi/cli/php run-tests.php -l "$c" > "$c.log" 2>&1 &
    PIDS+=($!)
done
for p in "${PIDS[@]}"; do wait "$p"; done

echo "==== 汇总 ===="
grep -hE "^Tests (failed|warned|passed|skipped)" /tmp/rt_chunk_*.log
echo "==== 失败明细 ===="
grep -h "^\[" /tmp/rt_chunk_*.log 2>/dev/null | sort -u || true
sed -n '/FAILED TEST SUMMARY/,/^====*$/p' /tmp/rt_chunk_*.log | grep -oE '\[[^]]+\]' | sort -u
