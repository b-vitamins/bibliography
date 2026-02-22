---
name: bibops-year-intake
description: Bootstrap complete conference-year bibliography files from canonical venue catalogs, reconcile with local files, and write deterministic BibTeX with fail-closed completeness checks.
---

Use this when a new year is announced and you need `conferences/<venue>/<year>.bib` generated or refreshed reliably.

## Execute

1. Discover source availability first:
   - `python3 scripts/bibops.py intake discover iclr:2025 neurips:2025 icml:2025 --json`
2. Plan reconciliation without writes:
   - `python3 scripts/bibops.py intake plan iclr:2025 neurips:2025 icml:2025 --json`
3. Apply writes with strict gap checks:
   - `python3 scripts/bibops.py intake run iclr:2025 neurips:2025 icml:2025 --write --fail-on-gap --json`
4. Enrich newly written files:
   - `python3 scripts/bibops.py enrich run conferences/iclr/2025.bib conferences/neurips/2025.bib conferences/icml/2025.bib --write --fail-on-unresolved --json`
5. Finish with quality gate:
   - `python3 scripts/bibops.py lint`

## Constraints

- Prefer canonical venue sources over derived mirrors.
- Treat `missing/extra/duplicate/invalid` counts as blockers until triaged.
- Keep runs traceable via `ops/intake-runs/`, `ops/intake-snapshots/`, and `ops/unresolved/intake/`.
- Do not hand-edit large generated year files before running intake + enrichment.

## Configuration

- Default config: `ops/intake-pipeline.toml`
- Report output: `ops/intake-runs/`
- Snapshot output: `ops/intake-snapshots/`
- Unresolved queue: `ops/unresolved/intake/`

