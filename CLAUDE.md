# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ CRITICAL: USE OF --no-verify IS STRICTLY PROHIBITED ⚠️
**NEVER use `git commit --no-verify` or any other means to bypass Git hooks.**
- All validation errors MUST be fixed before committing
- The repository enforces correctness through Git hooks - bypassing them violates the core invariant
- If hooks are blocking your commit, FIX THE ISSUES, don't bypass the checks

## CRITICAL: Correctness Invariant
**This repository MUST maintain correctness at all times.** This is a hard requirement that applies to the entire lifetime of the project:
- Never commit invalid or inconsistent data
- All tools MUST support --dry-run mode for safe testing
- Test with real data (existing issues) before fixing
- Only commit BibTeX files after all validation passes
- Use existing validation errors as test cases during development
- Git hooks enforce this invariant - they will block commits with validation errors
- Always work within Guix environment: `guix shell -m manifest.scm`

## Repository Overview
This is a BibTeX-based personal bibliography management system that maintains strict one-to-one correspondence between PDF files and BibTeX metadata entries. The system is designed for academic reference management with version control (Git) for metadata.

## Architecture
- **Bibliography metadata**: `/home/b/projects/bibliography/bibtex/` (Git-controlled .bib files)
- **PDF storage**: `/home/b/documents/{entry-type}/` (filesystem storage, not in Git)
- **Entry types**: article, book, booklet, conference, inbook, incollection, inproceedings, manual, mastersthesis, misc, phdthesis, proceedings, techreport, unpublished

## Key Files
- `DESIGN.md`: Complete system architecture and validation rules
- `ROADMAP.md`: Phased implementation plan (Phase 2 complete, Phase 3 ready)
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
```

### CRUD Operations
```bash
# Add entries
python3 -m bibmgr.cli add               # Interactive entry creation
python3 -m bibmgr.cli add --type article --dry-run  # Preview adding article
python3 -m bibmgr.cli add --from-file refs.bib  # Import from .bib file

# Remove entries
python3 -m bibmgr.cli remove <key> --dry-run  # Preview removal
python3 -m bibmgr.cli remove <key> --remove-pdf  # Also delete PDF file

# Update entries
python3 -m bibmgr.cli update <key>     # Interactive update
python3 -m bibmgr.cli update <key> --set title="New Title"  # Direct update
python3 -m bibmgr.cli update <key> --move-pdf /new/path.pdf  # Move PDF

# View entries
python3 -m bibmgr.cli show <key>       # Display single entry
python3 -m bibmgr.cli list --type article  # List by type
python3 -m bibmgr.cli list --author feynman  # Filter by author
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
- 13 .bib files (3 by-subject, 10 by-type) - all committed and validated
- Phase 1: Complete ✓ - Validation framework and Git hooks operational
- Phase 2: Complete ✓ - Core data layer with CRUD operations implemented
- Phase 3: Ready - Enhanced search and query capabilities

### Phase History
- **Phase 1**: Core infrastructure, validation, Git hooks - Complete
- **Phase 2**: Core data layer, basic CRUD operations - Complete (14 tests passing)
- **Phase 3**: Enhanced search and query - Ready to begin
- **Phase 4**: Bulk operations - Next
- **Phase 5**: Maintenance and analysis tools - Future
- **Phase 6**: Import and integration tools - Future

### Implementation Priority (Phase 3)
1. Build search engine with indexing and ranking
2. Implement natural language query parser
3. Add fuzzy matching and similarity detection
4. Create faceted search capabilities
5. Integrate advanced search into CLI

### Recent Phase 2 Features
- BibEntry model with manipulation methods
- Repository pattern with atomic operations and dry-run
- Query builder for flexible searching
- Interactive CRUD operations with rich UI
- All operations maintain repository correctness

### Dependencies
Defined in `manifest.scm`:
- python3, python-bibtexparser, python-click
- python-rich for terminal UI and formatting
- python-ruff for linting and formatting
- node-pyright for type checking
- python-lsp-server for editor LSP support

### Code Standards
- Python 3.11+ with full type hints
- Ruff and pyright compliant
- Click-based CLI with subcommands
- Dataclasses for models