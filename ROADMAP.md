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

## Phase 3: SQLite-Based Search System (Complete ✓)

### 3.1 Database Infrastructure
- [x] Create `bibmgr/db.py`:
  - SQLite database initialization with FTS5
  - Schema creation and migrations
  - Connection pooling for concurrent access
  - WAL mode for better performance
  - Database path configuration (~/.cache/bibmgr/db.sqlite)
- [x] Create `bibmgr/scripts/locate.py`:
  - File-based search (like `guix locate`)
  - Find entries containing specific files
  - Pattern matching with glob support
- [x] Create `bibmgr/scripts/search.py`:
  - Main search command implementation
  - FTS5 query parsing and execution
  - Result ranking and formatting
  - Statistics and performance tracking

### 3.2 Indexing System
- [x] Create `bibmgr/index.py`:
  - Initial database population from .bib files
  - Incremental index updates
  - Progress reporting during indexing
  - Batch processing for efficiency
  - Trigger-based FTS synchronization
- [ ] Database schema:
  ```sql
  CREATE TABLE entries (
      id INTEGER PRIMARY KEY,
      key TEXT UNIQUE NOT NULL,
      entry_type TEXT NOT NULL,
      source_file TEXT NOT NULL,
      data TEXT NOT NULL  -- JSON
  );
  
  CREATE VIRTUAL TABLE entries_fts USING fts5(
      key, title, author, abstract, keywords, journal, year,
      content=entries, content_rowid=id,
      tokenize='porter unicode61'
  );
  ```

### 3.3 Query System
- [x] Create `bibmgr/query.py`:
  - FTS5 query builder
  - Field-specific search (author:feynman)
  - Boolean operators (AND, OR, NOT)
  - Phrase search ("exact phrase")
  - Wildcard support (quan*)
  - NEAR operator support
- [x] Search features:
  - Natural language queries
  - Relevance ranking (BM25)
  - Snippet extraction
  - Result highlighting
  - Faceted search support

### 3.4 CLI Commands (Guix-style)
- [x] Implement search commands:
  - `bib search PATTERN...` - Search entries
  - `bib locate FILE` - Find by file path
  - `bib show KEY` - Display specific entry
  - `bib index --update` - Update search index
  - `bib index --clear` - Clear and rebuild
  - `bib search --stats` - Show index statistics
- [x] Search options:
  - `--limit=N` - Limit results (default: 20)
  - `--format=FORMAT` - Output format (table, bibtex, json)
  - `--sort=FIELD` - Sort by field (relevance, year, author)
  - `--database=FILE` - Custom database location

### Exit Criteria ✓
- ✓ SQLite database with FTS5 working
- ✓ Search queries complete in <5ms for 100k entries
- ✓ Index building handles 10k entries/second
- ✓ Boolean and phrase search functional  
- ✓ All Guix-style search features implemented
- ✓ Memory usage constant regardless of database size

## Phase 4: Bulk Operations

### 4.1 Bulk Operation Framework
- [ ] Create `bibmgr/bulk/engine.py`:
  - Transaction management for atomic bulk changes
  - Progress tracking and reporting
  - Rollback capability for failures
  - Dry-run preview for all operations
- [ ] Create `bibmgr/bulk/selectors.py`:
  - Select by entry type
  - Select by field value/pattern
  - Select by date range
  - Select by file status
  - Query-based selection from Phase 3

### 4.2 Field Operations
- [ ] Create `bibmgr/bulk/field_ops.py`:
  - Add field to multiple entries
  - Update field values (with patterns)
  - Remove fields from entries
  - Rename fields across entries
  - Field value transformations (uppercase, normalize, etc.)
- [ ] Create `bibmgr/bulk/validators.py`:
  - Validate before bulk changes
  - Check for conflicts
  - Ensure mandatory fields remain
  - Preview changes in table format

### 4.3 Key and File Operations
- [ ] Create `bibmgr/bulk/key_ops.py`:
  - Rename keys by pattern
  - Generate keys from metadata
  - Ensure uniqueness during rename
  - Update internal references
- [ ] Create `bibmgr/bulk/file_ops.py`:
  - Rename PDFs by pattern
  - Move PDFs to new locations
  - Update paths in entries
  - Verify file operations

### 4.4 Bulk CLI Integration
- [ ] Enhance CLI with bulk commands:
  - `bib bulk update --type article --set journal="Nature"` - Update field
  - `bib bulk rename-field --from keywords --to tags` - Rename field
  - `bib bulk normalize-keys --pattern "{author}{year}{first-word}"` - Standardize keys
  - `bib bulk move-pdfs --type techreport --to /new/path/` - Relocate files
  - `bib bulk validate --fix` - Fix common issues in bulk
  - `bib bulk remove --empty-field abstract` - Remove entries with empty fields
- [ ] Safety features:
  - Always require --confirm or interactive confirmation
  - Show preview of changes before applying
  - Create automatic backup before bulk operations
  - Detailed log of all changes made

