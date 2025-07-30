# Bibliography Management System

Personal bibliography management system with BibTeX metadata and PDF storage.

## Description

Academic reference management system maintaining one-to-one correspondence between BibTeX entries and PDF files. Supports papers, books, theses, technical reports with Git version control for metadata.

## Installation

```bash
git clone <repository>
cd bibliography

# Guix users
guix shell -m manifest.scm

# Run validation
python3 -m bibmgr.cli check all
```

## Usage

### Validate bibliography
```bash
# Enter Guix environment
guix shell -m manifest.scm

# Check all validations
python3 -m bibmgr.cli check all

# Check file paths only
python3 -m bibmgr.cli check paths

# Check for duplicates
python3 -m bibmgr.cli check duplicates

# Check mandatory fields
python3 -m bibmgr.cli check fields
```

### Fix validation errors
```bash
# Fix all issues (dry-run by default)
python3 -m bibmgr.cli fix all

# Fix specific issues
python3 -m bibmgr.cli fix duplicates
python3 -m bibmgr.cli fix fields

# Apply fixes (no dry-run)
python3 -m bibmgr.cli fix all --no-dry-run
```

### Search entries
```bash
grep -r "author.*Feynman" bibtex/
```

### Count PDFs
```bash
find /home/b/documents -name "*.pdf" -type f | wc -l
```

## Structure

- `bibtex/` - Bibliography files organized by subject/type
- `bibmgr/` - Core Python package
- `bib` - Main CLI tool
- `scripts/` - Additional maintenance scripts  
- `hooks/` - Git hooks for integrity checks
- `config/` - Configuration files

## License

See LICENSE file.