# CLAUDE.md - Bibliography Management with Agent Infrastructure

This file provides guidance to Claude Code when working with this bibliography management system.

## User-Level Infrastructure Integration
@~/.claude/instructions/guix-workflow.md
@~/.claude/instructions/python-development.md
@~/.claude/instructions/agent-chains.md
@~/.claude/instructions/code-quality.md

## Project Overview

Personal bibliography management system with automated enrichment tracking, quality validation, and systematic organization of academic references. Built on Python + Guix with comprehensive agent automation.

**Key Features:**
- Automated BibTeX entry enrichment with OpenAlex integration
- Quality validation and citation consistency checking
- Git hooks for automatic tracking export
- Comprehensive Python utilities with SQLite tracking
- Multi-format organization (by-domain/, by-format/)

## Proactive Agent Usage

### Primary Bibliography Workflow

#### Systematic Batch Enrichment (UPDATED FOR QUALITY)
The `bibtex-entry-enricher` agent now processes exactly 10 entries at a time:
```
# Usage: Provide directory path + entry range
bibtex-entry-enricher("/home/b/projects/bibliography/tmp/neurips/2024/", entries 1-10)
bibtex-entry-enricher("/home/b/projects/bibliography/tmp/neurips/2024/", entries 11-20)
# ... continues in batches of 10
```
- Processes entry-N.bib through entry-(N+9).bib sequentially
- Performs REAL searches for each entry (no hallucination)
- Modifies each file in-place (overwrites original)  
- ZERO skipping allowed - all 10 must be processed
- Returns summary with source verification for each entry
- Quality over speed: Better partial data than false data

#### Large-Scale Sprint Processing (NEW)
For massive enrichment sprints (1000+ entries), deploy **parallel litters** of 20 agents:
```
# Each litter processes 200 entries (20 agents × 10 entries each)
# Deploy 20 agents simultaneously:
bibtex-entry-enricher(entries 1-10)    bibtex-entry-enricher(entries 101-110)
bibtex-entry-enricher(entries 11-20)   bibtex-entry-enricher(entries 111-120)
bibtex-entry-enricher(entries 21-30)   bibtex-entry-enricher(entries 121-130)
...                                     ...
bibtex-entry-enricher(entries 91-100)  bibtex-entry-enricher(entries 191-200)
```
- **Sprint batch size**: 200 entries per litter (20 agents × 10 entries)
- **Parallel execution**: All 20 agents run simultaneously for maximum throughput
- **Quality maintained**: Each agent still processes exactly 10 entries with full verification
- **Use case**: Conference proceedings, large journal collections, bulk imports

#### Standard Workflow
1. **Split file**: Use `extract-entries.py` to split .bib into individual entries
2. **Batch enrichment**: Deploy `bibtex-entry-enricher` on 10-entry batches
3. **Quality Checks**: Use `bibtex-citation-checker` after LaTeX work
4. **Validation**: Always run `validate-enrichment.py` before submission

### Python Script Maintenance
- **Import Issues**: `python-import-resolver` → fix ModuleNotFoundError
- **Code Quality**: `python-ruff-fixer` → format and lint scripts
- **Testing**: `python-unit-test-writer` → test new utilities
- **Dependencies**: `guix-manifest-updater` → sync manifest.scm

### Before Every Commit
1. `security-secret-scanner` → check for exposed secrets
2. `git-commit-formatter` → ensure conventional format
3. Automatic: pre-commit hook exports tracking.json

## Agent Chain Workflows

### New Paper Addition Chain
```
[User finds paper] → bibtex-entry-enricher → validate-enrichment.py → git commit
```

### Bulk Enrichment Chain  
```
analyze-enrichment.py → [multiple bibtex-entry-enricher] → track-batch-enrichment.py → validate-enrichment.py
```

### Script Development Chain
```
python-import-resolver → python-unit-test-writer → python-ruff-fixer → pytest-runner-guix
```

### LaTeX Citation Workflow
```
bibtex-citation-checker → [fix citations] → latex-compiler-fixer → bibtex-citation-checker
```

## Streamlined Commands

### One-Command Enrichment (PREFERRED)
```bash
# Complete file enrichment with tracking
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py file.bib --backup

# Preview changes
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py file.bib --dry-run

# Validate existing enrichments
guix shell -m manifest.scm -- python3 scripts/enrich-bibliography.py file.bib --validate-only
```

### Single Entry Addition
```bash
# Prepare entry for agent enrichment  
guix shell -m manifest.scm -- python3 scripts/prepare-entry.py target.bib "@article{...}"

# [Claude uses bibtex-entry-enricher agent on tmp/pending-enrichment/entry.bib]

# Finalize enriched entry
guix shell -m manifest.scm -- python3 scripts/finalize-entry.py target.bib tmp/pending-enrichment/entry.bib
```

