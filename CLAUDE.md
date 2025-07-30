# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## CRITICAL: Correctness Invariant
**This repository MUST maintain correctness at all times.** This is a hard requirement that applies to the entire lifetime of the project:
- Never commit invalid or inconsistent data
- All tools MUST support --dry-run mode for safe testing
- Test with real data (existing issues) before fixing
- Only commit BibTeX files after all validation passes
- Use existing validation errors as test cases during development
- Git hooks enforce this invariant - they will block commits with validation errors
- Always work within Guix environment: `guix shell -m manifest.scm`
- **NEVER bypass hooks** - Fix all issues before committing (no --no-verify)

## Repository Overview
This is a BibTeX-based personal bibliography management system that maintains strict one-to-one correspondence between PDF files and BibTeX metadata entries. The system is designed for academic reference management with version control (Git) for metadata.

## Architecture
- **Bibliography metadata**: `/home/b/projects/bibliography/bibtex/` (Git-controlled .bib files)
- **PDF storage**: `/home/b/documents/{entry-type}/` (filesystem storage, not in Git)
- **Entry types**: article, book, booklet, conference, inbook, incollection, inproceedings, manual, mastersthesis, misc, phdthesis, proceedings, techreport, unpublished

## Key Files
- `DESIGN.md`: Complete system architecture and validation rules
- `ROADMAP.md`: Phased implementation plan (currently in Phase 1)
- `TODO.md`: Current task tracking
- `bibtex/by-subject/*.bib`: Subject-organized bibliography files
- `bibtex/by-type/*.bib`: Type-organized bibliography files

## Common Commands

### Validation
```bash
# In Guix shell environment:
python3 -m bibmgr.cli check all         # Run all validation checks
python3 -m bibmgr.cli check paths       # Verify all PDF paths exist
python3 -m bibmgr.cli check duplicates  # Check for duplicate keys
python3 -m bibmgr.cli check fields      # Validate required fields

# Fix operations (dry-run by default):
python3 -m bibmgr.cli fix all           # Fix all issues
python3 -m bibmgr.cli fix all --no-dry-run  # Apply fixes
```

### Quick Checks
```bash
# Count total PDFs in storage
find /home/b/documents -name "*.pdf" -type f | wc -l

# List all .bib files
find bibtex -name "*.bib" -type f

# Search for specific entry
grep -r "feynman" bibtex/
```

### Git Hooks
The repository includes comprehensive Git hooks that enforce quality standards and prevent non-compliant changes. Install them with:
```bash
./hooks/install.sh  # Install all quality enforcement hooks
```

**Hooks enforce:**
- **pre-commit**: Code quality (ruff, pyright), BibTeX validation, secrets scanning, file permissions
- **commit-msg**: Conventional commit format (type(scope): description)
- **pre-push**: Full test suite, documentation checks, security scan
- **prepare-commit-msg**: Commit template, scope suggestions, issue references
- **post-commit**: Statistics, follow-up reminders, repository health

See `hooks/README.md` for detailed documentation.

## Development Guidelines

### File Path Convention
All BibTeX entries must use absolute paths:
```bibtex
file = {:/home/b/documents/{entry-type}/{filename}.pdf:pdf}
```

### Citation Key Format
Pattern: `{author}{year}{keyword}` (e.g., `feynman1942principle`)

### Mandatory Fields by Type
- `@article`: author, title, journal, year
- `@book`: author/editor, title, publisher, year
- `@phdthesis`: author, title, school, year
- See `DESIGN.md` Section 3.1 for complete list

### Current Status
- 194 PDFs organized across entry types (189 misc, 4 techreport, 1 phdthesis)
- 13 .bib files (3 by-subject, 10 by-type) - **INTENTIONALLY UNCOMMITTED**
- Phase 1: Building validation framework with --dry-run capabilities

### Test Data (Existing Validation Errors)
The following errors are **intentionally preserved** as test cases:
1. **3 duplicate keys**: `illinois2012igmhw[1-3]` between homework/solutions files
2. **4 missing author fields**: ISO standards in technical-standards.bib

These errors will be fixed using the developed tools before committing .bib files.

### Implementation Priority
1. Create validation scripts in `scripts/validate/`
2. Set up Git pre-commit hooks
3. Create configuration files in `config/`
4. Build import/export utilities in Phase 2

### Dependencies
Defined in `manifest.scm`:
- python3, python-bibtexparser, python-click
- python-ruff for linting and formatting
- node-pyright for type checking
- python-lsp-server for editor LSP support

### Code Standards
- Python 3.11+ with full type hints
- Ruff and pyright compliant
- Click-based CLI with subcommands
- Dataclasses for models