#!/usr/bin/env bash
set -euo pipefail

python3 scripts/bibops.py doctor
python3 scripts/bibops.py lint --fail-on-error
python3 scripts/bibops.py report
