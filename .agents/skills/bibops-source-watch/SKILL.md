---
name: bibops-source-watch
description: Monitor conference source catalogs for newly available accepted/proceedings metadata and trigger intake runs with deterministic diff reporting.
---

Use this when you need a timely watch loop for ICLR/NeurIPS/ICML publication windows.

## Execute

1. Run catalog discovery on watched years:
   - `python3 scripts/bibops.py intake discover iclr:2025 neurips:2025 icml:2025 --json`
2. Run non-writing reconciliation to detect drift:
   - `python3 scripts/bibops.py intake plan iclr:2025 neurips:2025 icml:2025 --json`
3. If plan shows missing/extra deltas, run write mode:
   - `python3 scripts/bibops.py intake run iclr:2025 neurips:2025 icml:2025 --write --fail-on-gap --json`
4. Record unresolved triage artifacts and stop on blockers.

## Constraints

- Never treat zero unresolved as the sole success metric; validate that source counts are plausible for each venue.
- Keep source cache healthy (`ops/intake-source-cache.json`) and rely on built-in retry/backoff behavior.
- Prefer small, frequent runs over large delayed catch-up batches during active announcement windows.

