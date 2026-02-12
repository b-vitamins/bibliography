#!/usr/bin/env bash
set -euo pipefail

python3 scripts/bibops.py run-profile --profile ops/profiles/daily.toml
python3 scripts/bibops.py report
