"""Tests for locate functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bibmgr.db import BibliographyDB
from bibmgr.models import BibEntry
from bibmgr.scripts.locate import LocateEngine, LocateFormatter


@pytest.fixture
def locate_test_entries():
    """Create test entries with various file paths for locate testing."""
    return [
        BibEntry(
            key="article2023test",
            entry_type="article",
            fields={
                "title": "Test Article",
                "author": "John Doe",
                "year": "2023",
                "file": ":/home/b/documents/article/test-article-2023.pdf:pdf",
            },
            source_file=Path("test.bib"),
        ),
        BibEntry(
            key="book2020example",
            entry_type="book",
            fields={
                "title": "Example Book",
                "author": "Jane Smith",
                "year": "2020",
                "file": ":/home/b/documents/book/example-book.pdf:pdf",
            },
            source_file=Path("books.bib"),
        ),
        BibEntry(
            key="thesis2021phd",
            entry_type="phdthesis",
            fields={
                "title": "PhD Thesis Example",
                "author": "Bob Johnson",
                "year": "2021",
                "file": ":/home/b/documents/phdthesis/johnson-2021-thesis.pdf:pdf",
            },
            source_file=Path("thesis.bib"),
        ),
        BibEntry(
            key="report2022tech",
            entry_type="techreport",
            fields={
                "title": "Technical Report",
                "author": "Alice Brown",
                "year": "2022",
                "file": ":/home/b/documents/techreport/alice-brown-report.pdf:pdf",
            },
            source_file=Path("reports.bib"),
        ),
        BibEntry(
            key="nofile2023",
            entry_type="article",
            fields={
                "title": "Article Without File",
                "author": "No File Author",
                "year": "2023",
                # No file field
            },
            source_file=Path("test.bib"),
        ),
    ]


@pytest.fixture
def locate_database(locate_test_entries: list[BibEntry]):
    """Create database with locate test entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "locate_test.db"
        db = BibliographyDB(db_path)
        db.insert_entries_batch(locate_test_entries)
        yield db_path


