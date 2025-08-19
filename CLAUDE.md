# CLAUDE.md - Bibliography Management & Enrichment Workflows

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Decision Tree

- **Enriching entire file?** → Run `enrich-bibliography.py file.bib --backup` (ONE COMMAND!)
- **Adding a new paper?** → Run `prepare-entry.py` → I'll enrich → Run `finalize-entry.py`
- **Manual batch enrichment?** → Run `analyze-enrichment.py` → I'll process batches → Reassemble with sequential loop
- **Quick check?** → Run `verify-bib.py` or `count-entries.py --enrichment-stats`
- **Finding a paper?** → Use `grep -i "title\|author" file.bib`

## Programmatic vs Agent Boundaries

- **Scripts handle**: Analysis, file I/O, validation, preparation, assembly
- **Claude handles**: Enrichment agent invocations, batch orchestration
- **Handoff points**: Always through tmp/ files with clear naming
- **Recovery**: If enrichment fails, original files remain untouched

## Repository Overview

This is a personal bibliography management system storing BibTeX entries organized by research domain and format. The repository contains Python scripts for verifying, cleaning, and manipulating BibTeX files.

## Streamlined Workflows

### Workflow AUTOMATED: Complete File Enrichment (NEW!)
```
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py file.bib --backup
```
This single command:
1. Analyzes the file for unenriched entries
2. Creates batches and processes them (handles ENRICHMENT_REQUIRED markers)
3. Reassembles the enriched file
4. Validates the results
5. Replaces the original (with backup)
6. Handles all errors with automatic rollback

Options:
- `--backup`: Create timestamped backup (recommended)
- `--validate-only`: Just validate without enriching
- `--retry-failed`: Include previously failed entries
- `--dry-run`: Preview what would be done
- `--batch-size N`: Custom batch size (default: 20)
- `--verbose`: Detailed debug output

### Workflow A: Single Entry Addition
```
1. User: guix shell -m manifest.scm -- python3 scripts/prepare-entry.py target.bib "@article{...}"
2. Claude: Task(subagent_type: "bibtex-entry-enricher", prompt: "Please enrich the BibTeX entry in the file: tmp/pending-enrichment/entry.bib")
3. User: guix shell -m manifest.scm -- python3 scripts/finalize-entry.py target.bib tmp/pending-enrichment/entry.bib
```

### Workflow B: Batch File Enrichment
```
1. User: guix shell -m manifest.scm -- python3 scripts/analyze-enrichment.py file.bib
   Output: "15 unenriched entries found, prepared in 1 batch: tmp/file/batch-1.json"
2. Claude: Process batch files listed in JSON (parallel enrichment of up to 20 entries)
3. User: Reassemble using sequential loop method (see File Assembly section)
4. User: guix shell -m manifest.scm -- python3 scripts/track-batch-enrichment.py file.bib tmp/file/
```

### Workflow C: Automated Single Entry Enrichment with Tracking
```
1. User: guix shell -m manifest.scm -- python3 scripts/enrich-entry-with-tracking.py target.bib entry_key
   Output: Instructions for manual agent invocation and temporary file path
2. Claude: Task(subagent_type: "bibtex-entry-enricher", prompt: "Please enrich the BibTeX entry in the file: /tmp/enrich_entry_key_xyz.bib")
3. Script automatically tracks result in database
```

### Workflow D: Automated Batch Enrichment with Tracking
```
1. User: guix shell -m manifest.scm -- python3 scripts/analyze-enrichment.py file.bib
   Output: Batch JSON files in tmp/file/
2. User: guix shell -m manifest.scm -- python3 scripts/batch-enrich-with-tracking.py tmp/file/batch-1.json
3. Claude: For each entry marked "ENRICHMENT_REQUIRED", run bibtex-entry-enricher
4. Script automatically tracks all results and provides summary
```

### Workflow E: Post-Enrichment Validation
```
1. User: guix shell -m manifest.scm -- python3 scripts/validate-enrichment.py file.bib
   Output: Detailed validation report with pass/warning/fail status
2. Review warnings and failures
3. Re-enrich failed entries if needed
4. Use in CI/CD: Script exits with code 1 if any failures found
```


## Common Commands

