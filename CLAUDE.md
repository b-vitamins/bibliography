# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
./bib check all         # Run all validation checks
./bib check paths       # Verify all PDF paths exist
./bib check duplicates  # Check for duplicate keys
./bib check fields      # Validate required fields
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

### Git Hooks (once installed)
```bash
bash hooks/install.sh  # Install pre-commit validation hooks
```

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
- 13 .bib files (3 by-subject, 10 by-type)
- Phase 1: Building validation framework and Git hooks

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