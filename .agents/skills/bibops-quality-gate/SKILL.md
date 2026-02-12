---
name: bibops-quality-gate
description: Enforce pre-commit and pre-merge quality gates for bibliography infrastructure and data. Use when asked to verify readiness, run strict checks, or block commits until quality criteria are met.
---

Run deterministic quality gates before commit/merge.

## Execute

1. Run `scripts/run_gate.sh`.
2. If the gate fails, report failing classes first and list concrete fix targets.
3. Re-run the gate after changes until pass.

## Gate policy

- Fail on error-severity lint issues.
- Surface warnings as follow-up debt, not hard blockers.
- Always include the lint run ID in gate output.