### New Streamlined Commands
```bash
# Prepare entry for enrichment
guix shell -m manifest.scm -- python3 scripts/prepare-entry.py target.bib "@article{key2024, ...}"

# Finalize enriched entry
guix shell -m manifest.scm -- python3 scripts/finalize-entry.py target.bib tmp/pending-enrichment/entry.bib

# Analyze file for batch enrichment
guix shell -m manifest.scm -- python3 scripts/analyze-enrichment.py file.bib

# Count with enrichment statistics
guix shell -m manifest.scm -- python3 scripts/count-entries.py --enrichment-stats file.bib

# Validate enriched entries quality
guix shell -m manifest.scm -- python3 scripts/validate-enrichment.py file.bib [entry_key]

# Track enrichment after batch processing
guix shell -m manifest.scm -- python3 scripts/track-batch-enrichment.py file.bib tmp/file/

# Enrich single entry with automatic tracking
guix shell -m manifest.scm -- python3 scripts/enrich-entry-with-tracking.py target.bib entry_key

# Process batch with automatic tracking
guix shell -m manifest.scm -- python3 scripts/batch-enrich-with-tracking.py tmp/file/batch-1.json
```

### NEW: One-Command Enrichment
```bash
# Enrich entire BibTeX file with automatic workflow
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py by-domain/llm.bib --backup

# Preview what would be enriched
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py by-domain/transformers.bib --dry-run

# Validate existing file
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py by-format/references/papers.bib --validate-only
```

### Core Commands
```bash
# Verify BibTeX syntax
guix shell -m manifest.scm -- python3 scripts/verify-bib.py by-domain/*.bib

# Clean BibTeX files
guix shell -m manifest.scm -- python3 scripts/clean-bib.py --in-place by-domain/transformers.bib

# Count entries (simple)
guix shell -m manifest.scm -- python3 scripts/count-entries.py by-domain/llm.bib

# Extract individual entries
guix shell -m manifest.scm -- python3 scripts/extract-entries.py by-domain/transformers.bib

# Compare BibTeX files
guix shell -m manifest.scm -- python3 scripts/compare-bib-files.py original.bib enriched.bib
```

### Enrichment Tracking Commands

**Important**: On fresh clone, run:
1. `guix shell -m manifest.scm -- python3 scripts/install-hooks.py` to install git hooks
2. `guix shell -m manifest.scm -- python3 scripts/import-tracking.py` to restore enrichment history

**CRITICAL**: All Python scripts require Guix environment. Always use:
```bash
guix shell -m manifest.scm -- python3 scripts/script-name.py
```

```bash
# Initialize tracking from version-controlled export (fresh clone)
guix shell -m manifest.scm -- python3 scripts/import-tracking.py tracking.json

# Check enrichment history
guix shell -m manifest.scm -- python3 scripts/enrichment-status.py [file.bib]

# Find failed entries to retry
guix shell -m manifest.scm -- python3 scripts/enrichment-status.py --retry-candidates

# Get JSON output for automation
guix shell -m manifest.scm -- python3 scripts/enrichment-status.py --json

# Manual export (automatic on git commit)
guix shell -m manifest.scm -- python3 scripts/export-tracking.py

# Manual tracking (normally automatic)
guix shell -m manifest.scm -- python3 scripts/track-enrichment.py file.bib entry_key success W123456789

# Retry failed enrichments
guix shell -m manifest.scm -- python3 scripts/retry-failed-enrichments.py
guix shell -m manifest.scm -- python3 scripts/retry-failed-enrichments.py --older-than 7
guix shell -m manifest.scm -- python3 scripts/retry-failed-enrichments.py --file file.bib
guix shell -m manifest.scm -- python3 scripts/retry-failed-enrichments.py --dry-run
```

## Enrichment Tracking System

The repository uses SQLite for local enrichment tracking with automatic export/import:

- **Local database**: `bibliography.db` (not version controlled)
- **Export file**: `tracking.json` (version controlled) 
- **Pre-commit hook**: Automatically exports database on every commit
- **Fresh clone**: Run `python3 scripts/import-tracking.py` to restore history

This hybrid approach provides:
- Fast local queries and atomic updates via SQLite
- Version-controlled history via JSON exports
- Seamless synchronization across machines
- Complete audit trail of enrichment attempts

## Git Hooks System

Version-controlled git hooks ensure consistent workflow across machines:

- **hooks/pre-commit**: Automatically exports tracking database on every commit
- **hooks/commit-msg**: Validates commit message format and enforces standards
- **scripts/install-hooks.py**: Installs hooks from version-controlled location

### Setup:
```bash
# Install hooks after fresh clone
python3 scripts/install-hooks.py
```

Hooks are stored in `hooks/` directory and copied to `.git/hooks/` during installation.

## Repository Structure

