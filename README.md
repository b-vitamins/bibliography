# Bibliography Infrastructure v2

This repository manages a large BibTeX corpus with a **single operations control plane** and a **skills-first AI workflow**.

## What changed

- Replaced ad-hoc operational flow with `scripts/bibops.py`.
- Added declarative operation profiles under `ops/profiles/`.
- Added repository-native skills under `.agents/skills/`.
- Replaced legacy manager instructions (`CLAUDE.md`) with `AGENTS.md`.

## Core principles

1. One command surface for repeatability.
2. Deterministic quality checks and traceable run IDs.
3. Small daily scope + explicit full-audit scope.
4. Skills as reusable operational policy.

## Quick start

```bash
# Health check
python3 scripts/bibops.py doctor

# Daily maintenance profile
python3 scripts/bibops.py run-profile --profile ops/profiles/daily.toml

# Oral subset validation profile
python3 scripts/bibops.py --config ops/bibops-orals.toml run-profile --profile ops/profiles/orals.toml

# Enrich oral subsets with arXiv IDs (keeps existing url/pdf untouched)
python3 scripts/bibops.py enrich run collections/orals/*/*.bib --enrichment-config ops/enrichment-arxiv.toml --write --fail-on-unresolved

# Semantic Scholar-mode enrichment for BibTeX quality fields (author/doi/abstract/note/etc.)
python3 scripts/bibops.py enrich run conferences/neurips/2025.bib --enrichment-config ops/enrichment-semanticscholar.toml --write

# Plan venue-grounded enrichment for a conference file
python3 scripts/enrich-pipeline.py plan conferences/iclr/2024.bib

# Run enrichment in dry mode (writes report + unresolved queue)
python3 scripts/enrich-pipeline.py run conferences/iclr/2024.bib

# Synchronize/download local PDFs for a target bibliography
python3 scripts/bibops.py pdf-sync conferences/iclr/2025.bib \
  --pdf-sync-policy ops/pdf-sync-policy.toml \
  --fail-on-error

# Preview a long-run workload without writes/downloads
python3 scripts/bibops.py pdf-sync conferences/aistats/2024.bib \
  --pdf-sync-policy ops/pdf-sync-policy.toml \
  --dry-run --max-entries 500

# Battle-test enrichment pipeline behavior on real workloads
python3 scripts/enrichment/battle_test.py --mode standard

# Release profile (hooks + lint + tracking export)
python3 scripts/bibops.py run-profile --profile ops/profiles/release.toml

# Full archive audit (includes journals/)
python3 scripts/bibops.py --config ops/bibops-full.toml run-profile --profile ops/profiles/full-audit.toml
```

Or use `make` shortcuts:

```bash
make doctor
make daily
make orals
make enrich-arxiv-orals
make enrich-battle
make pdf-sync TARGETS='conferences/iclr/2025.bib'
make release
make full-audit
```

## Operational config

- Default config: `ops/bibops.toml`
- Full config: `ops/bibops-full.toml`
- Orals subset config: `ops/bibops-orals.toml`

Default scope is tuned for speed and active curation:
- `books/`, `conferences/`, `collections/`, `references/`, `courses/`, `theses/`, `presentations/`

Full scope additionally includes:
- `journals/`

Orals scope (subset verification) includes:
- `collections/orals/`

## Skills

Repository skills are in `.agents/skills/`:

- `bibops-daily-operations`
- `bibops-entry-curation`
- `bibops-quality-gate`
- `bibops-release-manager`
- `bibops-enrichment-pipeline`

These are designed with progressive disclosure and can be invoked explicitly or implicitly by task match.

## Data and state

- Bibliography files live across domain folders (`books/`, `conferences/`, `collections/`, etc.).
- Derived oral subsets live in `collections/orals/<venue>/<year>.bib`.
- Local operational state and enrichment tracking use `bibliography.db`.
- Version-controlled tracking snapshot is `tracking.json`.

Hook behavior:
- `pre-commit` tracking export is opt-in (`BIBOPS_AUTO_EXPORT_TRACKING=1`).
- Default commits do not auto-rewrite `tracking.json`.

`bibops` stores run metadata and issue snapshots in `ops_*` tables inside `bibliography.db`.

## Legacy scripts

Existing scripts in `scripts/` remain available for specialized operations (enrichment, export, key updates, etc.).

Use `bibops` for orchestration and health checks; use specialized scripts for targeted actions.