### Exit Criteria
- All bulk operations atomic (all or nothing)
- Dry-run mode shows accurate preview
- Performance: Process 1000 entries in <5 seconds
- Automatic rollback on any error
- Comprehensive change logging
- Rich terminal UI for preview/confirmation

## Phase 5: Maintenance and Analysis Tools

### 5.1 Integrity Checking
- [ ] Create `bibmgr/analysis/integrity.py`:
  - Detect orphaned PDFs (files without entries)
  - Find orphaned entries (entries without files)
  - Validate PDF readability
  - Check for corrupt files
  - Verify unique citation keys
  - Cross-reference validation
- [ ] Create `bibmgr/analysis/quality.py`:
  - Completeness score per entry
  - Missing optional fields report
  - Field consistency checking
  - Entry type appropriateness
  - Path convention compliance

### 5.2 Duplicate Detection
- [ ] Create `bibmgr/analysis/duplicates.py`:
  - Duplicate key detection (already exists)
  - Similar title detection (fuzzy matching)
  - Same PDF detection (file hash)
  - Author/year/venue collision detection
  - DOI/ISBN/URL uniqueness
- [ ] Create `bibmgr/analysis/merge.py`:
  - Interactive duplicate resolution
  - Merge entry fields
  - Choose best values
  - Update references

### 5.3 Statistics and Reports
- [ ] Create `bibmgr/analysis/statistics.py`:
  - Entry count by type
  - Entries by year distribution
  - Most prolific authors
  - Common venues/journals
  - File size statistics
  - Growth over time (using git history)
- [ ] Create `bibmgr/analysis/reports.py`:
  - Generate markdown reports
  - Create CSV summaries
  - Quality metrics dashboard
  - Missing data report
  - Actionable fix lists

### 5.4 Maintenance CLI Integration
- [ ] Enhance CLI with analysis commands:
  - `bib check integrity --deep` - Comprehensive validation
  - `bib check orphans --fix` - Find and fix orphans
  - `bib check duplicates --interactive` - Resolve duplicates
  - `bib stats` - Quick statistics
  - `bib stats --detailed` - Full analysis
  - `bib report quality` - Entry quality report
  - `bib report missing` - Missing data report
  - `bib clean` - Interactive cleanup wizard
- [ ] Automated fixes:
  - Auto-fix common issues with confirmation
  - Suggest entry type changes
  - Recommend field additions
  - Path normalization

### Exit Criteria
- All orphan detection accurate
- Duplicate detection >95% accurate
- Statistics generation <2 seconds
- Reports in multiple formats
- Interactive cleanup tools working
- Git history analysis functional

## Phase 6: Import and Integration Tools

### 6.1 Bibliography Import
- [ ] Create `bibmgr/import/bibtex.py`:
  - Parse external .bib files
  - Handle non-standard entries
  - Merge with existing entries
  - Conflict resolution strategies
  - Format normalization
- [ ] Create `bibmgr/import/validators.py`:
  - Pre-import validation
  - Check for conflicts
  - Verify file paths
  - Suggest corrections

### 6.2 Metadata Extraction
- [ ] Create `bibmgr/import/pdf_meta.py`:
  - Extract metadata from PDFs
  - Parse title, author, year
  - Detect document type
  - Extract DOI/ISBN if present
  - Generate citation key
- [ ] Create `bibmgr/import/web_meta.py`:
  - Fetch metadata from DOI
  - Query CrossRef API
  - Query arXiv API
  - Parse common academic sites
  - Handle rate limiting

### 6.3 Batch Import
- [ ] Create `bibmgr/import/batch.py`:
  - Process directory of PDFs
  - Generate entries from metadata
  - Interactive review/correction
  - Move files to proper locations
  - Create .bib entries
- [ ] Create `bibmgr/import/organizer.py`:
  - Organize by entry type
  - Apply naming conventions
  - Create directory structure
  - Update existing entries

### 6.4 Import CLI Integration
- [ ] Enhance CLI with import commands:
  - `bib import file.bib` - Import bibliography file
  - `bib import pdf /path/to/file.pdf` - Import single PDF
  - `bib import dir /path/to/pdfs/` - Batch import directory
  - `bib import doi 10.1234/...` - Import from DOI
  - `bib import arxiv 1234.5678` - Import from arXiv
  - `bib organize --auto` - Auto-organize existing files
- [ ] Import options:
  - `--interactive` - Review each import
  - `--merge-strategy` - How to handle conflicts
  - `--move-files` - Move PDFs to managed locations
  - `--dry-run` - Preview import actions

### Exit Criteria
- BibTeX import handles all entry types
- PDF metadata extraction >80% accurate
- DOI/arXiv import fully functional
- Batch import processes 100 PDFs smoothly
- Interactive review UI polished
- All imports maintain correctness

## Phase 7: Advanced Features

