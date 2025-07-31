"""Search command implementation following Guix patterns.

This module implements the main search functionality using SQLite/FTS5,
similar to how Guix implements package search.
"""

from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..db import BibliographyDB
from ..index import get_default_db_path
from ..models import BibEntry


class SearchResult:
    """Represents a search result with entry and relevance score."""

    def __init__(self, entry: BibEntry, score: float):
        self.entry = entry
        self.score = score


class SearchFormatter:
    """Formats search results for display."""

    def __init__(self, console: Console):
        self.console = console

    def format_results(
        self,
        results: list[SearchResult],
        query: str,
        format_type: str = "table",
        show_stats: bool = False,
    ) -> None:
        """Format and display search results.

        Args:
            results: List of search results
            query: Original search query
            format_type: Output format (table, bibtex, json, keys)
            show_stats: Whether to show search statistics
        """
        if not results:
            self.console.print(f"No results found for: {query}")
            return

        if show_stats:
            self._print_stats(results, query)

        if format_type == "table":
            self._format_table(results)
        elif format_type == "bibtex":
            self._format_bibtex(results)
        elif format_type == "json":
            self._format_json(results)
        elif format_type == "keys":
            self._format_keys(results)
        else:
            self.console.print(f"Unknown format: {format_type}")

    def _print_stats(self, results: list[SearchResult], query: str) -> None:
        """Print search statistics."""
        self.console.print(f"Found {len(results)} results for: [bold]{query}[/bold]\n")

    def _format_table(self, results: list[SearchResult]) -> None:
        """Format results as a table."""
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Score", width=6, justify="right")
        table.add_column("Key", width=25)
        table.add_column("Type", width=8)
        table.add_column("Author", width=20)
        table.add_column("Year", width=4)
        table.add_column("Title", width=50)

        for result in results:
            entry = result.entry

            # Format score with color
            score_text = Text(
                f"{result.score:.0f}",
                style="green"
                if result.score > 70
                else "yellow"
                if result.score > 40
                else "red",
            )

            author_field = entry.fields.get("author", "Unknown")
            author = author_field[:20] if author_field else "Unknown"
            year_field = entry.fields.get("year", "")
            year = year_field[:4] if year_field else ""
            title_field = entry.fields.get("title", "No title")
            title = title_field[:50] if title_field else "No title"

            table.add_row(score_text, entry.key, entry.entry_type, author, year, title)

        self.console.print(table)

    def _format_bibtex(self, results: list[SearchResult]) -> None:
        """Format results as BibTeX entries."""
        for result in results:
            entry = result.entry
            self.console.print(f"% Score: {result.score:.1f}")
            self.console.print(entry.to_bibtex())
            self.console.print()

    def _format_json(self, results: list[SearchResult]) -> None:
        """Format results as JSON."""
        import json

        data = []
        for result in results:
            entry_data = {
                "key": result.entry.key,
                "type": result.entry.entry_type,
                "fields": result.entry.fields,
                "source_file": str(result.entry.source_file),
                "score": result.score,
            }
            data.append(entry_data)

        print(json.dumps(data, indent=2))

    def _format_keys(self, results: list[SearchResult]) -> None:
        """Format results as citation keys only."""
        for result in results:
            self.console.print(result.entry.key)