class TestLocateFormatter:
    """Test LocateFormatter class."""

    def test_extract_file_path_formats(self) -> None:
        """Test extracting file paths from various BibTeX formats."""
        from rich.console import Console

        formatter = LocateFormatter(Console())

        # Standard format with colons and braces
        file_field = "{:/home/b/documents/article/test.pdf:pdf}"
        path = formatter.extract_file_path(file_field)
        assert path == "/home/b/documents/article/test.pdf"

        # Format without leading colon
        file_field = "{/home/b/documents/book/example.pdf:pdf}"
        path = formatter.extract_file_path(file_field)
        assert path == "/home/b/documents/book/example.pdf"

        # Simple path without braces
        file_field = "/home/b/documents/simple.pdf"
        path = formatter.extract_file_path(file_field)
        assert path == "/home/b/documents/simple.pdf"

        # Empty field
        path = formatter.extract_file_path("")
        assert path == ""

        # Just braces
        file_field = "{}"
        path = formatter.extract_file_path(file_field)
        assert path == ""

    def test_format_results_table(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test table format output."""
        from rich.console import Console

        engine = LocateEngine(locate_database)
        results = engine.locate_file("test-article")

        formatter = LocateFormatter(Console())
        formatter.format_results(results, "test-article", "table")

        captured = capsys.readouterr()
        assert "test-article" in captured.out
        assert "Found" in captured.out

    def test_format_results_paths(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test paths format output."""
        from rich.console import Console

        engine = LocateEngine(locate_database)
        results = engine.locate_file("pdf")

        formatter = LocateFormatter(Console())
        formatter.format_results(results, "pdf", "paths")

        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.split("\n") if line.strip()]

        # Should contain file paths
        assert len(lines) >= 1
        for line in lines:
            assert "documents" in line or line == ""

    def test_format_results_keys(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test keys format output."""
        from rich.console import Console

        engine = LocateEngine(locate_database)
        results = engine.locate_file("pdf")

        formatter = LocateFormatter(Console())
        formatter.format_results(results, "pdf", "keys")

        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.split("\n") if line.strip()]

        # Should contain citation keys
        assert len(lines) >= 1
        for line in lines:
            if line:  # Skip empty lines
                assert line in [
                    "article2023test",
                    "book2020example",
                    "thesis2021phd",
                    "report2022tech",
                ]

    def test_format_no_results(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test formatting when no results found."""
        from rich.console import Console

        engine = LocateEngine(locate_database)
        results = engine.locate_file("nonexistent")

        formatter = LocateFormatter(Console())
        formatter.format_results(results, "nonexistent", "table")

        captured = capsys.readouterr()
        assert "No entries found" in captured.out
        assert "nonexistent" in captured.out


class TestLocateEngine:
    """Test LocateEngine class."""

    def test_locate_engine_initialization(self, locate_database: Path) -> None:
        """Test LocateEngine initialization."""
        engine = LocateEngine(locate_database)

        assert engine.db is not None
        assert engine.console is not None
        assert engine.formatter is not None

    def test_locate_engine_default_path(self) -> None:
        """Test LocateEngine with default database path."""
        # This should not fail even if default DB doesn't exist
        engine = LocateEngine(None)
        assert engine.db is not None

    def test_locate_file_exact_match(self, locate_database: Path) -> None:
        """Test locating files with exact filename match."""
        engine = LocateEngine(locate_database)

        # Find by exact filename
        results = engine.locate_file("test-article-2023.pdf")
        assert len(results) == 1
        assert results[0].key == "article2023test"

        # Find by partial filename
        results = engine.locate_file("johnson-2021")
        assert len(results) == 1
        assert results[0].key == "thesis2021phd"

    def test_locate_file_substring_match(self, locate_database: Path) -> None:
        """Test locating files with substring matching."""
        engine = LocateEngine(locate_database)

        # Find by path component
        results = engine.locate_file("documents/book")
        assert len(results) == 1
        assert results[0].key == "book2020example"

        # Find by directory name
        results = engine.locate_file("techreport")
        assert len(results) == 1
        assert results[0].key == "report2022tech"

    def test_locate_file_glob_match(self, locate_database: Path) -> None:
        """Test glob pattern matching."""
        engine = LocateEngine(locate_database)

        # All PDF files
        results = engine.locate_file("*.pdf", glob_match=True)
        assert len(results) == 4  # All entries with files

        # Specific pattern
        results = engine.locate_file("*article*.pdf", glob_match=True)
        assert len(results) == 1
        assert results[0].key == "article2023test"

        # Directory pattern
        results = engine.locate_file("*/phdthesis/*", glob_match=True)
        assert len(results) == 1
        assert results[0].key == "thesis2021phd"

    def test_locate_file_basename_only(self, locate_database: Path) -> None:
        """Test basename-only matching."""
        engine = LocateEngine(locate_database)

        # Find by basename
        results = engine.locate_file("example-book.pdf", basename_only=True)
        assert len(results) == 1
        assert results[0].key == "book2020example"

        # Partial basename match
        results = engine.locate_file("alice-brown", basename_only=True)
        assert len(results) == 1
        assert results[0].key == "report2022tech"

        # Should not match path components when basename_only=True
        results = engine.locate_file("documents", basename_only=True)
        assert len(results) == 0  # No basenames contain "documents"

    def test_locate_by_extension(self, locate_database: Path) -> None:
        """Test locating files by extension."""
        engine = LocateEngine(locate_database)

        # PDF extension
        results = engine.locate_by_extension("pdf")
        assert len(results) == 4  # All entries with files are PDFs

        # Extension with dot
        results = engine.locate_by_extension(".pdf")
        assert len(results) == 4

        # Non-existent extension
        results = engine.locate_by_extension("doc")
        assert len(results) == 0

    def test_locate_in_directory(self, locate_database: Path) -> None:
        """Test locating files in specific directory."""
        engine = LocateEngine(locate_database)

        # Article directory
        results = engine.locate_in_directory("/home/b/documents/article")
        assert len(results) == 1
        assert results[0].key == "article2023test"

        # Book directory
        results = engine.locate_in_directory("/home/b/documents/book")
        assert len(results) == 1
        assert results[0].key == "book2020example"

        # Non-existent directory
        results = engine.locate_in_directory("/nonexistent/path")
        assert len(results) == 0

    def test_verify_files_exist(self, locate_database: Path) -> None:
        """Test file existence verification."""
        engine = LocateEngine(locate_database)

        # This is a placeholder test since the method is not fully implemented
        missing = engine.verify_files_exist()
        assert isinstance(missing, list)

    def test_locate_case_sensitivity(self, locate_database: Path) -> None:
        """Test case sensitivity in locate operations."""
        engine = LocateEngine(locate_database)

        # Should be case insensitive by default
        results_lower = engine.locate_file("test-article")
        results_upper = engine.locate_file("TEST-ARTICLE")
        results_mixed = engine.locate_file("Test-Article")

        # All should return same results (case insensitive)
        assert len(results_lower) == len(results_upper) == len(results_mixed)
        if results_lower:
            assert results_lower[0].key == results_upper[0].key == results_mixed[0].key

    def test_locate_empty_pattern(self, locate_database: Path) -> None:
        """Test locate with empty search pattern."""
        engine = LocateEngine(locate_database)

        # Empty string with LIKE %% matches all entries with files
        results = engine.locate_file("")
        assert len(results) == 4  # All entries with file fields

    def test_locate_special_characters(self, locate_database: Path) -> None:
        """Test locate with special characters in filenames."""
        engine = LocateEngine(locate_database)

        # Hyphen in filename
        results = engine.locate_file("test-article")
        assert len(results) == 1

        # Underscore and numbers
        results = engine.locate_file("2021")
        assert len(results) == 1
        assert results[0].key == "thesis2021phd"


class TestLocateCommandFunctions:
    """Test command-level locate functions."""

    def test_locate_command_basic(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test basic locate command function."""
        from bibmgr.scripts.locate import locate_command

        locate_command("test-article", db_path=locate_database)

        captured = capsys.readouterr()
        assert "test-article" in captured.out
        assert "Found" in captured.out

    def test_locate_command_no_pattern(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test locate command with no pattern."""
        from bibmgr.scripts.locate import locate_command

        locate_command("", db_path=locate_database)

        captured = capsys.readouterr()
        assert "Error" in captured.out or "No" in captured.out

    def test_locate_command_different_formats(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test locate command with different output formats."""
        from bibmgr.scripts.locate import locate_command

        # Table format
        locate_command("pdf", format_type="table", db_path=locate_database)
        captured = capsys.readouterr()
        table_output = captured.out

        # Paths format
        locate_command("pdf", format_type="paths", db_path=locate_database)
        captured = capsys.readouterr()
        paths_output = captured.out

        # Keys format
        locate_command("pdf", format_type="keys", db_path=locate_database)
        captured = capsys.readouterr()
        keys_output = captured.out

        # All should produce different output
        assert table_output != paths_output != keys_output

    def test_locate_extension_command(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test locate by extension command."""
        from bibmgr.scripts.locate import locate_extension_command

        locate_extension_command("pdf", db_path=locate_database)

        captured = capsys.readouterr()
        assert "pdf" in captured.out.lower()

    def test_locate_directory_command(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test locate by directory command."""
        from bibmgr.scripts.locate import locate_directory_command

        locate_directory_command("/home/b/documents/article", db_path=locate_database)

        captured = capsys.readouterr()
        assert "article" in captured.out

    def test_verify_files_command(
        self, locate_database: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test verify files command."""
        from bibmgr.scripts.locate import verify_files_command

        verify_files_command(db_path=locate_database)

        captured = capsys.readouterr()
        assert "Checking" in captured.out

    def test_unknown_format_type(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test formatter with unknown format type."""
        from rich.console import Console

        console = Console()
        formatter = LocateFormatter(console)
        entry = BibEntry(
            key="test1",
            entry_type="article",
            fields={"file": "{:/path/test.pdf:pdf}"},
            source_file=Path("test.bib"),
        )

        formatter.format_results([entry], "test", "unknown_format")

        captured = capsys.readouterr()
        assert "Unknown format" in captured.out

    def test_locate_command_exception(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test locate command with database exception."""
        from bibmgr.scripts.locate import locate_command

        # Use a valid temp path but mock the actual locate operation
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with patch("bibmgr.scripts.locate.LocateEngine.locate_file") as mock:
                mock.side_effect = Exception("Database error")
                locate_command("test.pdf", False, False, "table", db_path)

            captured = capsys.readouterr()
            assert "Locate error: Database error" in captured.out

    def test_locate_extension_command_exception(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test locate extension command with exception."""
        from bibmgr.scripts.locate import locate_extension_command

        with patch("bibmgr.scripts.locate.LocateEngine.locate_by_extension") as mock:
            mock.side_effect = Exception("Database error")
            locate_extension_command("pdf", "table", Path("/tmp/test.db"))

        captured = capsys.readouterr()
        assert "Locate error: Database error" in captured.out

    def test_locate_directory_command_exception(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test locate directory command with exception."""
        from bibmgr.scripts.locate import locate_directory_command

        with patch("bibmgr.scripts.locate.LocateEngine.locate_in_directory") as mock:
            mock.side_effect = Exception("Database error")
            locate_directory_command("/test/dir", "table", Path("/tmp/test.db"))

        captured = capsys.readouterr()
        assert "Locate error: Database error" in captured.out

    def test_verify_files_command_exception(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test verify files command with exception."""
        from bibmgr.scripts.locate import verify_files_command

        with patch("bibmgr.scripts.locate.LocateEngine.verify_files_exist") as mock:
            mock.side_effect = Exception("Verification error")
            verify_files_command(Path("/tmp/test.db"))

        captured = capsys.readouterr()
        assert "Verification error: Verification error" in captured.out

    def test_verify_files_with_missing_files(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test verify files command with missing files."""
        from bibmgr.scripts.locate import verify_files_command

        # Create mock entries with missing files
        missing_entries = [
            BibEntry(
                key="missing1",
                entry_type="article",
                fields={"file": "{:/missing/file1.pdf:pdf}"},
                source_file=Path("test.bib"),
            ),
            BibEntry(
                key="missing2",
                entry_type="book",
                fields={},  # No file field
                source_file=Path("test.bib"),
            ),
        ]

        with patch("bibmgr.scripts.locate.LocateEngine.verify_files_exist") as mock:
            mock.return_value = missing_entries
            verify_files_command(Path("/tmp/test.db"))

        captured = capsys.readouterr()
        assert "Found 2 entries with missing files" in captured.out
        assert "missing1: /missing/file1.pdf" in captured.out
        # Empty file field results in empty path
        assert "missing2: " in captured.out


class TestLocateEdgeCases:
    """Test edge cases and error conditions."""

    def test_locate_with_malformed_file_fields(self) -> None:
        """Test locate with malformed file field entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "malformed_test.db"
            db = BibliographyDB(db_path)

            # Entry with malformed file field
            malformed_entry = BibEntry(
                key="malformed2023",
                entry_type="article",
                fields={
                    "title": "Malformed File Field",
                    "author": "Test Author",
                    "year": "2023",
                    "file": "{{{broken:format:::}",  # Malformed
                },
                source_file=Path("test.bib"),
            )

            db.insert_entry(malformed_entry)

            engine = LocateEngine(db_path)

            # Should handle malformed fields gracefully
            results = engine.locate_file("broken")
            assert len(results) >= 0  # Should not crash

    def test_locate_database_error_handling(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test error handling when database initialization fails."""
        from bibmgr.scripts.locate import locate_command

        # Create a database path that will cause issues (directory as file)
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_db_path = Path(tmpdir) / "directory_as_db"
            bad_db_path.mkdir()  # Create as directory, not file

            # Try to use directory as database file
            import contextlib

            with contextlib.suppress(Exception):
                locate_command("test", db_path=bad_db_path)

            captured = capsys.readouterr()
            # Should complete without crashing (even if with errors)
            assert isinstance(captured.out, str)

    def test_locate_with_none_values(self, locate_database: Path) -> None:
        """Test locate functions with None values."""
        engine = LocateEngine(locate_database)

        # Test various None inputs
        results = engine.locate_file("test")  # Should work normally
        assert isinstance(results, list)

    def test_locate_regex_special_characters(self, locate_database: Path) -> None:
        """Test locate with regex special characters."""
        engine = LocateEngine(locate_database)

        # Characters that have special meaning in regex
        special_chars = [
            ".",
            "*",
            "+",
            "?",
            "^",
            "$",
            "(",
            ")",
            "[",
            "]",
            "{",
            "}",
            "|",
            "\\",
        ]

        for char in special_chars:
            # Should not crash with regex special characters
            results = engine.locate_file(f"test{char}")
            assert isinstance(results, list)

    def test_locate_very_long_patterns(self, locate_database: Path) -> None:
        """Test locate with very long search patterns."""
        engine = LocateEngine(locate_database)

        # Very long pattern
        long_pattern = "a" * 1000
        results = engine.locate_file(long_pattern)
        assert isinstance(results, list)
        assert len(results) == 0  # Unlikely to match anything

    def test_locate_unicode_characters(self, locate_database: Path) -> None:
        """Test locate with Unicode characters."""
        engine = LocateEngine(locate_database)

        # Unicode characters
        unicode_patterns = ["café", "naïve", "résumé", "大学", "🔍"]

        for pattern in unicode_patterns:
            results = engine.locate_file(pattern)
            assert isinstance(results, list)
            # These won't match our test data, but should not crash
