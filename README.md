# Bibliography Management System

Personal bibliography management system with BibTeX metadata and PDF storage.

## Overview

This is a BibTeX-based bibliography management system that maintains strict one-to-one correspondence between PDF files and BibTeX metadata entries. The system enforces correctness at all times through comprehensive validation and Git hooks.

**Key Features:**
- 194 validated bibliography entries
- Strict validation preventing invalid data
- Git hooks enforcing quality standards
- Type-based PDF organization
- Detailed error reporting with context

## Installation

```bash
git clone <repository>
cd bibliography

# Install Git hooks (REQUIRED)
./hooks/install.sh

# Enter development environment
guix shell -m manifest.scm

# Verify installation
python3 -m bibmgr.cli check all
```

## Usage

### Validation Commands

Always work within the Guix environment:
```bash
guix shell -m manifest.scm
```

Check bibliography integrity:
```bash
# Run all validation checks
python3 -m bibmgr.cli check all

# Check specific validations
python3 -m bibmgr.cli check paths       # Verify PDF files exist
python3 -m bibmgr.cli check duplicates  # Find duplicate keys
python3 -m bibmgr.cli check fields      # Validate mandatory fields
```

### Detailed Reports

Get detailed context for validation errors:
```bash
# Comprehensive report
python3 -m bibmgr.cli report all

# Specific reports with full context
python3 -m bibmgr.cli report duplicates  # Side-by-side duplicate entries
python3 -m bibmgr.cli report fields      # Missing fields with suggestions
python3 -m bibmgr.cli report paths       # Missing files with entry details
```

### Searching Bibliography

```bash
# Search by author
grep -r "author.*Feynman" bibtex/

# Search by title
grep -ri "quantum" bibtex/

# Find specific entry type
grep -r "@article" bibtex/
```

### Statistics

```bash
# Count total PDFs
find /home/b/documents -name "*.pdf" -type f | wc -l

# Count entries by type
grep -r "^@" bibtex/ | cut -d'{' -f1 | sort | uniq -c

# List all .bib files
find bibtex -name "*.bib" -type f
```

## Repository Structure

```
bibliography/
├── bibtex/              # Bibliography metadata (Git-controlled)
│   ├── by-subject/      # Subject-organized .bib files
│   └── by-type/         # Type-organized .bib files
├── bibmgr/              # Python CLI tool
│   ├── cli.py           # Command-line interface
│   ├── models.py        # Data models
│   ├── validators.py    # Validation logic
│   └── report.py        # Detailed reporting
├── hooks/               # Git hooks for quality enforcement
│   ├── pre-commit       # Code quality, validation
│   ├── commit-msg       # Conventional commits
│   ├── pre-push         # Final verification
│   └── README.md        # Hook documentation
├── manifest.scm         # Guix package definitions
├── pyproject.toml       # Python project config
├── DESIGN.md           # System architecture
├── ROADMAP.md          # Implementation phases
├── CLAUDE.md           # AI assistant guidelines
└── CHANGELOG.md        # Version history

PDF Storage (not in Git):
/home/b/documents/
├── article/            # Journal articles
├── book/               # Books
├── misc/               # Miscellaneous (189 files)
├── phdthesis/          # PhD dissertations (1 file)
└── techreport/         # Technical reports (4 files)
```

## Development

### Prerequisites

- GNU Guix package manager
- Git version control
- Access to PDF storage at `/home/b/documents/`

### Environment Setup

```bash
# Enter development environment
guix shell -m manifest.scm

# Install Git hooks (one-time)
./hooks/install.sh

# Run validation before any changes
python3 -m bibmgr.cli check all
```

### Git Workflow

The repository enforces quality through Git hooks:

1. **Pre-commit**: Validates Python code and BibTeX entries
2. **Commit-msg**: Enforces conventional commit format
3. **Pre-push**: Final comprehensive validation

Commit format:
```
type(scope): description

- type: feat|fix|docs|style|refactor|test|chore
- scope: bibmgr|bibtex|hooks|docs
- description: imperative mood, lowercase
```

Example:
```bash
git add bibtex/
git commit -m "fix(bibtex): correct duplicate keys in homework entries"
```

### Adding New Entries

1. Add PDF to appropriate directory under `/home/b/documents/`
2. Add BibTeX entry to appropriate `.bib` file
3. Ensure citation key follows pattern: `{author}{year}{keyword}`
4. Include required fields for entry type
5. Use absolute path in file field: `{:/home/b/documents/type/file.pdf:pdf}`
6. Run validation: `python3 -m bibmgr.cli check all`

## Quality Standards

This repository maintains strict quality standards:

- **Correctness Invariant**: No invalid data can be committed
- **Validation**: All entries must pass validation checks
- **Code Quality**: Python code must pass ruff and pyright
- **Commit Standards**: Conventional commit format required
- **Documentation**: Keep README, CHANGELOG, and docs updated

## Troubleshooting

### Common Issues

**Not in Guix environment:**
```bash
ERROR: Not in a Guix shell!
# Solution: guix shell -m manifest.scm
```

**Validation failures:**
```bash
# Get detailed report
python3 -m bibmgr.cli report all

# Fix issues manually based on report
# Re-run validation
```

**Hook failures:**
```bash
# Emergency bypass (use sparingly)
git commit --no-verify
SKIP_PRE_PUSH=1 git push
```

See `hooks/README.md` for detailed troubleshooting.

## License

This project is licensed under the MIT License - see LICENSE file for details.