class SearchEngine:
    """Main search engine using SQLite/FTS5."""

    def __init__(self, db_path: Path | None = None):
        """Initialize search engine.

        Args:
            db_path: Path to database, or None for default
        """
        if db_path is None:
            db_path = get_default_db_path()

        self.db = BibliographyDB(db_path)
        self.console = Console()
        self.formatter = SearchFormatter(self.console)

    def search(
        self, query: str, limit: int = 20, offset: int = 0, sort_by: str = "relevance"
    ) -> list[SearchResult]:
        """Search bibliography entries.

        Args:
            query: Search query (FTS5 syntax)
            limit: Maximum results to return
            offset: Offset for pagination
            sort_by: Sort order (relevance, year, author, title)

        Returns:
            List of search results
        """
        # Convert simple field queries to FTS5 syntax
        fts_query = self._prepare_fts_query(query)

        # Perform FTS search
        raw_results = self.db.search_fts(fts_query, limit, offset)

        # Convert to SearchResult objects
        results = [SearchResult(entry, score) for entry, score in raw_results]

        # Apply custom sorting if needed
        if sort_by != "relevance":
            results = self._sort_results(results, sort_by)

        return results

    def search_by_key(self, key: str) -> BibEntry | None:
        """Search for entry by exact key match.

        Args:
            key: Citation key to find

        Returns:
            BibEntry if found, None otherwise
        """
        return self.db.get_entry_by_key(key)

    def search_by_field(
        self, field: str, value: str, limit: int = 20
    ) -> list[SearchResult]:
        """Search entries by specific field.

        Args:
            field: Field name to search
            value: Value to match
            limit: Maximum results

        Returns:
            List of search results
        """
        entries = self.db.search_by_field(field, value, limit)
        # All field matches get same score
        return [SearchResult(entry, 95.0) for entry in entries]

    def get_statistics(self) -> dict[str, int | str]:
        """Get search database statistics.

        Returns:
            Dictionary with database statistics
        """
        return self.db.get_statistics()

    def _prepare_fts_query(self, query: str) -> str:
        """Convert user query to FTS5 query syntax.

        Args:
            query: User query string

        Returns:
            FTS5-compatible query string
        """
        # Handle field-specific queries
        import re

        # Convert field:value to {field}:value for FTS5
        def replace_field(match: re.Match[str]) -> str:
            field = match.group(1).lower()
            value = match.group(2) if len(match.groups()) > 1 else ""

            # Skip empty values
            if not value:
                return ""

            # Map to actual FTS columns
            if field in [
                "key",
                "title",
                "author",
                "abstract",
                "keywords",
                "journal",
                "year",
            ]:
                return f"{{{field}}}:{value}"
            return value  # Return just the value for unknown fields

        # Handle field queries like author:smith (stop at first space or end)
        # This prevents matching multiple colons in a single field
        query = re.sub(r"(\w+):([^\s:]+)", replace_field, query)

        return query

    def _sort_results(
        self, results: list[SearchResult], sort_by: str
    ) -> list[SearchResult]:
        """Sort results by specified field.

        Args:
            results: List of search results
            sort_by: Sort field (year, author, title)

        Returns:
            Sorted list of results
        """
        if sort_by == "year":
            results.sort(
                key=lambda r: r.entry.fields.get("year", "") or "", reverse=True
            )
        elif sort_by == "author":
            results.sort(key=lambda r: r.entry.fields.get("author", "") or "")
        elif sort_by == "title":
            results.sort(key=lambda r: r.entry.fields.get("title", "") or "")

        return results


def search_command(
    patterns: list[str],
    limit: int = 20,
    format_type: str = "table",
    sort_by: str = "relevance",
    stats: bool = False,
    db_path: Path | None = None,
) -> None:
    """Main search command function.

    Args:
        patterns: Search patterns to query
        limit: Maximum results to return
        format_type: Output format
        sort_by: Sort order
        stats: Show statistics
        db_path: Custom database path
    """
    if not patterns:
        console = Console()
        console.print("Error: No search patterns provided")
        return

    # Combine patterns into single query
    query = " ".join(patterns)

    # Create search engine
    engine = SearchEngine(db_path)

    try:
        # Perform search
        results = engine.search(query, limit=limit, sort_by=sort_by)

        # Format and display results
        engine.formatter.format_results(results, query, format_type, show_stats=stats)

    except Exception as e:
        engine.console.print(f"Search error: {e}")


def show_command(key: str, db_path: Path | None = None) -> None:
    """Show specific entry by key.

    Args:
        key: Citation key to display
        db_path: Custom database path
    """
    engine = SearchEngine(db_path)

    entry = engine.search_by_key(key)
    if entry:
        engine.console.print(entry.to_bibtex())
    else:
        engine.console.print(f"Entry not found: {key}")


def stats_command(db_path: Path | None = None) -> None:
    """Show database statistics.

    Args:
        db_path: Custom database path
    """
    engine = SearchEngine(db_path)
    console = engine.console

    stats = engine.get_statistics()

    console.print("[bold]Bibliography Database Statistics[/bold]\n")

    console.print(f"Total entries: {stats['total_entries']:,}")
    console.print(f"FTS entries: {stats['fts_entries']:,}")

    # Handle db_size_bytes properly
    db_size = stats.get("db_size_bytes", 0)
    if isinstance(db_size, int | float):
        console.print(f"Database size: {db_size / (1024 * 1024):.1f} MB\n")
    else:
        console.print("Database size: Unknown\n")

    by_type = stats.get("by_type", {})
    if isinstance(by_type, dict) and by_type:
        console.print("[bold]Entries by type:[/bold]")
        for entry_type, count in sorted(by_type.items()):
            console.print(f"  {entry_type:15} {count:6,}")
        console.print()

    by_file = stats.get("by_file", {})
    if isinstance(by_file, dict) and by_file:
        console.print("[bold]Entries by file:[/bold]")
        for file_path, count in sorted(by_file.items()):
            file_name = Path(file_path).name
            console.print(f"  {file_name:30} {count:6,}")
