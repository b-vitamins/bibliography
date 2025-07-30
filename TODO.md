# Bibliography Management System - TODO

## Phase 1: Core Infrastructure (Current)

### Known Validation Issues (Test Cases)
- [ ] 3 duplicate keys: illinois2012igmhw[1-3] between homework/solutions
- [ ] 4 missing author fields in technical-standards.bib (ISO standards)
- **Note**: These remain unfixed to test tooling during development

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
- [x] Report commands show issues with full BibTeX context
- [ ] Add --dry-run mode to all modification operations
- [ ] Implement fix operations (infrastructure-first, no automation yet)

### 1.3 Git Integration
- [x] Set up pre-commit hook
- [x] Create hooks/install.sh
- [ ] Test hook prevents invalid commits
- [ ] Document hook setup in README

### 1.4 Configuration
- [x] Embed validation rules in code (MANDATORY_FIELDS)
- [ ] Create config/naming_rules.yaml
- [ ] Create Python config parser for naming rules

### 1.5 Final Phase 1 Task
- [ ] Fix all validation errors using developed tools
- [ ] Commit clean .bib files as proof of working system

**Phase 1 Complete When**: All tools built, validation errors fixed, .bib files committed

## Phase 2: Import/Export (Next)

### Prerequisites
- [ ] Phase 1 complete
- [ ] All 194 PDFs validated

### Tasks
- [ ] Create from_pdf_metadata.py
- [ ] Create from_doi.py
- [ ] Create bulk_import.py
- [ ] Create to_json.py exporter
- [ ] Create to_csv.py exporter
- [ ] Create find_orphans.py
- [ ] Create generate_stats.py

## Phase 3: Advanced Features (Future)

### Prerequisites
- [ ] Phase 2 complete
- [ ] Import/export tested

### Tasks
- [ ] Enhanced validation (cross-references)
- [ ] Search functionality
- [ ] Test suite with >80% coverage
- [ ] Backup automation

## Future Phases

### Phase 4: User Interfaces
- Simple CLI tool
- Static HTML browsing

### Phase 5: Personal Integration
- LaTeX support
- Emacs package
- Note-taking

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