# AGENTS.md

This repository is managed by Codex through a **skills-first, command-first** workflow.

## Operating Model

### Primary control plane
Use `scripts/bibops.py` as the default orchestrator for repo health and repeatable operations.

Core commands:
- `python3 scripts/bibops.py doctor`
- `python3 scripts/bibops.py scan`
- `python3 scripts/bibops.py lint`
- `python3 scripts/bibops.py report`
- `python3 scripts/bibops.py pdf-sync <file.bib|glob ...> --pdf-sync-policy ops/pdf-sync-policy.toml [--fail-on-error]`
- `python3 scripts/bibops.py key-normalize <file.bib|glob ...> [--write] [--fail-on-issues]`
- `python3 scripts/bibops.py intake discover <venue:year> [more targets...]`
- `python3 scripts/bibops.py intake plan <venue:year> [more targets...]`
- `python3 scripts/bibops.py intake run <venue:year> [more targets...] --write --fail-on-gap`
- `python3 scripts/bibops.py run-profile --profile ops/profiles/intake-watch.toml`
- `python3 scripts/bibops.py run-profile --profile ops/profiles/daily.toml`
- `python3 scripts/bibops.py run-profile --profile ops/profiles/release.toml`
- `python3 scripts/bibops.py --config ops/bibops-full.toml run-profile --profile ops/profiles/full-audit.toml`

Convenience targets:
- `make doctor`
- `make lint`
- `make daily`
- `make pdf-sync TARGETS='conferences/iclr/2025.bib'`
- `make key-normalize TARGETS='conferences/iclr/2025.bib'`
- `make release`
- `make full-audit`

## Repository invariants

1. BibTeX must parse cleanly for managed files.
2. Keys should follow lowercase alnum `<author><year><keyword>` convention.
3. `inproceedings` entries must include `author`, `title`, `booktitle`, `year`.
4. Placeholder authors like `and others` are not acceptable in managed collection results.
5. Large operations should be profile-driven and repeatable.
6. `collections/orals/` is a derived subset layer; canonical source remains `conferences/`.
7. File-level repository metadata resolves via `meta/bibmeta.toml`; active files should prefer path-derived semantics over inline `@COMMENT{bibmeta: ...}` preambles.

## Scope tiers

### Daily managed scope (fast)
Default `ops/bibops.toml` scope:
- `books/`
- `conferences/`
- `collections/`
- `references/`
- `courses/`
- `theses/`
- `presentations/`

### Full archive scope (slow)
`ops/bibops-full.toml` includes `journals/` for periodic deep audits.

## Standard workflows

### 1) Daily health pass
1. `make daily`
2. If issues exist, fix highest-severity classes first.
3. Re-run `make lint` until acceptable.

### 2) Release pass
1. `make release`
2. Ensure hooks are installed and tracking export is current.
3. Commit only intentional changes.

### 3) Full audit
1. `make full-audit`
2. Use for periodic deep cleanup, not per-change development.

### 4) Oral subset validation
1. `make orals`
2. Keep oral files under `collections/orals/<venue>/<year>.bib`.
3. Run `verify-orals` to enforce canonical alignment (where canonical year files exist) and required `url`/`pdf` fields.

## Skills-first execution

Repository skills live under `.agents/skills`.

Codex should prefer these over ad-hoc behavior when tasks match:
- `bibops-daily-operations`
- `bibops-entry-curation`
- `bibops-quality-gate`
- `bibops-release-manager`
- `bibops-enrichment-pipeline`
- `bibops-year-intake`
- `bibops-source-watch`

If new capability is needed:
1. Create/update a skill in `.agents/skills`.
2. Keep it narrow and procedural.
3. Put reusable code in `scripts/`, deep docs in `references/`, templates in `assets/`.

For external skill onboarding, use `skill-installer` workflow instead of manual copying.

## Commit policy

Use conventional commit types enforced by hook:
- `feat`, `enhance`, `fix`, `refactor`, `doc/docs`, `chore`, `cleanup`, `test`, `style`

Commit in milestones:
1. Control-plane or infra changes.
2. Workflow/policy changes.
3. Data curation changes.

Keep commits scoped so each can be reasoned about independently.

## Legacy note

`CLAUDE.md` is deprecated and replaced by this file.
