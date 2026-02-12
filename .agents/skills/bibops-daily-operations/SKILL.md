---
name: bibops-daily-operations
description: Run the repository's daily bibliography operations profile and triage results. Use when asked to check repo health, run routine maintenance, or produce a fast quality status across managed bibliography collections.
---

Run the daily operations workflow through the unified control plane.

## Execute

1. Run `scripts/run_daily.sh` from repository root.
2. Read the latest lint report and summarize by severity and issue type.
3. Prioritize fixes in this order: parse errors, missing required fields, duplicate keys, key format, placeholder authors.
4. Re-run `scripts/run_daily.sh` after fixes to confirm improvement.

## Constraints

- Use default config scope (`ops/bibops.toml`) for routine runs.
- Use full scope only when explicitly requested.
- Report run ID in summaries so results are traceable.
