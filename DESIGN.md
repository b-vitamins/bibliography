# Bibliography Management System - Software Design Document

## 1. Introduction

### 1.1 Purpose
Design and architecture of BibTeX-based bibliography management system with strict one-to-one integrity between PDFs and metadata.

### 1.2 Scope
Academic reference management system. Supports papers, books, theses, technical reports. Foundation for CRUD operations, UI layers, search.

### 1.3 Design Goals
- **Integrity**: One-to-one correspondence between files and metadata
- **Simplicity**: Plain text files, standard tools
- **Standards**: BibTeX compatibility
- **Version Control**: Git for metadata history
- **Correctness**: Repository maintains validity at all times
- **Safety**: All operations support --dry-run mode

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Interface Layer                            │
│              (CLI tools, Emacs, LaTeX)                       │
├─────────────────────────────────────────────────────────────┤
│                  Processing Layer                             │
│           (BibTeX parsers, validators)                       │
├─────────────────────────────────────────────────────────────┤
│                    Storage Layer                              │
│  ┌─────────────────────────┐  ┌──────────────────────────┐ │
│  │   Bibliography Repo      │  │   Document Storage       │ │
│  │   (Git-controlled)       │  │   (Filesystem)          │ │
│  │   *.bib files           │  │   /home/b/documents/    │ │
│  └─────────────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Component Description

#### 2.2.1 Document Storage
- **Location**: `/home/b/documents/{entry-type}/`
- **Structure**: Flat directories per BibTeX entry type
- **Naming**: Consistent conventions per document category
- **Access**: Direct filesystem operations

#### 2.2.2 Bibliography Repository
- **Location**: `/home/b/projects/bibliography/`
- **Version Control**: Git
- **Structure**: Multiple .bib files organized by subject/type
- **Format**: Standard BibTeX entries with file paths

## 3. Data Model

### 3.1 BibTeX Entry Types

| Entry Type | Directory | Description | Mandatory Fields |
|------------|-----------|-------------|------------------|
| @article | `/article/` | Journal articles | author, title, journal, year |
| @book | `/book/` | Published books | author/editor, title, publisher, year |
| @booklet | `/booklet/` | Printed work without publisher | title |
| @conference | `/conference/` | Conference papers | author, title, booktitle, year |
| @inbook | `/inbook/` | Book chapter | author/editor, title, chapter/pages, publisher, year |
| @incollection | `/incollection/` | Book part with own title | author, title, booktitle, publisher, year |
| @inproceedings | `/inproceedings/` | Conference proceedings | author, title, booktitle, year |
| @manual | `/manual/` | Technical documentation | title |
| @mastersthesis | `/mastersthesis/` | Master's thesis | author, title, school, year |
| @misc | `/misc/` | Miscellaneous | (none required) |
| @phdthesis | `/phdthesis/` | PhD dissertation | author, title, school, year |
| @proceedings | `/proceedings/` | Conference proceedings | title, year |
| @techreport | `/techreport/` | Technical report | author, title, institution, year |
| @unpublished | `/unpublished/` | Unpublished work | author, title, note |

### 3.2 File Path Convention
```bibtex
file = {:/home/b/documents/{entry-type}/{filename}.pdf:pdf}
```

### 3.3 Citation Key Format
- Pattern: `{author}{year}{keyword}`
- Example: `feynman1942principle`
- Must be unique across entire collection

## 4. System Operations

### 4.1 Core Operations

#### 4.1.1 Add Entry
1. Copy PDF to appropriate `/home/b/documents/{type}/` directory
2. Create BibTeX entry in relevant .bib file
3. Set file path to absolute location
4. Commit changes to Git

#### 4.1.2 Remove Entry
1. Remove BibTeX entry from .bib file
2. Delete PDF from filesystem
3. Commit changes to Git

#### 4.1.3 Update Entry
1. Modify BibTeX entry maintaining file path integrity
2. If moving files: update path, move file, commit atomically
3. Validate path consistency

#### 4.1.4 Search/Query
1. Parse .bib files into memory
2. Build index on common fields (author, title, year)
3. Support regex and field-specific queries
4. Return BibTeX entries with file paths

### 4.2 Validation Rules
- Every file path must point to existing file
- Every PDF must have corresponding BibTeX entry
- Citation keys must be unique
- Mandatory fields must be populated
- File paths must be absolute

## 5. Implementation Guidelines

