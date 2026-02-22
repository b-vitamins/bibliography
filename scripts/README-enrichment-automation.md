# Enrichment Automation Scripts

This document describes the automated enrichment scripts that wrap the bibtex-entry-enricher agent and provide automatic tracking.

## New Modular Pipeline (`scripts/enrichment`)

For venue-grounded, provenance-aware enrichment, use the modular pipeline:

- `python3 scripts/enrich-pipeline.py plan <file.bib>`
- `python3 scripts/enrich-pipeline.py run <file.bib>`
- `python3 scripts/enrich-pipeline.py run <file.bib> --write`

Configuration lives in `ops/enrichment-pipeline.toml`.

The new pipeline is adapter-based and currently includes:

- OpenReview adapter for ICLR-style entries.
- Official NeurIPS proceedings adapter for NeurIPS-style entries.
- PMLR adapter for ICML-style entries.
- arXiv adapter for `eprint/archiveprefix/primaryclass/arxiv` field enrichment.
- Semantic Scholar adapter for BibTeX-standard metadata repair/fill
  (`author`, `doi`, `abstract`, `note`, venue/journal/year/keywords, and missing `url`/`pdf`).

Each run emits:

- Per-run report under `ops/enrichment-runs/`
- Unresolved triage queue under `ops/unresolved/enrichment/`

Use this pipeline for future enrichment work where source fidelity and repeatability are primary concerns.

For arXiv-focused runs (without touching canonical `url/pdf` venue links), use:

- `python3 scripts/enrich-pipeline.py run <file.bib> --config ops/enrichment-arxiv.toml --write`

For Semantic Scholar-focused BibTeX quality improvements, use:

- `python3 scripts/enrich-pipeline.py run <file.bib> --config ops/enrichment-semanticscholar.toml --write`

## New Intake Pipeline (`scripts/intake`)

For de novo year bootstrap from canonical venue catalogs, use:

- `python3 scripts/intake-pipeline.py discover <venue:year> [more targets...]`
- `python3 scripts/intake-pipeline.py plan <venue:year> [more targets...]`
- `python3 scripts/intake-pipeline.py run <venue:year> [more targets...] --write --fail-on-gap`

Control-plane wrapper:

- `python3 scripts/bibops.py intake discover <venue:year> ...`
- `python3 scripts/bibops.py intake plan <venue:year> ...`
- `python3 scripts/bibops.py intake run <venue:year> ... --write --fail-on-gap`

Configuration lives in `ops/intake-pipeline.toml`.

The intake pipeline emits:

- Per-run report under `ops/intake-runs/`
- Source snapshots under `ops/intake-snapshots/`
- Unresolved queue under `ops/unresolved/intake/`

## Scripts Overview

### enrich-entry-with-tracking.py
Enriches a single BibTeX entry and automatically tracks the result.

**Usage**: `python3 scripts/enrich-entry-with-tracking.py <target_file> <entry_key>`

**Features**:
- Extracts the specified entry from the target file
- Creates a temporary file for enrichment
- Provides instructions for agent invocation
- Checks enrichment success (openalex, pdf, abstract fields)
- Automatically tracks result in database
- Preserves enriched entry for later use

**Exit codes**:
- 0: Success
- 1: Error (entry not found, parse error, etc.)

### enrich-single-entry.py
Streamlined version designed for programmatic use within Claude Code environment.

**Usage**: `python3 scripts/enrich-single-entry.py <target_file> <entry_key>`

**Features**:
- Similar to enrich-entry-with-tracking.py but optimized for automation
- Outputs "ENRICHMENT_REQUIRED: <path>" marker for Claude to process
- Automatically cleans up temporary files
- Returns specific exit codes for different outcomes

**Exit codes**:
- 0: Success (enriched with indicators)
- 1: Failure (error)
- 2: Partial (processed but no indicators)

### batch-enrich-with-tracking.py
Processes multiple entries from a batch JSON file.

**Usage**: `python3 scripts/batch-enrich-with-tracking.py <batch_json_file>`

**Batch JSON format**:
```json
{
  "source_file": "path/to/file.bib",
  "entries": ["key1", "key2", "key3"]
}
```

**Features**:
- Processes each entry using enrich-single-entry.py
- Provides progress updates
- Summarizes results (success/partial/failed)
- All tracking handled automatically
- Returns appropriate exit code based on results

## Integration with Claude Code

These scripts are designed to work within Claude Code's environment where the bibtex-entry-enricher agent can be invoked programmatically.

### Manual workflow:
1. Run enrich-entry-with-tracking.py
2. Copy the Task() command from output
3. Execute in Claude Code
4. Script detects changes and tracks

### Automated workflow:
1. Run enrich-single-entry.py or batch-enrich-with-tracking.py
2. Claude Code detects "ENRICHMENT_REQUIRED" markers
3. Claude invokes agent for each marker
4. Scripts automatically track all results

## Complete Workflow Orchestration

### enrich-bibliography.py
Orchestrates the entire enrichment workflow end-to-end in a single command.

**Usage**: `python3 scripts/enrich-bibliography.py <file.bib> [options]`

**Options**:
- `--backup`: Create backup before modifying (recommended)
- `--validate-only`: Just run validation without enrichment
- `--retry-failed`: Include retry of previously failed entries
- `--dry-run`: Show what would be done without executing
- `--batch-size N`: Number of entries per batch (default: 20)
- `--max-batches N`: Limit number of batches to process
- `--verbose`: Show detailed debug output

**Features**:
- Analyzes file to find unenriched entries
- Processes entries in configurable batches
- Handles ENRICHMENT_REQUIRED markers automatically
- Reassembles enriched file atomically
- Validates results before replacing original
- Creates timestamped backups
- Provides clear progress reporting
- Gracefully handles errors with rollback

**Workflow steps**:
1. Initial checks (file exists, database ready)
2. Create backup (if requested)
3. Analyze file for enrichment status
4. Process batches via Claude enrichment
5. Reassemble enriched entries
6. Validate enriched file
7. Replace original with enriched version
8. Clean up temporary files

**Exit codes**:
- 0: Success
- 1: Failure (with automatic rollback)

### Example workflows:

**Basic enrichment with backup**:
```bash
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py by-domain/llm.bib --backup
```

**Dry run to preview**:
```bash
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py by-domain/transformers.bib --dry-run
```

**Validate existing file**:
```bash
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py by-format/references/papers.bib --validate-only
```

**Process with retry of failures**:
```bash
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py by-domain/ml-theory.bib --backup --retry-failed
```

## Database Tracking

All scripts use the enrichment tracking system:
- Success: Entry enriched with OpenAlex ID
- Failed: Entry could not be enriched
- Tracked fields: file_path, entry_key, status, openalex_id, timestamp

The tracking database is automatically initialized if it doesn't exist.