The bibliography is organized into three main directories:

- **by-domain/**: BibTeX files categorized by research domain (ML theory, transformers, LLMs, etc.)
- **by-format/**: BibTeX files organized by publication format (papers, theses, courses, presentations)
- **meta/**: Working and test BibTeX files

Python utilities in **scripts/** handle BibTeX file operations without requiring external package management. All scripts use bibtexparser and standard library modules.

## Enrichment Guidelines

### Entry Quality Standards
1. **Mandatory fields** must be present based on entry type
2. **OpenAlex ID** in format: `openalex = {W123456789}`
3. **PDF link** priority: official venue → arXiv → other
4. **Author names** with full first names when available
5. **Abstract** from official source when available
6. **Consistent formatting** following BibTeX grammar rules

### Pre-enrichment Checks
1. Verify file exists and is readable
2. Check for existing enriched entries (grep for "openalex")
3. Create backups before in-place modifications
4. Validate BibTeX syntax before processing

### Post-enrichment Validation
1. Verify all entries preserved (count matches)
2. Check enrichment indicators (openalex, pdf fields)
3. Run verify-bib.py to check syntax
4. Compare with original using compare-bib-files.py

### Error Recovery
1. Keep tmp/ directories if verification fails
2. Preserve .backup files until confirmed success
3. Log failed entries with reasons
4. Never delete original data without verification

## Performance Considerations

### Batch Processing
- Maximum 20 concurrent enrichment tasks
- 30-second timeout per entry
- Process unenriched entries first in partial enrichment
- Use TODO lists for files >50 entries

### File Assembly
**CRITICAL**: Always use sequential loop for concatenation:
```bash
for i in $(seq 1 $total); do
  if [ -f "tmp/dir/entry-$i.bib" ]; then
    cat "tmp/dir/entry-$i.bib"
    echo
  fi
done > output.bib
```

Never use:
- Brace expansion: `{1..100}`
- Wildcards with many files: `*.bib`
- xargs with large file lists

### Temporary File Management
- Create under tmp/ with descriptive names
- Clean up only after successful verification
- Preserve on any errors for debugging
- Use subdirectories to avoid conflicts

## Development Notes

- Scripts use UTF-8 encoding and handle control characters, EOF markers, and shell artifacts
- The clean-bib.py script creates backup files by default before modifications
- Entry extraction creates temporary directories under tmp/ which should be cleaned periodically
- All scripts follow Unix conventions with clear error messages and exit codes
- The bibtex-entry-enricher agent modifies files in-place and returns status messages only

## Commit Guidelines

### Format Requirements (Enforced by Git Hook)
- Format: `<type>: <description>`
- Maximum 72 characters for first line
- Do not add the "Generated by Claude Code" comment in commits for this repository

### Allowed Types:
- `feat`: New feature or functionality
- `enhance`: Improve existing feature (bibliographies, enrichment)
- `fix`: Bug fix or correction
- `refactor`: Code structure changes without functionality change
- `doc`/`docs`: Documentation updates
- `chore`: Maintenance tasks, dependency updates
- `cleanup`: Remove unused code, files, or data
- `test`: Add or modify tests
- `style`: Code style/formatting changes

### Examples:
- "enhance: Enrich autoencoder.bib with PDF links and fixes"
- "enhance: Update continual.bib with standardized bibkeys and camera-ready PDFs"
- "fix: Correct duplicate abstract fields in ssm.bib"
- "feat: Add streamlined entry enrichment workflow"
- "refactor: Rename tracking file to shorter name"

The commit-msg hook will reject non-conforming messages with helpful guidance.

## Detailed Legacy Workflows

### Manual Entry Addition (without scripts)
For reference when scripts are unavailable.

1. Verify target file exists: `ls -la target.bib`
2. Check for duplicates: `grep -i "key\|title" target.bib`
3. Create temp entry: `echo '@article{...}' > tmp/entry.bib`
4. Enrich via agent Task
5. Append: `echo "" >> target.bib && cat tmp/entry.bib >> target.bib`
6. Clean up: `rm -f tmp/entry.bib`

### Manual Partial Enrichment (without scripts)
For reference when scripts are unavailable.

1. Count entries: `grep -c "^@" file.bib`
2. Count enriched: `grep -c "openalex" file.bib`
3. Extract entries: `python3 scripts/extract-entries.py file.bib`
4. Find unenriched entries manually
5. Process in batches via agent Tasks
6. Reassemble with sequential loop
7. Verify and replace