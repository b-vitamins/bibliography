---
name: bibops-entry-curation
description: Curate and correct specific BibTeX entries with source-backed metadata and local validation. Use when adding papers, fixing fields, renaming keys, or repairing malformed entries in one or a few bibliography files.
---

Perform focused, source-backed entry edits with deterministic checks.

## Execute

1. Identify exact target file(s) and entry key(s).
2. Apply minimal edits required to fix metadata or formatting.
3. Run `scripts/check_entry_file.sh <file.bib> [more files...]`.
4. Ensure no placeholder authors remain and mandatory fields are present.
5. If links are updated, verify they resolve and match the cited work.

## Key rules

- Prefer official proceedings/journal URLs when available.
- Keep bibkeys lowercase alnum in `<author><year><keyword>` style.
- Preserve existing data unless clearly wrong.

See `references/source-quality.md` for source-quality and link-selection policy.
