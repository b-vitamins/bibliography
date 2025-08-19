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
1. **Adding Papers**: Use `bibtex-entry-enricher` for each new entry
2. **Quality Checks**: Use `bibtex-citation-checker` after LaTeX work  
3. **Bulk Processing**: Chain multiple `bibtex-entry-enricher` calls
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

### bibtex-entry-enricher Agent
**When to Use:**
- Single entry needs enrichment with OpenAlex ID + PDF
- Part of batch processing workflow  
- Entry has incomplete or incorrect metadata

**Expected Input:** File path to single BibTeX entry
**Agent Output:** Status message only (modifies file in-place)

**Workflow:**
```bash
# Prepare entry file for agent
echo '@article{key2023, title={...}}' > /tmp/entry.bib

# Use agent via Task tool
# Agent reads file, enriches entry, saves back to same file

# Verify enrichment worked
cat /tmp/entry.bib
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
- Maximum 20 entries per agent invocation
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