### 5.1 File Organization
```
/home/b/
├── documents/
│   ├── article/
│   ├── book/
│   ├── booklet/
│   ├── conference/
│   ├── inbook/
│   ├── incollection/
│   ├── inproceedings/
│   ├── manual/
│   ├── mastersthesis/
│   ├── misc/              # 189 PDFs
│   ├── phdthesis/        # 1 PDF
│   ├── proceedings/
│   ├── techreport/       # 4 PDFs
│   └── unpublished/
└── projects/
    └── bibliography/
        ├── .git/
        ├── DESIGN.md
        ├── ROADMAP.md
        ├── TODO.md
        ├── bibtex/           # UNCOMMITTED until validated
        │   ├── by-subject/
        │   │   ├── computational-physics.bib
        │   │   ├── information-theory.bib
        │   │   └── machine-learning.bib
        │   └── by-type/
        │       ├── course-notes.bib
        │       ├── coursework-exams.bib
        │       ├── coursework-homework.bib
        │       ├── coursework-solutions.bib
        │       ├── dissertations.bib
        │       ├── presentations.bib
        │       ├── problem-sets.bib
        │       ├── reference-guides.bib
        │       ├── technical-standards.bib
        │       └── tutorials.bib
        └── ...
```

### 5.2 Naming Conventions

#### 5.2.1 PDF Files
- **Course materials**: `{topic}-{year}-{instructor}-{type}-{identifier}.pdf`
- **Standards**: `standard-{year}-{org}-{number}.pdf`
- **Solutions**: `solutions-{year}-{identifier}-{type}.pdf`
- **General**: `{year}-{author}-{title-slug}.pdf`

#### 5.2.2 Bibliography Files
- By subject: `{subject}.bib` (e.g., `machine-learning.bib`)
- By type: `{type}.bib` (e.g., `presentations.bib`)

## 6. Operational Safety

### 6.1 Dry Run Mode
All modification operations MUST support --dry-run:
- Shows what would be changed without making changes
- Reports validation errors and proposed fixes
- Essential for maintaining repository correctness

### 6.2 Commit Strategy
- BibTeX files remain uncommitted during development
- Use existing validation errors to test tooling
- Only commit .bib files after all issues resolved
- Final commit demonstrates tool effectiveness

## 7. Future Extensions

### 7.1 Potential Extensions
- **Local Web UI**: Static HTML for browsing
- **Full-text Search**: grep through PDFs
- **Import Tools**: DOI and PDF metadata extraction
- **LaTeX**: Direct \cite{} support
- **Emacs Integration**: Browse and insert citations

## 8. Data Integrity

### 8.1 Validation
- Git hooks prevent invalid commits
- Path verification before operations
- Orphan detection scripts

### 8.2 Backup
- Git for metadata versioning
- Filesystem backups for PDFs
- Simple rsync scripts

## 9. Maintenance

### 9.1 Regular Tasks
- Validate all file paths
- Check for orphaned files
- Backup verification
- Citation key uniqueness audit

### 9.2 Troubleshooting
- **Missing files**: Check git history for moves
- **Duplicate keys**: Run uniqueness validator
- **Parse errors**: Validate BibTeX syntax
- **Sync issues**: Compare filesystem to .bib entries

## 10. Appendices

### 10.1 Example BibTeX Entry
```bibtex
@phdthesis{feynman1942principle,
  author = {Richard P. Feynman},
  title = {The Principle of Least Action in Quantum Mechanics},
  school = {Princeton University},
  year = {1942},
  type = {PhD thesis},
  note = {Feynman's doctoral dissertation on path integral formulation},
  file = {:/home/b/documents/phdthesis/thesis-1942-feynman-least-action.pdf:pdf}
}
```

### 10.2 Validation Script Template
```python
def validate_bibliography():
    """Ensure all file paths in .bib files point to existing files"""
    for bib_file in glob.glob("*.bib"):
        entries = parse_bibtex(bib_file)
        for entry in entries:
            if 'file' in entry:
                path = extract_path(entry['file'])
                if not os.path.exists(path):
                    raise ValidationError(f"Missing: {path}")
```

### 10.3 Git Hook Example
```bash
#!/bin/bash
# .git/hooks/pre-commit
python3 scripts/validate_paths.py || exit 1
python3 scripts/check_duplicates.py || exit 1
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-07-30  
**Author**: Ayan Das