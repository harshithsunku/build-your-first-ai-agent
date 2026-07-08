#!/usr/bin/env bash
# Benchmark: gtags (GNU Global) indexed lookups vs plain grep on a large C tree.
#
# Usage: ./benchmark.sh /path/to/large/c/project [symbol ...]
#
# Builds the gtags index (timed), then for each symbol compares:
#   grep -rn <symbol>   — full-tree scan, every textual occurrence
#   global -x <symbol>  — indexed definition lookup
#   global -rx <symbol> — indexed reference lookup
set -euo pipefail

TREE="${1:?usage: benchmark.sh /path/to/project [symbol ...]}"
shift
SYMBOLS=("${@:-tcp_v4_rcv}")

cd "$TREE"

now() { date +%s.%N; }
elapsed() { echo "$2 - $1" | bc; }

echo "== Tree stats =="
FILES=$(find . -name '*.[chS]' -o -name '*.cpp' -o -name '*.cc' -o -name '*.hpp' | wc -l)
LINES=$(find . -name '*.[ch]' -print0 | xargs -0 cat 2>/dev/null | wc -l)
echo "C/C++ source files: $FILES"
echo "Lines in .c/.h:     $LINES"
echo

if [ ! -f GTAGS ]; then
  echo "== One-time index build (gtags) =="
  t0=$(now); gtags; t1=$(now)
  printf "index build time: %.1fs\n" "$(elapsed "$t0" "$t1")"
  du -sh GTAGS GRTAGS GPATH | sed 's/^/index size:      /'
  echo
fi

printf "%-16s %-22s %10s %8s\n" "symbol" "method" "time(s)" "lines"
printf "%-16s %-22s %10s %8s\n" "------" "------" "-------" "-----"
for sym in "${SYMBOLS[@]}"; do
  t0=$(now); g_lines=$(grep -rn --include='*.[ch]' "$sym" . | wc -l); t1=$(now)
  printf "%-16s %-22s %10.2f %8s\n" "$sym" "grep -rn (scan)" "$(elapsed "$t0" "$t1")" "$g_lines"

  t0=$(now); d_lines=$(global -x "$sym" | wc -l); t1=$(now)
  printf "%-16s %-22s %10.2f %8s\n" "$sym" "global -x (definition)" "$(elapsed "$t0" "$t1")" "$d_lines"

  t0=$(now); r_lines=$(global -rx "$sym" | wc -l); t1=$(now)
  printf "%-16s %-22s %10.2f %8s\n" "$sym" "global -rx (references)" "$(elapsed "$t0" "$t1")" "$r_lines"
done
