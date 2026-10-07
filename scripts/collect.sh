#!/bin/bash
# collect.sh <file-name> [outdir] [timeout-seconds]
# Waits for a file saved by Chrome (download dir or wherever the user saved it from the
# "Save as" dialog), then moves it into outdir. Prints "SAVED: <path> (<w>x<h>)".
set -uo pipefail
NAME=${1:?usage: collect.sh <file-name> [outdir] [timeout]}
OUT=${2:-"$HOME/Pictures/AI生图"}
TIMEOUT=${3:-300}
mkdir -p "$OUT" || exit 2

DIRS=("$HOME/Downloads" "$HOME/Documents" "$HOME/Desktop")
for pref in "$HOME/Library/Application Support/Google/Chrome/"*/Preferences; do
  d=$(grep -o '"default_directory":"[^"]*"' "$pref" 2>/dev/null | head -1 | cut -d'"' -f4)
  [ -n "$d" ] && DIRS=("$d" "${DIRS[@]}")
done

waited=0
while [ "$waited" -lt "$TIMEOUT" ]; do
  for d in "${DIRS[@]}"; do
    f="$d/$NAME"
    # skip while Chrome is still writing (.crdownload sibling present)
    if [ -f "$f" ] && [ ! -e "$f.crdownload" ]; then
      dest="$OUT/$NAME"; i=1
      while [ -e "$dest" ]; do dest="$OUT/${NAME%.*}_$i.${NAME##*.}"; i=$((i+1)); done
      mv "$f" "$dest" || exit 1
      echo "SAVED: $dest ($(sips -g pixelWidth -g pixelHeight "$dest" 2>/dev/null | awk '/pixel/{print $2}' | paste -sd x -))"
      exit 0
    fi
  done
  sleep 2; waited=$((waited+2))
done
echo "ERROR: $NAME not found after ${TIMEOUT}s in: ${DIRS[*]} (did the Save dialog get confirmed?)" >&2
exit 1