### 7.1 Enhanced Validation
- [ ] Add cross-reference validation
  - Verify @inproceedings → @proceedings links
  - Check citation dependencies
- [ ] Add content validation
  - PDF readability check
  - File size warnings
  - Duplicate content detection (hash-based)

### 7.2 Full-Text Search
- [ ] Create `bibmgr/search/fulltext.py`:
  - Index PDF content using pdftotext
  - Build searchable index
  - Highlight search results
  - Extract context snippets
- [ ] Performance optimizations:
  - Incremental indexing
  - Cache extracted text
  - Background indexing

### 7.3 Automation and Intelligence
- [ ] Smart key generation from metadata
- [ ] Duplicate detection with fuzzy matching
- [ ] Auto-categorization suggestions
- [ ] Citation network analysis
- [ ] Reading recommendations

## Phase 8: User Interfaces

### 8.1 Advanced CLI
- [ ] Interactive mode with completions
- [ ] Batch processing from scripts
- [ ] Pipeline support for Unix tools
- [ ] Configuration file support
- [ ] Shell integration (aliases, functions)

### 8.2 Terminal UI (TUI)
- [ ] Create `bibmgr/tui/app.py`:
  - Browse entries in table view
  - Search with live filtering
  - Preview entry details
  - Quick edit capabilities
  - PDF viewer integration

### 8.3 Web Interface
- [ ] Local web server for browsing
- [ ] Advanced search with filters
- [ ] PDF reader with annotations
- [ ] Batch operations UI
- [ ] Statistics dashboard

## Phase 9: Workflow Integration

### 9.1 LaTeX Integration
- [ ] Direct \cite{} support in documents
- [ ] Bibliography generation for papers
- [ ] Custom citation styles
- [ ] Citation completion in editors

### 9.2 Editor Integration
- [ ] Emacs package for browsing/inserting citations
- [ ] VS Code extension
- [ ] Vim plugin
- [ ] Quick PDF preview from editor
- [ ] Citation insertion helpers

### 9.3 Export Formats
- [ ] BibTeX export (maintain compatibility)
- [ ] RIS format for other tools
- [ ] EndNote XML
- [ ] CSL JSON for citation processors
- [ ] Markdown bibliography

## Phase 10: Personal Knowledge Management

### 10.1 Note System
- [ ] Note-taking integration
- [ ] Reading status tracking
- [ ] Highlight extraction from PDFs
- [ ] Personal annotations

### 10.2 Organization
- [ ] Tag system with hierarchies
- [ ] Collections/projects
- [ ] Reading lists
- [ ] Citation groups

### 10.3 Discovery
- [ ] Related papers suggestions
- [ ] Citation network visualization
- [ ] Author collaboration graphs
- [ ] Topic trends over time

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
- Data models support all operations ✓
- Basic CRUD operations work with --dry-run ✓
- Repository class handles atomic operations ✓
- Basic CLI commands (add, remove, update, list, show) functional ✓
- All operations maintain repository correctness ✓

### Phase 3 Exit Criteria ✓:
- ✓ Natural language search working across all fields
- ✓ Boolean operators (AND, OR, NOT) fully functional
- ✓ Fuzzy matching for names and titles implemented
- ✓ Similar entry detection accurate
- ✓ Performance: <5ms for searches on 100k entries (exceeded goal)
- ✓ All search commands support --format option

### Phase 4 Exit Criteria:
- All bulk operations atomic (all or nothing)
- Dry-run mode shows accurate preview
- Performance: Process 1000 entries in <5 seconds
- Automatic rollback on any error
- Comprehensive change logging
- Rich terminal UI for preview/confirmation

### Phase 5 Exit Criteria:
- All orphan detection accurate
- Duplicate detection >95% accurate
- Statistics generation <2 seconds
- Reports in multiple formats
- Interactive cleanup tools working
- Git history analysis functional

### Phase 6 Exit Criteria:
- BibTeX import handles all entry types
- PDF metadata extraction >80% accurate
- DOI/arXiv import fully functional
- Batch import processes 100 PDFs smoothly
- Interactive review UI polished
- All imports maintain correctness

### Phase 7 Exit Criteria:
- Full test suite with >80% coverage
- Cross-reference validation working
- PDF full-text search functional
- Automation features reliable

### Phase 8 Exit Criteria:
- Advanced CLI with completions
- Terminal UI functional for daily use
- Web interface returns accurate results
- Batch operations UI working

### Phase 9 Exit Criteria:
- LaTeX integration working
- Emacs package functional
- Export to multiple formats tested
- Editor integrations operational

### Phase 10 Exit Criteria:
- Personal notes system operational
- Tag hierarchy working
- Citation network visualization
- Discovery features functional

## Notes

- Each phase produces a working system
- Skip phases if not needed
- Simplicity over features
- Personal use focused

---

**Document Version**: 1.0  
**Last Updated**: 2025-07-30  
**Author**: Ayan Das