# Bibliography Search System Design

## Overview

This document outlines the design for Phase 3's search capabilities, inspired by Guix's elegant search interface with added Rich terminal UI enhancements.

## Search Architecture

### 1. Search Index

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

### 2. Query Types

#### Natural Language Query
```bash
bib search "quantum computing feynman"
```
- Tokenizes into words
- Searches across all indexed fields
- Implicitly ANDs terms together

#### Field-Specific Query
```bash
bib search "author:feynman AND year:1965"
```
- Supports field:value syntax
- Boolean operators: AND, OR, NOT
- Parenthetical grouping

#### Regex Query
```bash
bib search "title:quantum.*computing"
```
- Full regex support in field values
- Case-insensitive by default

### 3. Relevance Scoring

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

### 4. Rich Display Format

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

def display_search_results(results: list[SearchResult]):
    """Display search results with Rich formatting"""
    
    console = Console()
    
    # Summary panel
    summary = Panel(
        f"Found [bold cyan]{len(results)}[/bold cyan] matching entries",
        title="Search Results",
        border_style="blue"
    )
    console.print(summary)
    
    # Results table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Relevance", style="dim", width=9)
    table.add_column("Key", style="cyan", width=25)
    table.add_column("Year", width=6)
    table.add_column("Author", width=20)
    table.add_column("Title", width=40)
    
    for result in results[:20]:  # Show top 20
        relevance = f"[green]{'█' * int(result.score/10)}[/green]"
        table.add_row(
            relevance,
            result.entry.key,
            result.entry.fields.get('year', ''),
            truncate(result.entry.fields.get('author', ''), 20),
            truncate(result.entry.fields.get('title', ''), 40)
        )
    
    console.print(table)
    
    # Detailed view for top result
    if results:
        top = results[0]
        detail = Panel(
            Syntax(top.entry.to_bibtex(), "bibtex", theme="monokai"),
            title=f"Top Result: {top.entry.key}",
            border_style="green"
        )
        console.print(detail)
```

## Search Features

### 1. Fuzzy Matching
- Author name variations (Last, First vs First Last)
- Typo tolerance using Levenshtein distance
- Partial word matching

### 2. Faceted Search
```bash
bib search "quantum" --facet year
```
Shows distribution of results by year

### 3. Similar Entry Detection
```bash
bib find --similar feynman1965
```
Finds entries similar to the given key based on:
- Title similarity (n-gram comparison)
- Author overlap
- Year proximity
- Keyword/topic similarity

### 4. Search Modifiers
- `--case-sensitive`: Enable case-sensitive search
- `--limit N`: Limit results to N entries
- `--format FORMAT`: Output format (table, full, keys, json)
- `--sort FIELD`: Sort by field instead of relevance

## Implementation Plan

### Phase 3.1: Search Foundation
1. Create `SearchIndex` class with tokenization
2. Implement field weighting system
3. Build relevance scoring algorithm
4. Add caching for performance

### Phase 3.2: Query Parser
1. Natural language tokenization
2. Field:value syntax parsing
3. Boolean operator support
4. Regex pattern compilation

### Phase 3.3: Display System
1. Rich-based result tables
2. Relevance visualization
3. Faceted result summaries
4. Export formats

### Phase 3.4: Advanced Features
1. Fuzzy matching algorithms
2. Similar entry detection
3. Search history/saved searches
4. Performance optimization

## Performance Goals
- Index 10,000 entries in <1 second
- Search response <100ms for typical queries
- Incremental index updates
- Memory-efficient token storage

## CLI Examples

```bash
# Natural language search
bib search "quantum computing"

# Field-specific search
bib search "author:feynman year:1965"

# Boolean search
bib search "(quantum OR classical) AND computing"

# Regex search
bib search "title:^On.*Theory$"

# Fuzzy author search
bib search "author:~feinman"  # matches feynman

# Show facets
bib search "physics" --facet year,type

# Similar entries
bib find --similar feynman1965 --limit 10

# Export results
bib search "quantum" --format json > results.json
```