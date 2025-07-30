# Bibliography Management System - Implementation Roadmap

## Overview
Phased implementation plan for the bibliography management system. Each phase builds upon the previous, ensuring a working system at every stage.

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

## Phase 2: Import/Export Utilities

### 2.1 Import Tools
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

### 2.2 Export Tools
- [ ] Create `scripts/export/to_json.py`
  - Export for web applications
  - Include file paths and metadata
- [ ] Create `scripts/export/to_csv.py`
  - Tabular format for spreadsheets
  - Configurable column selection
- [ ] Create `scripts/export/generate_index.py`
  - Create HTML index of all entries
  - Include links to PDFs

### 2.3 Quality of Life Scripts
- [ ] Create `scripts/maintenance/find_orphans.py`
  - Find PDFs without .bib entries
  - Find .bib entries without PDFs
- [ ] Create `scripts/maintenance/generate_stats.py`
  - Entry count by type
  - Year distribution
  - Author frequency

## Phase 3: Advanced Features

### 3.1 Enhanced Validation
- [ ] Add cross-reference validation
  - Verify @inproceedings → @proceedings links
  - Check citation dependencies
- [ ] Add content validation
  - PDF readability check
  - File size warnings
  - Duplicate content detection (hash-based)

### 3.2 Search and Query Tools
- [ ] Create `scripts/search.py`
  - Full-text search in metadata
  - RegEx support
  - Field-specific queries
  - Output formatting options

### 3.3 Maintenance Automation
- [ ] Create `scripts/maintenance/backup.sh`
  - Incremental backups
  - Compression options
  - Remote backup support
- [ ] Create `scripts/maintenance/sync_check.py`
  - Verify filesystem ↔ .bib consistency
  - Generate sync report
  - Auto-fix option for common issues

### 3.4 Testing Framework
- [ ] Create comprehensive test suite:
  - Unit tests for each validator
  - Integration tests for workflows
  - Performance tests for large collections
- [ ] Set up continuous integration (GitHub Actions)

## Phase 4: User Interfaces

### 4.1 Command-Line Interface
- [ ] Simple CLI for common operations:
  ```bash
  bib add <pdf>         # Add PDF with metadata extraction
  bib search <query>    # Search entries
  bib validate          # Check integrity
  bib export <format>   # Export bibliography
  ```
- [ ] Shell completion support

### 4.2 Local Web Interface
- [ ] Static HTML generator for browsing
- [ ] Simple search page
- [ ] PDF links for reading

## Phase 5: Personal Workflow Integration

### 5.1 LaTeX Integration
- [ ] Direct \cite{} support in documents
- [ ] Bibliography generation for papers
- [ ] Custom citation styles

### 5.2 Text Editor Integration
- [ ] Emacs package for browsing/inserting citations
- [ ] Simple completion for citation keys
- [ ] Quick PDF preview from editor

### 5.3 Personal Notes
- [ ] Add note field to entries
- [ ] Reading status tracking
- [ ] Simple tagging system

## Success Metrics

### Phase 1 Exit Criteria:
- All path validations pass on existing collection (194 PDFs)
- Duplicate detection operational
- Git hooks prevent invalid commits
- Core documentation complete (README, DESIGN)

### Phase 2 Exit Criteria:
- Import from PDF metadata functional
- Export to JSON and CSV working
- Orphan detection identifies mismatches
- Bulk import processes directories correctly

### Phase 3 Exit Criteria:
- Full test suite with >80% coverage
- Cross-reference validation working
- Search functionality returns accurate results
- Backup and sync scripts operational

### Phase 4 Exit Criteria:
- CLI tool functional for daily use
- Static HTML browsing works
- Search returns accurate results

### Phase 5 Exit Criteria:
- LaTeX integration working
- Emacs package functional
- Personal notes system operational

## Notes

- Each phase produces a working system
- Skip phases if not needed
- Simplicity over features
- Personal use focused

---

**Document Version**: 1.0  
**Last Updated**: 2025-07-30  
**Author**: Ayan Das