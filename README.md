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
./bib check all
```

## Usage

### Validate bibliography
```bash
# Check all validations
./bib check all

# Check file paths only
./bib check paths

# Check for duplicates
./bib check duplicates

# Check mandatory fields
./bib check fields
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