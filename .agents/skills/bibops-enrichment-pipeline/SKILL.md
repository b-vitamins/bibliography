---
name: bibops-enrichment-pipeline
description: Run the modular enrichment pipeline with source adapters, provenance-aware validation, and triage-first handling for unresolved entries.
---

Use this when enriching conference bibliographies at scale while preserving source integrity.

## Execute

1. Plan candidate updates: `python3 scripts/enrich-pipeline.py plan <file.bib> --out ops/enrichment-plan.json`.
2. Execute dry run first: `python3 scripts/enrich-pipeline.py run <file.bib> --fail-on-unresolved`.
3. Review unresolved queue in `ops/unresolved/enrichment/` and resolve conflicts entry-by-entry.
4. Apply approved updates with write mode: `python3 scripts/enrich-pipeline.py run <file.bib> --write`.
5. Finish with `python3 scripts/bibops.py lint`.

## Constraints

- Prefer canonical venue sources (OpenReview, official proceedings) over inferred summaries.
- Do not overwrite protected identity fields (`author`, `title`, `booktitle`, `year`) unless policy is explicitly changed.
- Treat unresolved entries as triage items, never as silent pass/fail noise.

## Configuration

- Default config: `ops/enrichment-pipeline.toml`
- Report output: `ops/enrichment-runs/`
- Unresolved queue: `ops/unresolved/enrichment/`
