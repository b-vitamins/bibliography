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
- `neurips_proceedings`: extracts canonical NeurIPS proceedings metadata, including
  a stale-URL recovery path via yearly proceedings index lookup (hash first, then title match).

## Outputs

- Run report JSON: `ops/enrichment-runs/`
- Unresolved triage queue JSONL: `ops/unresolved/enrichment/`
- HTTP response cache: `ops/enrichment-source-cache.json`

## Resilience Guarantees

- Host-level politeness throttling (`host_min_interval_seconds`).
- Retry/backoff for transport and content-validation failures.
- Rate-limit awareness via `Retry-After` and body hints (e.g., "try again in N seconds").
- Poison-cache defense: known throttling/challenge pages are never reused as valid source payloads.
- Automatic cache hygiene: poisoned rows are purged on load and invalidated on access.

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
