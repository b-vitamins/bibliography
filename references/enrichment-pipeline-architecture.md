# Enrichment Pipeline Architecture

## Objective

Build a long-lived, source-grounded enrichment pipeline that improves metadata completeness while preserving bibliographic integrity.

The pipeline must:

- Prefer canonical venue sources over heuristic enrichment.
- Keep provenance for every injected field.
- Separate policy decisions from source connectors.
- Route uncertain cases into explicit triage queues instead of silent mutation.
- Support repeated runs across new years and new venues without rewriting core logic.

## Design Basis

This design follows the additive and extension-oriented approach described in *Software Design for Flexibility* (Hanson and Sussman, MIT Press):

- Separate stable mechanisms from variable policy.
- Use generic interfaces so new behavior is added by extension, not surgery.
- Compose simple layers (planning, source retrieval, validation, application) rather than one monolith.

Reference:

- https://mitpress.mit.edu/9780262545491/software-design-for-flexibility/

## Architecture Overview

The implementation is a staged pipeline with explicit artifacts:

1. `plan`: identify candidate entries and missing/target fields.
2. `retrieve`: fetch canonical metadata through venue/source adapters.
3. `validate`: enforce source-domain, field-shape, and confidence rules.
4. `apply`: mutate only approved fields and record provenance.
5. `report`: emit run summary + unresolved triage queue.

Each stage has stable interfaces and independent outputs so failures are observable and resumable.

## Core Modules

- `scripts/enrichment/models.py`
  - Shared dataclasses (`WorkItem`, `SourceRecord`, `FieldProposal`, `EntryDecision`).
- `scripts/enrichment/config.py`
  - TOML-backed runtime policy and venue mapping.
- `scripts/enrichment/bibtex_io.py`
  - Parse/update/write BibTeX files deterministically.
- `scripts/enrichment/http_client.py`
  - Retry, timeout, and host-throttled HTTP retrieval.
- `scripts/enrichment/sources/`
  - Adapter interface + source implementations (`openreview`, `neurips`).
- `scripts/enrichment/engine.py`
  - Orchestration for `plan` and `run`, provider dispatch, triage/report emission.
- `scripts/enrich-pipeline.py`
  - CLI for repeatable operations.

## Stable Interfaces

### Source Adapter Contract

Each source adapter implements:

- `name`: stable identifier.
- `supports(file_path, entry) -> bool`: applicability.
- `fetch(entry, context) -> SourceRecord | None`: return canonical metadata.

`SourceRecord` fields are normalized, provenance-tagged, and limited to source-authoritative data.

### Policy Contract

Policy is externalized in `ops/enrichment-pipeline.toml`:

- venue path matching to adapter names.
- field targets by entry type.
- overwrite behavior and protected fields.
- domain allowlists per venue.
- cache/report/triage output paths.

This isolates repository policy from algorithmic code.

## Integrity Controls

### Provenance

Every proposed field includes:

- source adapter name
- source URL
- fetch timestamp
- value fingerprint (sha256)

This allows post-hoc audits and reproducibility checks.

### Guardrails

- Do not overwrite protected bibliographic identity fields by default (`author`, `title`, `booktitle`, `year`).
- Reject URL/PDF values from domains outside venue allowlist.
- Reject empty/trivial abstracts.
- Mark conflicts as unresolved instead of forced updates.

### Triage-First Failure Mode

Any entry with unresolved conflicts is written to a queue file under `ops/unresolved/enrichment/` with machine-readable reasons.

### Resilience and Source Safety

- Shared HTTP layer enforces polite host pacing and adaptive backoff.
- Host pacing can be tuned per domain so conservative sources and bulk proceedings
  mirrors are handled with different request cadences.
- Source fetches use adapter-level content validation (`require_any`/`reject_any`) so error pages are not mistaken for canonical records.
- Rate-limit/challenge pages are treated as poisoned payloads:
  - not accepted as source data,
  - not persisted into cache,
  - purged from existing cache snapshots on load/access.
- Run reports include HTTP diagnostics to support post-run audits.

## Extension Strategy

### Add a New Venue

1. Add venue mapping in `ops/enrichment-pipeline.toml`.
2. Implement a new adapter under `scripts/enrichment/sources/`.
3. Register adapter in the source registry.
4. Run `plan` and `run` in dry mode first.

No core pipeline changes required.

### Add New Fields

1. Add field in policy targets.
2. Extend `SourceRecord` extraction in relevant adapters.
3. Add field-level validation rule if needed.

Again, no control-flow rewrites.

## Operating Model

Recommended execution sequence:

1. `python3 scripts/enrich-pipeline.py plan <file.bib>`
2. `python3 scripts/enrich-pipeline.py run <file.bib> --report <path>`
3. Review triage queue and resolve unresolved entries.
4. Re-run `run` until unresolved queue is empty or explicitly accepted.
5. Finish with `python3 scripts/bibops.py lint`.

## Why This Is Better Than Prior Passes

Compared to large monolithic enrichment commits, this architecture:

- distinguishes canonical extraction from heuristic mutation.
- prevents silent degradation hidden behind aggregate metrics.
- captures evidence for each field-level mutation.
- supports incremental, venue-specific improvements over years.
