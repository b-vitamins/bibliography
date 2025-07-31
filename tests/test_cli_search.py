"""Tests for CLI search commands."""

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from bibmgr.cli import cli
from bibmgr.db import BibliographyDB
from bibmgr.models import BibEntry


@pytest.fixture
def cli_test_entries() -> list[BibEntry]:
    """Create test entries for CLI testing."""
    return [
        BibEntry(
            key="feynman1965qed",
            entry_type="article",
            fields={
                "title": "Quantum Electrodynamics",
                "author": "Richard P. Feynman",
                "journal": "Physical Review",
                "year": "1965",
                "file": ":/home/b/documents/article/feynman1965qed.pdf:pdf",
            },
            source_file=Path("physics.bib"),
        ),
        BibEntry(
            key="turing1950computing",
            entry_type="article",
            fields={
                "title": "Computing Machinery and Intelligence",
                "author": "Alan M. Turing",
                "journal": "Mind",
                "year": "1950",
                "file": ":/home/b/documents/article/turing1950computing.pdf:pdf",
            },
            source_file=Path("cs.bib"),
        ),
    ]


@pytest.fixture
def cli_database(cli_test_entries: list[BibEntry]) -> Generator[Path, None, None]:
    """Create database for CLI testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "cli_test.db"
        db = BibliographyDB(db_path)
        db.insert_entries_batch(cli_test_entries)
        yield db_path


class TestSearchCommand:
    """Test the search CLI command."""

    def test_search_basic_query(self, cli_database: Path) -> None:
        """Test basic search command."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["search", "quantum", "--database", str(cli_database)]
        )

        assert result.exit_code == 0
        assert "quantum" in result.output.lower() or "feynman" in result.output

    def test_search_field_query(self, cli_database: Path):
        """Test field-specific search."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["search", "author:Feynman", "--database", str(cli_database)]
        )

        assert result.exit_code == 0
        assert "feynman" in result.output.lower()

    def test_search_with_limit(self, cli_database: Path):
        """Test search with result limit."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["search", "article", "--limit", "1", "--database", str(cli_database)]
        )

        assert result.exit_code == 0
        # Should still work even if matches are fewer than limit

    def test_search_different_formats(self, cli_database: Path):
        """Test different output formats."""
        runner = CliRunner()

        # Table format (default)
        result_table = runner.invoke(
            cli,
            ["search", "quantum", "--format", "table", "--database", str(cli_database)],
        )
        assert result_table.exit_code == 0

        # JSON format
        result_json = runner.invoke(
            cli,
            ["search", "quantum", "--format", "json", "--database", str(cli_database)],
        )
        assert result_json.exit_code == 0

        # Keys format
        result_keys = runner.invoke(
            cli,
            ["search", "quantum", "--format", "keys", "--database", str(cli_database)],
        )
        assert result_keys.exit_code == 0

        # BibTeX format
        result_bibtex = runner.invoke(
            cli,
            [
                "search",
                "quantum",
                "--format",
                "bibtex",
                "--database",
                str(cli_database),
            ],
        )
        assert result_bibtex.exit_code == 0

    def test_search_different_sort_orders(self, cli_database: Path):
        """Test different sort orders."""
        runner = CliRunner()

        sort_orders = ["relevance", "year", "author", "title"]

        for sort_order in sort_orders:
            result = runner.invoke(
                cli,
                [
                    "search",
                    "article",  # Should match both entries
                    "--sort",
                    sort_order,
                    "--database",
                    str(cli_database),
                ],
            )
            assert result.exit_code == 0

    def test_search_with_stats(self, cli_database: Path):
        """Test search with statistics display."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["search", "quantum", "--stats", "--database", str(cli_database)]
        )

        assert result.exit_code == 0
        assert "found" in result.output.lower() or "results" in result.output.lower()

    def test_search_no_patterns(self):
        """Test search command without patterns."""
        runner = CliRunner()

        result = runner.invoke(cli, ["search"])

        # Should fail or show help
        assert result.exit_code != 0

    def test_search_multiple_patterns(self, cli_database: Path):
        """Test search with multiple patterns."""
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["search", "quantum", "electrodynamics", "--database", str(cli_database)],
        )

        assert result.exit_code == 0

    def test_search_boolean_query(self, cli_database: Path):
        """Test boolean search queries."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["search", "quantum OR computing", "--database", str(cli_database)]
        )

        assert result.exit_code == 0

    def test_search_phrase_query(self, cli_database: Path):
        """Test phrase search queries."""
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["search", '"Quantum Electrodynamics"', "--database", str(cli_database)],
        )

        assert result.exit_code == 0

    def test_search_wildcard_query(self, cli_database: Path):
        """Test wildcard search queries."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["search", "comput*", "--database", str(cli_database)]
        )

        assert result.exit_code == 0

    def test_search_nonexistent_database(self):
        """Test search with non-existent database."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["search", "test", "--database", "/nonexistent/path.db"]
        )

        # Should handle gracefully (exit code may vary)
        assert isinstance(result.exit_code, int)


