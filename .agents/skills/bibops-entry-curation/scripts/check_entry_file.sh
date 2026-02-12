#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: check_entry_file.sh <file.bib> [more files...]" >&2
  exit 2
fi

python3 scripts/verify-bib.py "$@"
python3 scripts/check-bibkey-format.py "$@"

bad=0
for f in "$@"; do
  if rg -n "and others|others\}" "$f" >/dev/null 2>&1; then
    echo "placeholder author detected in $f" >&2
    bad=1
  fi
done

if [ "$bad" -ne 0 ]; then
  exit 3
fi
