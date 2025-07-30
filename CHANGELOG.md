# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Basic test suite structure with pytest
- Version badge in README.md
- Rich library dependency for enhanced terminal UI (Phase 2 preparation)

### Changed
- Restructured ROADMAP.md with incremental Phase 2 (Core Data Layer) and Phase 3 (Higher-Level Operations)
- Updated README.md to show current phase status and upcoming features
- Removed bypass instructions from README.md - bypassing hooks is strictly prohibited

### Fixed
- Pre-push hook syntax errors and robustness issues
- README.md now displays current version (0.1.0)

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
- Documentation (DESIGN.md, ROADMAP.md, CLAUDE.md)
- Automatic tool execution through Guix shell in hooks

### Fixed
- 3 duplicate citation keys in homework/solutions files (added 'sol' suffix)
- 4 missing author fields in ISO/IEC/IEEE technical standards

### Changed
- Reorganized 194 PDFs into type-based directory structure
- Moved 13 .bib files into bibtex/ directory (by-subject and by-type)