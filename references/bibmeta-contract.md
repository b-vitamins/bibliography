# Bibmeta Contract

`bibmeta` is the bibliography repository's neutral file-level metadata contract.

It exists to classify `.bib` files by repository role and to expose the small
amount of file-level metadata that cannot be recovered from BibTeX entries
alone. It is owned by this repository and intentionally does not mention any
consumer application.

## Design goals

- Path structure is the default metadata carrier.
- File-level metadata is resolved from a single manifest: `meta/bibmeta.toml`.
- Inline metadata is available for true exceptions, but active files should not
  need it.
- Derived, archive, and auxiliary layers are explicitly recognizable and are not
  treated as canonical bibliographic truth.

## Roles

`bibmeta` defines exactly five file roles:

- `canonical`: authoritative bibliographic source files
- `curated`: thematic/selective collections that classify or group works
- `derived`: generated or subset layers derived from canonical sources
- `archive`: historical snapshots not intended for default consumers
- `auxiliary`: scratch, test, or metadata files not intended for normal ingest

## Manifest

The manifest lives at [`meta/bibmeta.toml`](../meta/bibmeta.toml).

Schema:

- `version = 1`
- ordered `[[rules]]` tables
- each rule supports:
  - `name`: human-readable label
  - `glob`: path glob relative to repo root
  - `exclude`: optional list of path globs to skip for that rule
  - `role`: one of the five roles above
  - `subject`: optional scalar slug template
  - `topics`: optional list of slug templates

Supported placeholders inside `subject` and `topics`:

- `{stem}`
- `{parent}`
- `{grandparent}`

Rules are evaluated in order. The first matching rule wins.

## Active path rules

Current active rules are:

- `books/*.bib` -> `role = "canonical"`, `subject = "{stem}"`
- `conferences/**/*.bib` -> `role = "canonical"`
- `journals/**/*.bib` -> `role = "canonical"`
- `references/**/*.bib` -> `role = "canonical"`
- `theses/**/*.bib` -> `role = "canonical"`
- `courses/**/*.bib` -> `role = "canonical"`
- `presentations/**/*.bib` -> `role = "canonical"`
- top-level `collections/*.bib` -> `role = "curated"`, `topics = ["{stem}"]`
- `collections/orals/*/*.bib` -> `role = "derived"`
- `collections/_archive/**/*.bib` -> `role = "archive"`
- `meta/*.bib` -> `role = "auxiliary"`

## Inline preamble

Inline metadata uses this exact syntax:

```bibtex
@COMMENT{bibmeta:
role = "curated"
topics = ["normalizing-flows"]
}
```

Rules:

- at most one `@COMMENT{bibmeta: ...}` block per file
- it must appear before the first real BibTeX directive
- the body is TOML
- inline metadata is merged over path-derived defaults
- malformed inline metadata is rejected
- inline metadata is rejected when it merely restates the path-derived default

Merge semantics:

- `role` and `subject` override path-derived defaults
- `topics` extends the default topic list by union
- `replace_topics = true` replaces the default topic list instead of extending it
- `topics_append` appends additional topics after any `topics` merge

## Field validation

`bibmeta` keeps role/field combinations intentionally strict:

- `canonical` may define `subject`, but not `topics`
- `curated` must define `topics`, but not `subject`
- `derived`, `archive`, and `auxiliary` may define neither `subject` nor `topics`

All `subject` and `topics` values must be lowercase kebab-case slugs.

## Precedence

Resolution order is:

1. path-derived defaults from `meta/bibmeta.toml`
2. optional inline `@COMMENT{bibmeta: ...}` block

Active files should prefer path semantics over inline restatement. The current
active corpus is expected to derive cleanly from path and therefore should not
need inline `bibmeta` blocks.
