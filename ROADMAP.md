# Bibliography Management System - Implementation Roadmap

## Overview
Phased implementation plan for the bibliography management system. Each phase builds upon the previous, ensuring a working system at every stage.

## Core Principles
1. **Correctness First**: Repository maintains validity at all times
2. **Test with Real Data**: Use existing BibTeX files with known issues to drive development
3. **Safe Operations**: All tools support --dry-run mode
4. **Fix Then Commit**: BibTeX files only committed after all tooling complete and issues resolved

## Phase 1: Core Infrastructure

### 1.1 Repository Structure Setup
- [x] Create directory structure:
  ```bash
  mkdir -p bibtex/{by-subject,by-type}
  mkdir -p scripts/{validate,import,export,maintenance}
  mkdir -p {hooks,config,docs,tests,tools}
  ```
- [x] Move existing .bib files to appropriate directories under `bibtex/`
- [ ] Create `.gitignore` with appropriate patterns
- [ ] Create `manifest.scm` for Guix dependencies
- [ ] Create initial `README.md` with setup instructions

### 1.2 Basic Validation Framework
- [ ] Create `scripts/validate/check_paths.py`
  - Verify all file paths exist
  - Report missing files with line numbers
  - Exit with error code for CI integration
- [ ] Create `scripts/validate/check_duplicates.py`
  - Check for duplicate citation keys
  - Check for duplicate file paths
  - Suggest resolution strategies
- [ ] Create `scripts/validate/check_mandatory_fields.py`
  - Validate required fields per entry type
  - Report incomplete entries

### 1.3 Git Hooks Integration
- [ ] Create `hooks/pre-commit` script:
  ```bash
  #!/bin/bash
  python3 scripts/validate/check_paths.py || exit 1
  python3 scripts/validate/check_duplicates.py || exit 1
  ```
- [ ] Create `hooks/install.sh` for easy setup
- [ ] Document hook installation in README

### 1.4 Configuration Framework
- [ ] Create `config/validation_rules.yaml`:
  ```yaml
  mandatory_fields:
    article: [author, title, journal, year]
    book: [author, title, publisher, year]
    # ... etc
  ```
- [ ] Create `config/naming_rules.yaml` for PDF naming conventions
- [ ] Create configuration parser in Python

## Phase 2: Core Data Layer

### 2.1 Data Models and Abstractions
- [ ] Create `bibmgr/models.py` enhancements:
  - Entry manipulation methods (update fields, validate)
  - Path manipulation utilities
  - Entry comparison and merging
- [ ] Create `bibmgr/repository.py`:
  - Load/save .bib files with preservation of formatting
  - Transaction support for atomic operations
  - Change tracking for --dry-run mode
- [ ] Create `bibmgr/query.py`:
  - Simple field-based queries
  - Query builder pattern
  - Result filtering and sorting

### 2.2 Basic CRUD Operations
- [ ] Create `bibmgr/operations/add.py`:
  - Add single entry with validation
  - Support --dry-run mode
  - Automatic key generation option
  - Path validation before commit
- [ ] Create `bibmgr/operations/remove.py`:
  - Remove entry and optionally PDF
  - Support --dry-run mode
  - Orphan warnings
- [ ] Create `bibmgr/operations/update.py`:
  - Update entry fields
  - Move/rename PDF with path update
  - Support --dry-run mode

### 2.3 Basic CLI Foundation
- [ ] Enhance `bibmgr/cli.py`:
  - `bib add` - Interactive entry creation
  - `bib remove <key>` - Remove entry
  - `bib update <key>` - Update entry fields
  - `bib show <key>` - Display entry details
  - `bib list [--type TYPE]` - List entries
  - All commands support --dry-run

## Phase 3: Higher-Level Operations

### 3.1 Enhanced Search and Query
- [ ] Create `bibmgr/search.py`:
  - Multi-field search
  - Boolean operators (AND, OR, NOT)
  - Fuzzy matching for author names
  - Search result ranking
- [ ] Add to CLI:
  - `bib search <query>` - Full search
  - `bib find --author "Name"` - Field search
  - `bib similar <key>` - Find similar entries

### 3.2 Bulk Operations
- [ ] Create `bibmgr/operations/bulk.py`:
  - Bulk field updates
  - Batch validation
  - Mass renaming with patterns
- [ ] Add to CLI:
  - `bib bulk-update --type article --set journal="Nature"`
  - `bib validate --fix-paths` - Fix common issues
  - `bib normalize-keys` - Standardize citation keys

### 3.3 Import/Export Foundation
- [ ] Create `bibmgr/io/bibtex_parser.py`:
  - Robust BibTeX parsing with error recovery
  - Format preservation for round-trip editing
  - Comment and preamble handling
- [ ] Create `bibmgr/io/formats.py`:
  - JSON export with schema
  - CSV export with configurable fields
  - Simple HTML export
- [ ] Add to CLI:
  - `bib import <file.bib>` - Import entries
  - `bib export --format json` - Export data

### 3.4 Maintenance Tools
- [ ] Create `bibmgr/maintenance/orphans.py`:
  - Find PDFs without entries
  - Find entries without PDFs
  - Generate actionable reports
