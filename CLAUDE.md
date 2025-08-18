# CLAUDE.md - Bibliography Management & Enrichment Workflows

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Decision Tree

- **Adding a new paper?** → Run `prepare-entry.py` → I'll enrich → Run `finalize-entry.py`
- **Enriching existing file?** → Run `analyze-enrichment.py` → I'll process batches → Reassemble with sequential loop
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

### Workflow A: Single Entry Addition
```
1. User: python3 scripts/prepare-entry.py target.bib "@article{...}"
2. Claude: Task(subagent_type: "bibtex-entry-enricher", prompt: "Please enrich the BibTeX entry in the file: tmp/pending-enrichment/entry.bib")
3. User: python3 scripts/finalize-entry.py target.bib tmp/pending-enrichment/entry.bib
```

### Workflow B: Batch File Enrichment
```
1. User: python3 scripts/analyze-enrichment.py file.bib
   Output: "15 unenriched entries found, prepared in 1 batch: tmp/file/batch-1.json"
2. Claude: Process batch files listed in JSON (parallel enrichment of up to 20 entries)
3. User: Reassemble using sequential loop method (see File Assembly section)
```


## Common Commands

### New Streamlined Commands
```bash
# Prepare entry for enrichment
python3 scripts/prepare-entry.py target.bib "@article{key2024, ...}"

# Finalize enriched entry
python3 scripts/finalize-entry.py target.bib tmp/pending-enrichment/entry.bib

# Analyze file for batch enrichment
python3 scripts/analyze-enrichment.py file.bib

# Count with enrichment statistics
python3 scripts/count-entries.py --enrichment-stats file.bib
```

### Core Commands
```bash
# Verify BibTeX syntax
python3 scripts/verify-bib.py by-domain/*.bib

# Clean BibTeX files
python3 scripts/clean-bib.py --in-place by-domain/transformers.bib

# Count entries (simple)
python3 scripts/count-entries.py by-domain/llm.bib

# Extract individual entries
python3 scripts/extract-entries.py by-domain/transformers.bib

# Compare BibTeX files
python3 scripts/compare-bib-files.py original.bib enriched.bib
```

### Enrichment Tracking Commands

**Important**: On fresh clone, run `python3 scripts/import-tracking.py` to restore enrichment history.

```bash
# Initialize tracking from version-controlled export (fresh clone)
python3 scripts/import-tracking.py enrichment-tracking.json

# Check enrichment history
python3 scripts/enrichment-status.py [file.bib]

# Find failed entries to retry
python3 scripts/enrichment-status.py --retry-candidates

# Get JSON output for automation
python3 scripts/enrichment-status.py --json

# Manual export (automatic on git commit)
python3 scripts/export-tracking.py

# Manual tracking (normally automatic)
python3 scripts/track-enrichment.py file.bib entry_key success W123456789
```

## Enrichment Tracking System

The repository uses SQLite for local enrichment tracking with automatic export/import:

- **Local database**: `bibliography.db` (not version controlled)
- **Export file**: `enrichment-tracking.json` (version controlled) 
- **Pre-commit hook**: Automatically exports database on every commit
- **Fresh clone**: Run `python3 scripts/import-tracking.py` to restore history

This hybrid approach provides:
- Fast local queries and atomic updates via SQLite
- Version-controlled history via JSON exports
- Seamless synchronization across machines
- Complete audit trail of enrichment attempts

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

- Do not add the "Generated by Claude Code" comment in commits for this repository
- Use descriptive commit messages following the examples:
  - "enhance: Enrich autoencoder.bib with PDF links and fixes"
  - "enhance: Update continual.bib with standardized bibkeys and camera-ready PDFs"
  - "fix: Correct duplicate abstract fields in ssm.bib"

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