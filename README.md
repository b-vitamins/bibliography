# bibliography

Personal bibliography collection.

## Setup

```bash
guix shell -m manifest.scm
```

## Structure

- `by-domain/` - References organized by research area
- `by-format/` - References organized by publication type
- `scripts/` - BibTeX manipulation utilities

## Usage

Verify BibTeX syntax:
```bash
python3 scripts/verify-bib.py file.bib
```

Clean BibTeX files:
```bash
python3 scripts/clean-bib.py --in-place file.bib
```

Count entries:
```bash
python3 scripts/count-entries.py file.bib
```
