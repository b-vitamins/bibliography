# Bibliography Management System - TODO

## Phase 1: Core Infrastructure (Complete ✓)

### 1.1 Repository Setup
- [x] Create directory structure (bibtex/by-subject, bibtex/by-type)
- [x] Move refs/*.bib files to bibtex/ organized by type/subject
- [x] Create .gitignore file
- [x] Create manifest.scm for dependencies
- [x] Create initial README.md

### 1.2 Validation Framework
- [x] Create unified CLI tool with check subcommands
- [x] Implement path validation (0 errors found)
- [x] Implement duplicate detection (3 errors found ✓)
- [x] Implement mandatory field validation (4 errors found ✓)
- [x] Test on existing 194 PDF references
- [x] Create validation report generator with detailed context
- [x] Fix all validation errors (7 total)
- [x] Commit clean .bib files

### 1.3 Git Integration
- [x] Set up comprehensive Git hooks system
- [x] Create hooks/install.sh
- [x] Test hooks prevent invalid commits
- [x] Document hooks in README and hooks/README.md
- [x] Add changelog enforcement
- [x] Add quality metrics and security scanning

### 1.4 Testing
- [x] Create test suite structure
- [x] Add validator tests
- [x] Ensure tests pass in pre-push hook

## Phase 2: Core Data Layer (Current)

### 2.1 Data Models and Abstractions
- [ ] Enhance bibmgr/models.py:
  - [ ] Entry manipulation methods (update fields, validate)
  - [ ] Path manipulation utilities
  - [ ] Entry comparison and merging
- [ ] Create bibmgr/repository.py:
  - [ ] Load/save .bib files with format preservation
  - [ ] Transaction support for atomic operations
  - [ ] Change tracking for --dry-run mode
- [ ] Create bibmgr/query.py:
  - [ ] Simple field-based queries
  - [ ] Query builder pattern
  - [ ] Result filtering and sorting

### 2.2 Basic CRUD Operations
- [ ] Create bibmgr/operations/add.py:
  - [ ] Add single entry with validation
  - [ ] Support --dry-run mode
  - [ ] Automatic key generation option
  - [ ] Path validation before commit
- [ ] Create bibmgr/operations/remove.py:
  - [ ] Remove entry and optionally PDF
  - [ ] Support --dry-run mode
  - [ ] Orphan warnings
- [ ] Create bibmgr/operations/update.py:
  - [ ] Update entry fields
  - [ ] Move/rename PDF with path update
  - [ ] Support --dry-run mode

### 2.3 Basic CLI Foundation
- [ ] Enhance bibmgr/cli.py:
  - [ ] `bib add` - Interactive entry creation
  - [ ] `bib remove <key>` - Remove entry
  - [ ] `bib update <key>` - Update entry fields
  - [ ] `bib show <key>` - Display entry details
  - [ ] `bib list [--type TYPE]` - List entries
  - [ ] All commands support --dry-run

## Phase 3: Higher-Level Operations (Next)

### 3.1 Enhanced Search and Query
- [ ] Create bibmgr/search.py
- [ ] Add multi-field search
- [ ] Add boolean operators
- [ ] Add fuzzy matching

### 3.2 Bulk Operations
- [ ] Create bibmgr/operations/bulk.py
- [ ] Add bulk field updates
- [ ] Add batch validation
- [ ] Add mass renaming

### 3.3 Import/Export Foundation
- [ ] Create bibmgr/io/bibtex_parser.py
- [ ] Create bibmgr/io/formats.py
- [ ] Add JSON/CSV export
- [ ] Add simple HTML export

### 3.4 Maintenance Tools
- [ ] Create bibmgr/maintenance/orphans.py
- [ ] Create bibmgr/maintenance/integrity.py
- [ ] Add orphan detection
- [ ] Add deep validation

## Phase 4: Import/Export Utilities (Future)

### 4.1 Advanced Import
- [ ] PDF metadata extraction
- [ ] DOI lookup and import
- [ ] Bulk PDF import

### 4.2 Advanced Export
- [ ] Static website generation
- [ ] Citation formatting
- [ ] LaTeX bibliography generation

## Phase 5: Advanced Features

### 5.1 Enhanced Validation
- [ ] Cross-reference validation
- [ ] PDF content validation
- [ ] Duplicate detection by content

### 5.2 Advanced Search
- [ ] Full-text PDF search
- [ ] Search result highlighting
- [ ] Context extraction

## Phase 6: User Interfaces

### 6.1 Advanced CLI
- [ ] Interactive mode
- [ ] Shell completions
- [ ] Configuration files

### 6.2 Web Interface
- [ ] Local web server
- [ ] Advanced search UI
- [ ] PDF reader integration

## Phase 7: Workflow Integration

### 7.1 LaTeX Integration
- [ ] Direct \cite{} support
- [ ] Bibliography generation
- [ ] Custom citation styles

### 7.2 Editor Integration
- [ ] Emacs package
- [ ] VS Code extension
- [ ] Vim plugin

## Development Status

### Working Components
- `./bib check all` - Identifies all 7 known issues correctly
- `./bib check paths` - No missing files
- `./bib check duplicates` - Finds 3 duplicate keys
- `./bib check fields` - Finds 4 missing fields

### Repository State
- Infrastructure committed (manifest.scm, pyproject.toml, etc.)
- Python package committed (bibmgr/)
- Documentation committed (DESIGN.md, ROADMAP.md, etc.)
- **BibTeX files uncommitted** - waiting for fix tools

## Completed

- [x] System design document (DESIGN.md)
- [x] Implementation roadmap (ROADMAP.md)
- [x] Reorganized 194 PDFs by BibTeX entry type
- [x] Updated all .bib file paths
- [x] Validated all file references
- [x] Moved PDFs to correct directories:
  - 189 files → /home/b/documents/misc/
  - 4 files → /home/b/documents/techreport/
  - 1 file → /home/b/documents/phdthesis/
- [x] Created bibtex directory structure
- [x] Moved 13 .bib files to bibliography repo:
  - 3 files → bibtex/by-subject/
  - 10 files → bibtex/by-type/

## Notes

- Current: 194 PDFs organized, .bib files moved to repository
- Priority: Validation framework to maintain integrity
- Decision needed: Version control for PDFs or metadata only?

## Quick Commands

```bash
# Check PDF count
find /home/b/documents -name "*.pdf" -type f | wc -l

# List .bib files in repository
find /home/b/projects/bibliography/bibtex -name "*.bib" | wc -l

# Run validation (after implementation)
python3 scripts/validate/checkpaths.py
```