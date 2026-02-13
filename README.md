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
make release
make full-audit
```

## Operational config

- Default config: `ops/bibops.toml`
- Full config: `ops/bibops-full.toml`
- Orals subset config: `ops/bibops-orals.toml`

Default scope is tuned for speed and active curation:
- `books/`, `conferences/`, `curated/`, `references/`, `courses/`, `theses/`, `presentations/`

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

These are designed with progressive disclosure and can be invoked explicitly or implicitly by task match.

## Data and state

- Bibliography files live across domain folders (`books/`, `conferences/`, `curated/`, etc.).
- Derived oral subsets live in `collections/orals/<venue>/<year>.bib`.
- Local operational state and enrichment tracking use `bibliography.db`.
- Version-controlled tracking snapshot is `tracking.json`.

`bibops` stores run metadata and issue snapshots in `ops_*` tables inside `bibliography.db`.

## Legacy scripts

Existing scripts in `scripts/` remain available for specialized operations (enrichment, PDF sync, key updates, etc.).

Use `bibops` for orchestration and health checks; use specialized scripts for targeted actions.