### Batch Processing
```bash
# Analyze and prepare batches
guix shell -m manifest.scm -- python3 scripts/analyze-enrichment.py file.bib

# [Claude processes each batch with bibtex-entry-enricher]

# Track results
guix shell -m manifest.scm -- python3 scripts/track-batch-enrichment.py file.bib tmp/file/
```

### Quality Validation
```bash
# Comprehensive validation
guix shell -m manifest.scm -- python3 scripts/validate-enrichment.py file.bib

# Citation consistency (for LaTeX work)
# [Claude uses bibtex-citation-checker agent]
```

### Enrichment Status Tracking
```bash
# Check what needs enrichment
guix shell -m manifest.scm -- python3 scripts/enrichment-status.py

# Find retry candidates  
guix shell -m manifest.scm -- python3 scripts/enrichment-status.py --retry-candidates

# Statistics for specific file
guix shell -m manifest.scm -- python3 scripts/count-entries.py --enrichment-stats file.bib
```

## Fresh Clone Setup

**Required Steps:**
```bash
# 1. Install git hooks
guix shell -m manifest.scm -- python3 scripts/install-hooks.py

# 2. Import tracking history
guix shell -m manifest.scm -- python3 scripts/import-tracking.py

# 3. Verify setup
guix shell -m manifest.scm -- python3 scripts/enrichment-status.py
```

**Critical**: All Python commands require Guix environment: `guix shell -m manifest.scm -- python3 ...`

## Agent-Specific Usage Patterns

### bibtex-entry-enricher Agent (UPDATED FOR QUALITY)
**When to Use:**
- Processing batches of 10 entries systematically  
- Large-scale bibliography enrichment projects
- Conference/journal paper collections needing metadata

**Expected Input:** Directory path + entry range (10 entries)
**Agent Output:** Summary report with source verification for all 10 entries

**Quality Safeguards:**
- Reduced batch size (10 vs 25) to prevent fatigue/hallucination
- Mandatory source verification for each enrichment
- "Partial enrichment" marking when data not found
- No data reuse between entries

**Smart Landing Page Strategy:**
- Agent attempts to fetch conference landing page once per batch
- Extracts available titles/URL patterns as HINTS (not complete data)
- Uses patterns to guide more efficient individual searches
- Still fetches individual paper pages for abstracts and complete data
- Flexible: continues even if landing page fails or is incomplete
- Realistic about web scraping: expects redirects, changes, missing data

**Domain-Specific Search Optimization:**
The agent uses venue-specific sources and PDF patterns:
- **NeurIPS**: `proceedings.neurips.cc/paper_files/paper/YEAR/file/HASH-Paper-Conference.pdf`
- **ICML**: `proceedings.mlr.press/vVOL/surname##a/surname##a.pdf`
- **ICLR**: `openreview.net/pdf?id=PAPER_ID`
- **CVPR/ICCV**: `openaccess.thecvf.com/content/` + patterns
- **ACL**: `aclanthology.org/YEAR.venue-main.###.pdf`

**Critical Priority**: Always prefer official accepted version PDFs over arXiv preprints
**Note:** OpenAlex ID enrichment is optional (removed to optimize token usage)

**Workflow:**
```bash
# Extract entries from bibliography file to specific directory
guix shell -m manifest.scm -- python3 scripts/extract-entries.py conferences/neurips/2024.bib tmp/neurips/2024/

# OR use default tmp/<basename>/ directory
guix shell -m manifest.scm -- python3 scripts/extract-entries.py conferences/neurips/2024.bib

# Process in batches of 10 (for quality assurance)
# Agent enriches entry-1.bib through entry-10.bib in-place with verified data
bibtex-entry-enricher("tmp/neurips/2024/", entries 1-10)
bibtex-entry-enricher("tmp/neurips/2024/", entries 11-20)
bibtex-entry-enricher("tmp/neurips/2024/", entries 21-30)
# ... continue until all entries processed

# Reassemble enriched entries
for i in $(seq 1 4494); do
  cat tmp/neurips/2024/entry-$i.bib
  echo
done > conferences/neurips/2024-enriched.bib
```

### bibtex-citation-checker Agent  
**When to Use:**
- Before LaTeX paper submission
- After adding citations to documents
- Cleaning up unused entries

**Agent Tasks:**
- Find missing BibTeX entries for LaTeX citations
- Identify unused entries in .bib files  
- Detect citation key typos and case mismatches

