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

## Phase 2: Core Data Layer (Complete ✓)

### 2.1 Data Models and Abstractions
- [x] Enhanced bibmgr/models.py:
  - [x] Entry manipulation methods (update fields, validate)
  - [x] Path manipulation utilities
  - [x] Entry comparison and merging
- [x] Created bibmgr/repository.py:
  - [x] Load/save .bib files with format preservation
  - [x] Transaction support for atomic operations
  - [x] Change tracking for --dry-run mode
- [x] Created bibmgr/query.py:
  - [x] Simple field-based queries
  - [x] Query builder pattern
  - [x] Result filtering and sorting

### 2.2 Basic CRUD Operations
- [x] Created bibmgr/operations/add.py:
  - [x] Add single entry with validation
  - [x] Support --dry-run mode
  - [x] Automatic key generation option
  - [x] Path validation before commit
- [x] Created bibmgr/operations/remove.py:
  - [x] Remove entry and optionally PDF
  - [x] Support --dry-run mode
  - [x] Orphan warnings
- [x] Created bibmgr/operations/update.py:
  - [x] Update entry fields
  - [x] Move/rename PDF with path update
  - [x] Support --dry-run mode

### 2.3 Basic CLI Foundation
- [x] Enhanced bibmgr/cli.py:
  - [x] `bib add` - Interactive entry creation
  - [x] `bib remove <key>` - Remove entry
  - [x] `bib update <key>` - Update entry fields
  - [x] `bib show <key>` - Display entry details
  - [x] `bib list [--type TYPE]` - List entries
  - [x] All commands support --dry-run

## Phase 3: SQLite-Based Search System (Complete ✓)

### 3.1 Database Infrastructure
- [x] Create bibmgr/db.py:
  - [x] BibliographyDB class with SQLite/FTS5
  - [x] Schema creation with entries and entries_fts tables
  - [x] Connection pooling and WAL mode
  - [x] Database path: ~/.cache/bibmgr/db.sqlite
  - [x] Migration support for schema updates
- [x] Create bibmgr/scripts/search.py:
  - [x] Search command implementation (Guix-style)
  - [x] FTS5 query execution
  - [x] Result formatting (table, bibtex, json)
  - [x] Performance statistics
- [x] Create bibmgr/scripts/locate.py:
  - [x] File-based search (like `guix locate`)
  - [x] Find entries by PDF path
  - [x] Glob pattern support

### 3.2 Indexing System
- [x] Create bibmgr/index.py:
  - [x] Build initial index from .bib files
  - [x] Incremental updates for changes
  - [x] Progress reporting (like Guix)
  - [x] Batch processing (1000 entries at a time)
  - [x] JSON serialization of fields
- [x] Implement FTS5 triggers:
  - [x] After INSERT trigger
  - [x] After UPDATE trigger
  - [x] After DELETE trigger

### 3.3 Query System
- [x] Enhanced bibmgr/query.py:
  - [x] FTS5 query builder
  - [x] Field-specific search (author:feynman)
  - [x] Boolean operators (AND, OR, NOT)
  - [x] Phrase search ("exact phrase")
  - [x] Wildcard support (quan*)
  - [x] NEAR operator

### 3.4 CLI Commands
- [x] Implement search commands:
  - [x] `bib search PATTERN...` - Search entries
  - [x] `bib locate FILE` - Find by file path
  - [x] `bib show KEY` - Display specific entry
  - [x] `bib index --update` - Update search index
  - [x] `bib index --clear` - Clear and rebuild
  - [x] `bib search --stats` - Show statistics
- [x] Search options:
  - [x] --limit=N (default: 20)
  - [x] --format=FORMAT (table, bibtex, json)
  - [x] --sort=FIELD (relevance, year, author)
  - [x] --database=FILE (custom location)

## Phase 4: Bulk Operations (Next)

### 4.1 Bulk Operation Framework
- [ ] Create bibmgr/bulk/engine.py:
  - [ ] Transaction management
  - [ ] Progress tracking
  - [ ] Rollback capability
  - [ ] Dry-run preview

### 4.2 Field Operations
- [ ] Create bibmgr/bulk/field_ops.py:
  - [ ] Add field to multiple entries
  - [ ] Update field values
  - [ ] Remove fields
  - [ ] Field transformations

### 4.3 Key and File Operations
- [ ] Create bibmgr/bulk/key_ops.py:
  - [ ] Rename keys by pattern
  - [ ] Generate keys from metadata
  - [ ] Ensure uniqueness
- [ ] Create bibmgr/bulk/file_ops.py:
  - [ ] Rename PDFs by pattern
  - [ ] Move PDFs to new locations
  - [ ] Update paths in entries

### 4.4 Bulk CLI Integration
- [ ] `bib bulk update --type article --set journal="Nature"`
- [ ] `bib bulk rename-field --from keywords --to tags`
- [ ] `bib bulk normalize-keys --pattern "{author}{year}{first-word}"`
- [ ] `bib bulk move-pdfs --type techreport --to /new/path/`

## Phase 5: Maintenance and Analysis Tools (Future)

### 5.1 Integrity Checking
- [ ] Create bibmgr/analysis/integrity.py
- [ ] Create bibmgr/analysis/quality.py
- [ ] Orphan detection
- [ ] PDF validation

### 5.2 Duplicate Detection
- [ ] Create bibmgr/analysis/duplicates.py
- [ ] Create bibmgr/analysis/merge.py
- [ ] Title similarity detection
- [ ] File hash comparison

### 5.3 Statistics and Reports
- [ ] Create bibmgr/analysis/statistics.py
- [ ] Create bibmgr/analysis/reports.py
- [ ] Entry distributions
- [ ] Quality metrics

## Phase 6: Import and Integration Tools

### 6.1 Bibliography Import
- [ ] Create bibmgr/import/bibtex.py
- [ ] Handle non-standard entries
- [ ] Conflict resolution

### 6.2 Metadata Extraction
- [ ] Create bibmgr/import/pdf_meta.py
- [ ] Create bibmgr/import/web_meta.py
- [ ] DOI and arXiv support

### 6.3 Batch Import
- [ ] Create bibmgr/import/batch.py
- [ ] Interactive review
- [ ] Auto-organization

## Phase 7+: Advanced Features
(See ROADMAP.md for Phases 7-10)

## Development Status

### Working Components
- Phase 1 ✓: Complete validation framework with Git hooks
- Phase 2 ✓: Full CRUD operations with 423 tests passing (90%+ coverage)
- Phase 3 ✓: SQLite-based search system with FTS5
  - `python3 -m bibmgr.cli search quantum computing` - Natural language search
  - `python3 -m bibmgr.cli locate file.pdf` - File-based search (Guix-style)
  - `python3 -m bibmgr.cli index build` - Search index management
  - `python3 -m bibmgr.cli stats` - Database statistics

### Repository State
- Infrastructure committed (manifest.scm, pyproject.toml, etc.)
- Python package committed (bibmgr/) with comprehensive test suite
- Documentation committed (docs/design.md, ROADMAP.md, etc.)
- Phase 3 search implementation committed
- BibTeX files committed and validated (0 validation errors)

## Completed

- [x] System design document (docs/design.md)
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