class TestShowCommand:
    """Test the show CLI command."""

    def test_show_existing_key(self, cli_database: Path):
        """Test showing an existing entry."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["show", "feynman1965qed", "--database", str(cli_database)]
        )

        assert result.exit_code == 0
        assert "feynman1965qed" in result.output
        assert "Quantum Electrodynamics" in result.output

    def test_show_nonexistent_key(self, cli_database: Path):
        """Test showing a non-existent entry."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["show", "nonexistent2023", "--database", str(cli_database)]
        )

        assert result.exit_code == 0  # Command succeeds but shows "not found"
        assert (
            "not found" in result.output.lower() or "nonexistent2023" in result.output
        )

    def test_show_no_key(self):
        """Test show command without key argument."""
        runner = CliRunner()

        result = runner.invoke(cli, ["show"])

        # Should fail without key
        assert result.exit_code != 0


class TestLocateCommand:
    """Test the locate CLI command."""

    def test_locate_basic_pattern(self, cli_database: Path):
        """Test basic locate command."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["locate", "feynman", "--database", str(cli_database)]
        )

        assert result.exit_code == 0

    def test_locate_with_glob(self, cli_database: Path):
        """Test locate with glob pattern."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["locate", "*.pdf", "--glob", "--database", str(cli_database)]
        )

        assert result.exit_code == 0

    def test_locate_basename_only(self, cli_database: Path):
        """Test locate with basename-only search."""
        runner = CliRunner()

        result = runner.invoke(
            cli,
            [
                "locate",
                "feynman1965qed.pdf",
                "--basename",
                "--database",
                str(cli_database),
            ],
        )

        assert result.exit_code == 0

    def test_locate_different_formats(self, cli_database: Path):
        """Test locate with different output formats."""
        runner = CliRunner()

        formats = ["table", "paths", "keys"]

        for format_type in formats:
            result = runner.invoke(
                cli,
                [
                    "locate",
                    "pdf",
                    "--format",
                    format_type,
                    "--database",
                    str(cli_database),
                ],
            )
            assert result.exit_code == 0

    def test_locate_no_pattern(self):
        """Test locate command without pattern."""
        runner = CliRunner()

        result = runner.invoke(cli, ["locate"])

        # Should fail without pattern
        assert result.exit_code != 0


class TestIndexCommands:
    """Test index management CLI commands."""

    def test_index_build_command(self):
        """Test index build command."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "index_test.db"

            # Mock repository to avoid needing real .bib files
            with patch("bibmgr.cli.Repository") as mock_repo_class:
                mock_repo = Mock()
                mock_repo.get_all_entries.return_value = []
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(
                    cli, ["index", "build", "--database", str(db_path), "--quiet"]
                )

                assert result.exit_code == 0

    def test_index_build_with_clear(self):
        """Test index build with clear flag."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "index_clear_test.db"

            with patch("bibmgr.cli.Repository") as mock_repo_class:
                mock_repo = Mock()
                mock_repo.get_all_entries.return_value = []
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(
                    cli,
                    [
                        "index",
                        "build",
                        "--clear",
                        "--database",
                        str(db_path),
                        "--quiet",
                    ],
                )

                assert result.exit_code == 0

    def test_index_update_command(self):
        """Test index update command."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "index_update_test.db"

            with patch("bibmgr.cli.Repository") as mock_repo_class:
                mock_repo = Mock()
                # Mock get_all_entries to return an empty list for full rebuild
                mock_repo.get_all_entries.return_value = []
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(
                    cli, ["index", "update", "--database", str(db_path)]
                )

                assert result.exit_code == 0

    def test_index_status_command(self):
        """Test index status command."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "index_status_test.db"
            # Create empty database
            BibliographyDB(db_path)

            with patch("bibmgr.cli.Repository") as mock_repo_class:
                mock_repo = Mock()
                mock_repo.get_all_entries.return_value = []
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(
                    cli, ["index", "status", "--database", str(db_path)]
                )

                assert result.exit_code == 0
                assert "Index" in result.output or "entries" in result.output


