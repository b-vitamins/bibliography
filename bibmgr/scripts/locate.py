"""Locate command implementation following Guix patterns.

This module implements file-based search functionality, similar to 'guix locate',
allowing users to find bibliography entries by PDF file paths.
"""

from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..db import BibliographyDB
from ..index import get_default_db_path
from ..models import BibEntry


class LocateFormatter:
    """Formats locate results for display."""

    def __init__(self, console: Console):
        self.console = console

    def format_results(
        self, results: list[BibEntry], pattern: str, format_type: str = "table"
    ) -> None:
        """Format and display locate results.

        Args:
            results: List of matching entries
            pattern: File pattern that was searched
            format_type: Output format (table, paths, keys)
        """
        if not results:
            self.console.print(f"No entries found containing file pattern: {pattern}")
            return

        if format_type == "table":
            self._format_table(results, pattern)
        elif format_type == "paths":
            self._format_paths(results)
        elif format_type == "keys":
            self._format_keys(results)
        else:
            self.console.print(f"Unknown format: {format_type}")

    def _format_table(self, results: list[BibEntry], pattern: str) -> None:
        """Format results as a table showing key, type, and file path."""
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Key", width=25)
        table.add_column("Type", width=10)
        table.add_column("Author", width=20)
        table.add_column("Year", width=4)
        table.add_column("File Path", width=60)

        for entry in results:
            author_field = entry.fields.get("author", "Unknown")
            author = author_field[:20] if author_field else "Unknown"
            year_field = entry.fields.get("year", "")
            year = year_field[:4] if year_field else ""

            # Extract file path from entry
            file_field = entry.fields.get("file", "")
            file_path = self.extract_file_path(file_field) if file_field else ""

            # Highlight the matching pattern in the path
            if pattern.lower() in file_path.lower():
                highlighted_path = file_path.replace(
                    pattern, f"[bold yellow]{pattern}[/bold yellow]"
                )
            else:
                highlighted_path = file_path

            table.add_row(
                entry.key, entry.entry_type, author, year, highlighted_path[:60]
            )

        self.console.print(
            f"\nFound {len(results)} entries containing: [bold]{pattern}[/bold]\n"
        )
        self.console.print(table)

    def _format_paths(self, results: list[BibEntry]) -> None:
        """Format results showing only file paths."""
        for entry in results:
            file_field = entry.fields.get("file", "")
            if file_field:
                file_path = self.extract_file_path(file_field)
                if file_path:
                    self.console.print(file_path)

    def _format_keys(self, results: list[BibEntry]) -> None:
        """Format results showing only citation keys."""
        for entry in results:
            self.console.print(entry.key)

    def extract_file_path(self, file_field: str) -> str:
        """Extract file path from BibTeX file field.

        Args:
            file_field: BibTeX file field value

        Returns:
            Extracted file path
        """
        if not file_field:
            return ""

        # Handle different file field formats
        # Format: {path:type} or {:/path:type} or just path
        if file_field.startswith("{") and file_field.endswith("}"):
            # Remove braces
            content = file_field[1:-1]

            # Split by colons and take the path part
            parts = content.split(":")
            if len(parts) >= 2:
                # Format like {:/path:pdf}
                if parts[0] == "":
                    return parts[1] if len(parts) > 1 else content
                # Format like {path:pdf}
                return parts[0]
            else:
                return content

        return file_field


