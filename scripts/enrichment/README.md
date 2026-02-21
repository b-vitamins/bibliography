# Enrichment Package (`scripts/enrichment`)

This package implements a modular metadata enrichment pipeline with venue-specific source adapters and explicit provenance.

## CLI

- Plan candidates: `python3 scripts/enrich-pipeline.py plan <file.bib>`
- Run dry mode: `python3 scripts/enrich-pipeline.py run <file.bib>`
- Apply approved updates: `python3 scripts/enrich-pipeline.py run <file.bib> --write`

Or through `bibops`:

- `python3 scripts/bibops.py enrich plan <file.bib>`
- `python3 scripts/bibops.py enrich run <file.bib>`

## Current adapters

- `openreview`: extracts canonical OpenReview metadata for ICLR-style entries.
- `neurips_proceedings`: extracts canonical NeurIPS proceedings metadata.

## Outputs

- Run report JSON: `ops/enrichment-runs/`
- Unresolved triage queue JSONL: `ops/unresolved/enrichment/`
- HTTP response cache: `ops/enrichment-source-cache.json`

## Battle Testing

Run systematic workload and surface checks:

- `python3 scripts/enrichment/battle_test.py --mode quick`
- `python3 scripts/enrichment/battle_test.py --mode standard`
- `python3 scripts/enrichment/battle_test.py --mode stress`

## Configuration

Default config path: `ops/enrichment-pipeline.toml`

It controls:

- target fields by entry type
- protected fields
- venue-to-adapter mapping
- domain allowlists
- operational output locations