- [ ] Create `bibmgr/maintenance/integrity.py`:
  - Deep validation beyond mandatory fields
  - Cross-reference checking
  - Duplicate content detection (by title similarity)
- [ ] Add to CLI:
  - `bib check orphans` - Find mismatches
  - `bib check integrity` - Deep validation
  - `bib stats` - Collection statistics

## Phase 4: Import/Export Utilities

### 4.1 Advanced Import Tools
- [ ] Create `scripts/import/from_pdf_metadata.py`
  - Extract metadata from PDF files
  - Generate BibTeX entries
  - Suggest appropriate entry types
- [ ] Create `scripts/import/from_doi.py`
  - Fetch metadata from DOI
  - Generate complete BibTeX entry
  - Download PDF if available
- [ ] Create `scripts/import/bulk_import.py`
  - Process directory of PDFs
  - Generate .bib file
  - Move files to correct locations

### 4.2 Advanced Export Tools
- [ ] Create `scripts/export/to_website.py`
  - Static site generation
  - Search functionality
  - PDF viewer integration
- [ ] Create `scripts/export/to_citations.py`
  - Format for various citation styles
  - LaTeX bibliography generation
  - Word/LibreOffice compatible formats

### 4.3 External Tool Integration
- [ ] Create `scripts/integrate/zotero_sync.py`
  - Import from Zotero
  - Maintain sync state
- [ ] Create `scripts/integrate/mendeley_import.py`
  - One-time Mendeley import
  - Preserve annotations

## Phase 5: Advanced Features

### 5.1 Enhanced Validation
- [ ] Add cross-reference validation
  - Verify @inproceedings → @proceedings links
  - Check citation dependencies
- [ ] Add content validation
  - PDF readability check
  - File size warnings
  - Duplicate content detection (hash-based)

### 5.2 Advanced Search
- [ ] Full-text PDF search
  - Index PDF content
  - Highlight search results
  - Extract context

### 5.3 Automation and Intelligence
- [ ] Smart key generation from metadata
- [ ] Duplicate detection with fuzzy matching
- [ ] Auto-categorization suggestions
- [ ] Citation network analysis

## Phase 6: User Interfaces

### 6.1 Advanced CLI
- [ ] Interactive mode with completions
- [ ] Batch processing from scripts
- [ ] Pipeline support for Unix tools
- [ ] Configuration file support

### 6.2 Web Interface
- [ ] Local web server for browsing
- [ ] Advanced search with filters
- [ ] PDF reader with annotations
- [ ] Batch operations UI

## Phase 7: Workflow Integration

### 7.1 LaTeX Integration
- [ ] Direct \cite{} support in documents
- [ ] Bibliography generation for papers
- [ ] Custom citation styles

### 7.2 Editor Integration
- [ ] Emacs package for browsing/inserting citations
- [ ] VS Code extension
- [ ] Vim plugin
- [ ] Quick PDF preview from editor

### 7.3 Personal Knowledge Management
- [ ] Note-taking integration
- [ ] Reading status tracking
- [ ] Tag system with hierarchies
- [ ] Related papers suggestions

## Development Approach

### Known Issues (Driving Test Cases)
Current BibTeX files have these validation errors:
1. **Duplicate Keys** (3): Between coursework-homework.bib and coursework-solutions.bib
2. **Missing Fields** (4): Technical standards missing author field

These issues remain unfixed to:
- Test validation tools during development
- Ensure tools can detect real problems
- Demonstrate fix capabilities when complete

### Commit Strategy
1. Infrastructure and tooling committed immediately
2. BibTeX files remain uncommitted during Phase 1
3. Final Phase 1 task: Fix all issues and commit clean .bib files
4. This demonstrates the complete toolchain working correctly

## Success Metrics

### Phase 1 Exit Criteria:
- All validation tools complete with --dry-run support
- Tools successfully identify all known issues:
  - 3 duplicate keys between homework/solutions
  - 4 technical standards missing author field
- Git hooks prevent invalid commits
- Core documentation complete
- BibTeX files fixed and committed as demonstration

### Phase 2 Exit Criteria:
- Data models support all operations
- Basic CRUD operations work with --dry-run
- Repository class handles atomic operations
- Basic CLI commands (add, remove, update, list, show) functional
- All operations maintain repository correctness

### Phase 3 Exit Criteria:
- Search supports multi-field and boolean queries
- Bulk operations work reliably
- Import/export to JSON and CSV functional
- Orphan detection accurate
- Basic maintenance tools operational

### Phase 4 Exit Criteria:
- Import from PDF metadata functional
- DOI import working
- Static website generation works
- External tool integration tested
- Bulk import processes directories correctly

### Phase 5 Exit Criteria:
- Full test suite with >80% coverage
- Cross-reference validation working
- PDF full-text search functional
- Automation features reliable

### Phase 6 Exit Criteria:
- Advanced CLI with completions
- Web interface functional for daily use
- Search returns accurate results
- Batch operations UI working

### Phase 7 Exit Criteria:
- LaTeX integration working
- Emacs package functional
- Personal notes system operational
- Editor integrations tested

## Notes

- Each phase produces a working system
- Skip phases if not needed
- Simplicity over features
- Personal use focused

---

**Document Version**: 1.0  
**Last Updated**: 2025-07-30  
**Author**: Ayan Das