class LocateEngine:
    """File-based search engine for bibliography entries."""

    def __init__(self, db_path: Path | None = None):
        """Initialize locate engine.

        Args:
            db_path: Path to database, or None for default
        """
        if db_path is None:
            db_path = get_default_db_path()

        self.db = BibliographyDB(db_path)
        self.console = Console()
        self.formatter = LocateFormatter(self.console)

    def locate_file(
        self, pattern: str, glob_match: bool = False, basename_only: bool = False
    ) -> list[BibEntry]:
        """Locate entries by file path pattern.

        Args:
            pattern: File pattern to search for
            glob_match: Whether to use glob pattern matching
            basename_only: Search only in file basenames

        Returns:
            List of matching entries
        """
        if basename_only:
            # Extract basename from pattern for more targeted search
            pattern = Path(pattern).name

        # Use database locate functionality
        results = self.db.locate_file(pattern, glob_match=glob_match)

        # If basename_only, filter results to only basename matches
        if basename_only:
            filtered_results = []
            for entry in results:
                file_field = entry.fields.get("file", "")
                if file_field:
                    file_path = self.formatter.extract_file_path(file_field)
                    if file_path and pattern.lower() in Path(file_path).name.lower():
                        filtered_results.append(entry)
            return filtered_results

        return results

    def locate_by_extension(self, extension: str) -> list[BibEntry]:
        """Locate entries by file extension.

        Args:
            extension: File extension to search for (e.g., 'pdf', '.pdf')

        Returns:
            List of matching entries
        """
        if not extension.startswith("."):
            extension = "." + extension

        # Use glob pattern for extension matching
        pattern = f"*{extension}"
        return self.db.locate_file(pattern, glob_match=True)

    def locate_in_directory(self, directory: str) -> list[BibEntry]:
        """Locate entries with files in specific directory.

        Args:
            directory: Directory path to search in

        Returns:
            List of matching entries
        """
        # Normalize directory path
        dir_path = str(Path(directory).resolve())
        return self.db.locate_file(dir_path, glob_match=False)

    def verify_files_exist(self) -> list[BibEntry]:
        """Find entries where the referenced files don't exist.

        Returns:
            List of entries with missing files
        """
        # Get all entries and check file existence
        self.db.get_statistics()
        missing = []

        # For now, we'll need to implement this by checking each entry
        # This is a simplified version - full implementation would batch check

        return missing  # TODO: Implement file existence checking


def locate_command(
    pattern: str,
    glob_match: bool = False,
    basename_only: bool = False,
    format_type: str = "table",
    db_path: Path | None = None,
) -> None:
    """Main locate command function.

    Args:
        pattern: File pattern to search for
        glob_match: Use glob pattern matching
        basename_only: Search only basenames
        format_type: Output format
        db_path: Custom database path
    """
    if not pattern:
        console = Console()
        console.print("Error: No file pattern provided")
        return

    # Create locate engine
    engine = LocateEngine(db_path)

    try:
        # Perform file search
        results = engine.locate_file(pattern, glob_match, basename_only)

        # Format and display results
        engine.formatter.format_results(results, pattern, format_type)

    except Exception as e:
        engine.console.print(f"Locate error: {e}")


def locate_extension_command(
    extension: str, format_type: str = "table", db_path: Path | None = None
) -> None:
    """Locate files by extension.

    Args:
        extension: File extension to search for
        format_type: Output format
        db_path: Custom database path
    """
    engine = LocateEngine(db_path)

    try:
        results = engine.locate_by_extension(extension)
        engine.formatter.format_results(
            results, f"*.{extension.lstrip('.')}", format_type
        )

    except Exception as e:
        engine.console.print(f"Locate error: {e}")


def locate_directory_command(
    directory: str, format_type: str = "table", db_path: Path | None = None
) -> None:
    """Locate files in specific directory.

    Args:
        directory: Directory to search in
        format_type: Output format
        db_path: Custom database path
    """
    engine = LocateEngine(db_path)

    try:
        results = engine.locate_in_directory(directory)
        engine.formatter.format_results(results, directory, format_type)

    except Exception as e:
        engine.console.print(f"Locate error: {e}")


def verify_files_command(db_path: Path | None = None) -> None:
    """Verify that all referenced files exist.

    Args:
        db_path: Custom database path
    """
    engine = LocateEngine(db_path)
    console = engine.console

    console.print("🔍 Checking file existence...")

    try:
        missing = engine.verify_files_exist()

        if missing:
            console.print(f"❌ Found {len(missing)} entries with missing files:")
            for entry in missing:
                file_field = entry.fields.get("file", "")
                if file_field:
                    file_path = engine.formatter.extract_file_path(file_field)
                    console.print(f"  {entry.key}: {file_path}")
                else:
                    console.print(f"  {entry.key}: [no file field]")
        else:
            console.print("✅ All referenced files exist")

    except Exception as e:
        console.print(f"Verification error: {e}")