### python-import-resolver Agent
**When to Use:**
- ModuleNotFoundError in scripts
- Missing packages after Guix updates
- New dependencies added to code

**Agent Tasks:**
- Maps import names to Guix package names
- Updates manifest.scm with missing packages
- Verifies imports work in Guix shell

## Repository Structure & Organization

```
bibliography/
├── by-domain/              # Research domain organization
│   ├── llm.bib            # Large language models  
│   ├── transformers.bib   # Transformer architectures
│   ├── diffusion.bib      # Diffusion models
│   └── ...
├── by-format/             # Publication type organization
│   ├── papers/            # Journal articles
│   ├── references/        # Technical references
│   │   ├── whitepapers.bib
│   │   └── award.bib
│   ├── theses/           # Academic theses
│   └── courses/          # Course materials
├── scripts/              # Python utilities (Guix-based)
├── tracking.json         # Version-controlled enrichment history
├── bibliography.db       # Local SQLite tracking (ignored by git)
├── hooks/               # Git hooks (pre-commit, commit-msg)
└── manifest.scm         # Guix dependency specification
```

## Error Recovery & Troubleshooting

### Import Errors in Scripts
1. Use `python-import-resolver` agent
2. Check manifest.scm has required packages
3. Verify Guix environment: `guix shell -m manifest.scm -- python3 -c "import MODULE"`

### Enrichment Failures
1. Check enrichment-status.py output
2. Review tmp/ files for partial work
3. Use --retry-failed flag with enrich-bibliography.py
4. Validate BibTeX syntax with verify-bib.py

### Git Hook Issues
```bash
# Reinstall hooks
guix shell -m manifest.scm -- python3 scripts/install-hooks.py

# Manual tracking export
guix shell -m manifest.scm -- python3 scripts/export-tracking.py
```

### Citation Consistency Problems
1. Use `bibtex-citation-checker` agent for analysis
2. Check LaTeX vs BibTeX key matches (case sensitive)
3. Verify all citation commands (\cite, \citep, \parencite, etc.)

## Performance Guidelines

### Batch Processing
- **Standard batches**: 10 entries per agent (quality-focused)
- **Sprint litters**: 20 agents × 10 entries = 200 entries per litter (throughput-focused)
- Use analyze-enrichment.py for optimal batching
- Process unenriched entries first

### File Assembly  
**CRITICAL**: Always use sequential loops for concatenation:
```bash
for i in $(seq 1 $total); do
  if [ -f "tmp/dir/entry-$i.bib" ]; then
    cat "tmp/dir/entry-$i.bib"
    echo
  fi
done > output.bib
```

Never use brace expansion `{1..100}` or wildcards `*.bib` with large counts.

## Quality Standards

### BibTeX Entry Requirements
1. **Mandatory Fields**: Present for entry type (@article needs author, title, journal, year)
2. **OpenAlex ID**: Format `openalex = {W123456789}`
3. **PDF Priority**: Official venue → arXiv → preprint
4. **Author Names**: Full first names when available
5. **Abstract**: From official source when possible
6. **Consistent Formatting**: BibTeX grammar compliance

### Python Code Standards
- Use `python-ruff-fixer` for formatting/linting
- Always wrap commands: `guix shell -m manifest.scm -- command`
- 100% test coverage on public APIs (use `python-unit-test-writer`)
- Type hints on function signatures (use `python-pyright-resolver`)

## Commit Guidelines

### Format (Enforced by Hook)
```
<type>: <description>
```

**Types**: feat, enhance, fix, refactor, doc/docs, chore, cleanup, test, style

**Examples:**
- `enhance: Enrich 15 autoencoder papers with PDF links`
- `feat: Add automated batch enrichment with tracking`
- `fix: Resolve duplicate keys in transformers.bib`

**Note**: This repository does NOT add Claude Code co-authored-by lines.

## Development Workflow

### Adding New Scripts
1. Implement with proper error handling
2. Use `python-unit-test-writer` for tests
3. Run `python-ruff-fixer` for code quality
4. Update manifest.scm if new dependencies needed
5. Document in scripts/README-enrichment-automation.md

### Extending Enrichment Logic
1. Modify enrich-bibliography.py or related scripts
2. Use `python-regression-tester` to avoid breaking existing workflows
3. Test with --dry-run flag first
4. Update tracking database schema if needed

### Git Workflow Integration
- Pre-commit hook automatically exports tracking.json
- Commit-msg hook validates format
- Use conventional commit format for clean history

This system combines powerful Python utilities with Claude Code's agent infrastructure for efficient, high-quality bibliography management. The agent chains automate routine tasks while maintaining research organization and academic standards.