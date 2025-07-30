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

### 3.1 Core Abstractions

#### 3.1.1 BibEntry Model
```python
@dataclass
class BibEntry:
    key: str                    # Unique citation key
    entry_type: str             # article, book, etc.
    fields: dict[str, str]      # All BibTeX fields
    source_file: Path           # Which .bib file contains this entry
    
    # Methods for manipulation
    def update_field(field: str, value: str) -> None
    def remove_field(field: str) -> None
    def set_file_path(path: Path) -> None
    def validate_mandatory_fields() -> list[str]
    def to_bibtex() -> str
```

#### 3.1.2 Repository Pattern
```python
class Repository:
    """Central abstraction for all bibliography operations"""
    
    # Core CRUD operations
    def get_entry(key: str) -> BibEntry | None
    def add_entry(entry: BibEntry, target_file: Path) -> None
    def remove_entry(key: str) -> BibEntry | None
    def update_entry(key: str, updates: dict) -> BibEntry | None
    
    # Atomic operations with dry-run support
    def enable_dry_run() -> None
    def disable_dry_run() -> None
    def changeset() -> ChangeSet | None
    
    # Query support
    def load_entries() -> list[BibEntry]
    def get_entries_by_type(type: str) -> list[BibEntry]
    def get_entries_by_file(file: Path) -> list[BibEntry]
```

#### 3.1.3 Query Builder Pattern
```python
class Query:
    """Composable query builder for flexible searching"""
    
    def where(field: str, value: str, exact: bool = True) -> Query
    def where_any(search: str) -> Query
    def where_type(entry_type: str) -> Query
    def order_by(field: str) -> Query
    def limit(n: int) -> Query
    def execute() -> list[BibEntry]
```

### 3.2 BibTeX Entry Types

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

### 4.2 Advanced Operations

#### 4.2.1 Search Capabilities
- **Field Search**: Query specific fields with exact or fuzzy matching
- **Full-text Search**: Search across all fields with ranking
- **Boolean Logic**: AND, OR, NOT operators for complex queries
- **Similarity Search**: Find entries similar to a given entry
- **Regex Support**: Pattern matching in field values

#### 4.2.2 Bulk Operations
- **Field Updates**: Update fields across multiple entries
- **Batch Validation**: Validate and fix multiple entries
- **Key Normalization**: Standardize citation keys by pattern
- **Type Migration**: Change entry types with field mapping
- **Orphan Cleanup**: Remove entries without PDFs

#### 4.2.3 Analysis and Reporting
- **Statistics**: Entry counts by type, year, author
- **Coverage Reports**: Missing fields, broken paths
- **Duplicate Detection**: By key, title similarity, or file hash
- **Citation Graph**: Analyze references between entries
- **Quality Metrics**: Completeness scores for entries

### 4.3 Validation Rules
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
        ├── docs/
        │   └── design.md
        ├── ROADMAP.md
        ├── TODO.md
        ├── bibtex/           # Bibliography .bib files
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

## 10. Search System Design (Phase 3)

### 10.1 Search Architecture

#### Search Index
```python
class SearchIndex:
    """In-memory search index with field weighting"""
    
    def __init__(self):
        self.entries: dict[str, BibEntry] = {}
        self.tokens: dict[str, set[str]] = {}  # token -> entry keys
        self.field_weights = {
            'key': 5.0,        # Citation key has highest weight
            'title': 4.0,      # Title is very important
            'author': 3.5,     # Author names important
            'keywords': 3.0,   # Keywords if present
            'year': 2.5,       # Year for temporal search
            'abstract': 2.0,   # Abstract text
            'journal': 2.0,    # Journal/venue
            'note': 1.5,       # Notes field
            'description': 1.0 # Any other descriptive fields
        }
```

#### Query Types
- **Natural Language**: `bib search "quantum computing feynman"`
- **Field-Specific**: `bib search "author:feynman year:1965"`
- **Boolean Logic**: `bib search "(quantum OR classical) AND computing"`
- **Regex Patterns**: `bib search "title:quantum.*computing"`
- **Fuzzy Matching**: `bib search "author:~feinman"` (matches feynman)

#### Relevance Scoring
```python
def calculate_relevance(entry: BibEntry, query_tokens: list[str]) -> float:
    """Calculate relevance score for an entry"""
    score = 0.0
    
    for field, weight in self.field_weights.items():
        field_value = entry.fields.get(field, '')
        field_tokens = tokenize(field_value)
        
        for query_token in query_tokens:
            if query_token in field_tokens:
                # Exact match gets full weight
                score += weight
            elif fuzzy_match(query_token, field_tokens):
                # Fuzzy match gets partial weight
                score += weight * 0.7
    
    return score
```

### 10.2 Rich Display System

The search results use Rich library for beautiful terminal output:
- **Relevance visualization**: Bar charts showing match quality
- **Result tables**: Truncated display with key fields
- **Detailed view**: Syntax-highlighted BibTeX for top results
- **Facet panels**: Distribution by year, type, author

### 10.3 Search Features

#### Fuzzy Matching
- Author name variations (Last, First vs First Last)
- Typo tolerance using Levenshtein distance
- Partial word matching

#### Faceted Search
```bash
bib search "quantum" --facet year,type
```
Shows distribution of results by specified fields

#### Similar Entry Detection
```bash
bib find --similar feynman1965
```
Based on title similarity, author overlap, year proximity

### 10.4 Performance Goals
- Index 10,000 entries in <1 second
- Search response <100ms for typical queries
- Incremental index updates
- Memory-efficient token storage

## 11. Appendices

### 11.1 Example BibTeX Entry
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

### 11.2 Validation Script Template
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

### 11.3 Git Hook Example
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