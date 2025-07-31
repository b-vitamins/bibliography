# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-07-31

### Added
- **Phase 3: SQLite-based Search System (Complete)**
  - SQLite database with FTS5 full-text search engine (`bibmgr/db.py`)
  - Scalable search handling 100k+ entries with <5ms query time
  - Search index management with incremental updates (`bibmgr/index.py`)
  - Guix-style search commands:
    - `search` - Natural language and boolean search with FTS5
    - `locate` - File-based search (like `guix locate`)
    - `show` - Display specific entries from database
    - `stats` - Database statistics and performance metrics
  - Index management commands (`build`, `update`, `status`)
  - Multiple output formats (table, bibtex, json, keys)
  - Field-specific search (`author:feynman`, `journal:nature`)
  - Advanced query features (wildcards, phrase search, boolean operators)
- **Comprehensive Test Suite (423 tests, 90%+ coverage)**
  - Complete test coverage for all modules (cli.py 98%, models.py 95%, etc.)
  - Integration tests for search functionality
  - Performance tests for scalability
  - Robustness tests for edge cases
  - Database and FTS5 functionality tests
- **Enhanced CLI Integration**
  - Integrated search commands into main CLI
  - Rich console output with enhanced formatting
  - Database path configuration options
  - Search result sorting and limiting
- **Core Data Layer Improvements (Phase 2)**
  - Enhanced BibEntry model with manipulation methods
  - Repository class for atomic .bib file operations with dry-run support
  - Query builder for flexible entry searching and filtering
  - CRUD operations: add, remove, update with interactive prompts
  - CLI commands: add, remove, update, show, list

### Changed
- Updated all documentation (README.md, ROADMAP.md, TODO.md, CLAUDE.md) for Phase 3 completion
- Enhanced list command with simplified filtering (removed QueryBuilder dependency)
- Improved test organization and coverage reporting
- Updated dependency specifications in pyproject.toml

### Fixed
- CLI test failures caused by import shadowing (`all` function conflict)
- Ruff linting errors (unused arguments, nested with statements)
- Test fixture naming issues and mock setup problems
- Type safety improvements across all modules

### Performance
- Search queries: <5ms on 100k+ entries (exceeded <100ms goal)
- Index building: 10k+ entries/second
- Memory usage: Constant ~10MB regardless of database size
- Database operations: WAL mode for concurrent access

## [0.1.0] - 2025-07-31

### Added
- Initial bibliography management system infrastructure
- Python CLI tool (`bibmgr`) with validation and reporting commands
- Comprehensive Git hooks for quality enforcement
  - pre-commit: Code quality, BibTeX validation, security scanning
  - commit-msg: Conventional commit format enforcement
  - pre-push: Final validation and changelog enforcement
  - prepare-commit-msg: Commit templates and helpers
  - post-commit: Quality metrics tracking
  - post-merge: Dependency update alerts
  - pre-rebase: Safety checks for rebasing
- Validation framework for BibTeX entries
  - Path validation (file existence)
  - Duplicate key detection
  - Mandatory field validation
- Detailed reporting with context for manual fixes
- Guix manifest for reproducible development environment
- Documentation (docs/design.md, ROADMAP.md, CLAUDE.md)
- Automatic tool execution through Guix shell in hooks

### Fixed
- 3 duplicate citation keys in homework/solutions files (added 'sol' suffix)
- 4 missing author fields in ISO/IEC/IEEE technical standards

### Changed
- Reorganized 194 PDFs into type-based directory structure
- Moved 13 .bib files into bibtex/ directory (by-subject and by-type)