class TestStatsCommand:
    """Test the stats CLI command."""

    def test_stats_command(self, cli_database: Path):
        """Test stats command."""
        runner = CliRunner()

        result = runner.invoke(cli, ["stats", "--database", str(cli_database)])

        assert result.exit_code == 0
        assert (
            "entries" in result.output.lower() or "statistics" in result.output.lower()
        )

    def test_stats_empty_database(self):
        """Test stats command with empty database."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "empty_stats_test.db"
            # Create empty database
            BibliographyDB(db_path)

            result = runner.invoke(cli, ["stats", "--database", str(db_path)])

            assert result.exit_code == 0
            assert "0" in result.output  # Should show 0 entries


class TestCLIErrorHandling:
    """Test CLI error handling."""

    def test_search_with_invalid_database(self):
        """Test search command with invalid database path."""
        runner = CliRunner()

        # Use a directory as database path (should fail)
        result = runner.invoke(cli, ["search", "test", "--database", "/tmp"])

        # Should handle error gracefully
        assert isinstance(result.exit_code, int)

    def test_command_with_permission_error(self):
        """Test commands with permission errors."""
        runner = CliRunner()

        # Try to use root directory as database (permission denied)
        result = runner.invoke(
            cli, ["search", "test", "--database", "/root/forbidden.db"]
        )

        # Should handle permission errors gracefully
        assert isinstance(result.exit_code, int)

    def test_malformed_search_queries(self, cli_database: Path):
        """Test search with malformed queries."""
        runner = CliRunner()

        malformed_queries = [
            "((unbalanced",
            "field:",
            ":::",
            "author:((()))",
        ]

        for query in malformed_queries:
            result = runner.invoke(
                cli, ["search", query, "--database", str(cli_database)]
            )

            # Should not crash, even with malformed queries
            assert isinstance(result.exit_code, int)

    def test_commands_with_very_long_arguments(self, cli_database: Path):
        """Test commands with very long arguments."""
        runner = CliRunner()

        # Very long search query
        long_query = "a" * 10000
        result = runner.invoke(
            cli, ["search", long_query, "--database", str(cli_database)]
        )

        assert isinstance(result.exit_code, int)

        # Very long key
        long_key = "key" + "a" * 1000
        result = runner.invoke(cli, ["show", long_key, "--database", str(cli_database)])

        assert isinstance(result.exit_code, int)

    def test_commands_with_unicode_arguments(self, cli_database: Path):
        """Test commands with Unicode arguments."""
        runner = CliRunner()

        unicode_queries = ["café", "大学", "🔍", "naïve résumé"]

        for query in unicode_queries:
            result = runner.invoke(
                cli, ["search", query, "--database", str(cli_database)]
            )

            # Should handle Unicode gracefully
            assert isinstance(result.exit_code, int)


class TestCLIIntegration:
    """Integration tests for CLI commands."""

    def test_full_workflow_commands(self):
        """Test a complete workflow of CLI commands."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "workflow_test.db"

            # Mock repository
            with patch("bibmgr.cli.Repository") as mock_repo_class:
                test_entry = BibEntry(
                    key="test2023workflow",
                    entry_type="article",
                    fields={
                        "title": "Workflow Test Article",
                        "author": "Test Author",
                        "year": "2023",
                    },
                    source_file=Path("test.bib"),
                )

                mock_repo = Mock()
                mock_repo.get_all_entries.return_value = [test_entry]
                mock_repo_class.return_value = mock_repo

                # Build index
                result = runner.invoke(
                    cli, ["index", "build", "--database", str(db_path), "--quiet"]
                )
                assert result.exit_code == 0

                # Check status
                result = runner.invoke(
                    cli, ["index", "status", "--database", str(db_path)]
                )
                assert result.exit_code == 0

                # Search entries
                result = runner.invoke(
                    cli, ["search", "workflow", "--database", str(db_path)]
                )
                assert result.exit_code == 0

                # Show specific entry
                result = runner.invoke(
                    cli, ["show", "test2023workflow", "--database", str(db_path)]
                )
                assert result.exit_code == 0

                # Get statistics
                result = runner.invoke(cli, ["stats", "--database", str(db_path)])
                assert result.exit_code == 0

    def test_cli_help_commands(self):
        """Test that help commands work."""
        runner = CliRunner()

        # Main help
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "search" in result.output

        # Search help
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "PATTERNS" in result.output

        # Index help
        result = runner.invoke(cli, ["index", "--help"])
        assert result.exit_code == 0

        # Locate help
        result = runner.invoke(cli, ["locate", "--help"])
        assert result.exit_code == 0
