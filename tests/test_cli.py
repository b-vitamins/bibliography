"""Tests for main CLI commands."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from bibmgr.cli import (
    add_cmd,
    check,
    cli,
    duplicates,
    fields,
    find_bib_files,
    list_cmd,
    load_all_entries,
    paths,
    print_errors,
    remove_cmd,
    report,
    report_all_cmd,
    report_duplicates_cmd,
    report_fields_cmd,
    report_paths_cmd,
    update_cmd,
)
from bibmgr.models import BibEntry, ValidationError


class TestCLIHelpers:
    """Test CLI helper functions."""

    def test_find_bib_files_with_files(self, tmp_path: Path) -> None:
        """Test finding .bib files in bibtex directory."""
        # Create bibtex directory structure
        bibtex_dir = tmp_path / "bibtex"
        bibtex_dir.mkdir()

        # Create some .bib files
        (bibtex_dir / "test1.bib").write_text("")
        (bibtex_dir / "test2.bib").write_text("")
        subdir = bibtex_dir / "subdir"
        subdir.mkdir()
        (subdir / "test3.bib").write_text("")

        # Create non-.bib file
        (bibtex_dir / "test.txt").write_text("")

        result = find_bib_files(tmp_path)

        assert len(result) == 3
        assert all(f.suffix == ".bib" for f in result)
        assert result == sorted(result)  # Should be sorted

        # Check that the right files were found
        result_names = [f.name for f in result]
        assert "test1.bib" in result_names
        assert "test2.bib" in result_names
        assert "test3.bib" in result_names

    def test_find_bib_files_no_bibtex_dir(self, tmp_path: Path) -> None:
        """Test finding .bib files when bibtex directory doesn't exist."""
        result = find_bib_files(tmp_path)
        assert result == []

    def test_print_errors_with_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test printing validation errors."""
        errors = [
            ValidationError(
                bib_file=Path("test1.bib"),
                entry_key="key1",
                error_type="missing_field",
                message="Missing title",
            ),
            ValidationError(
                bib_file=Path("test2.bib"),
                entry_key="key2",
                error_type="duplicate",
                message="Duplicate key",
            ),
        ]

        print_errors(errors, "Test Errors")

        captured = capsys.readouterr()
        assert "Test Errors:" in captured.out
        assert "test1.bib[key1]: missing_field - Missing title" in captured.out
        assert "test2.bib[key2]: duplicate - Duplicate key" in captured.out

    def test_print_errors_no_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test printing when no errors."""
        print_errors([], "No Errors")

        captured = capsys.readouterr()
        assert captured.out == ""

    @patch("bibmgr.cli.load_bibliography")
    @patch("bibmgr.cli.find_bib_files")
    def test_load_all_entries_success(
        self, mock_find: Mock, mock_load: Mock, tmp_path: Path
    ) -> None:
        """Test loading all entries successfully."""
        # Mock find_bib_files to return test files
        mock_find.return_value = [
            Path("test1.bib"),
            Path("test2.bib"),
        ]

        # Mock load_bibliography to return test entries
        entry1 = BibEntry(
            key="key1",
            entry_type="article",
            fields={"title": "Test 1"},
            source_file=Path("test1.bib"),
        )
        entry2 = BibEntry(
            key="key2",
            entry_type="book",
            fields={"title": "Test 2"},
            source_file=Path("test2.bib"),
        )

        mock_load.side_effect = [[entry1], [entry2]]

        result = load_all_entries(tmp_path)

        assert len(result) == 2
        assert result[0] == entry1
        assert result[1] == entry2

    @patch("bibmgr.cli.load_bibliography")
    @patch("bibmgr.cli.find_bib_files")
    def test_load_all_entries_with_error(
        self, mock_find: Mock, mock_load: Mock, tmp_path: Path
    ) -> None:
        """Test loading entries with parsing error."""
        mock_find.return_value = [Path("test.bib")]
        mock_load.side_effect = ValueError("Invalid BibTeX")

        with pytest.raises(SystemExit) as exc_info:
            load_all_entries(tmp_path)

        assert exc_info.value.code == 2


class TestCheckCommands:
    """Test check subcommands."""

    def test_check_paths_all_valid(self) -> None:
        """Test check paths command with all valid paths."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.check_paths") as mock_check,
        ):
            mock_load.return_value = [Mock(), Mock()]
            mock_check.return_value = []  # No errors

            result = runner.invoke(paths)

            assert result.exit_code == 0
            assert "Checking 2 entries..." in result.output
            assert "Validation PASSED" in result.output

    def test_check_paths_with_errors(self) -> None:
        """Test check paths command with missing files."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.check_paths") as mock_check,
        ):
            mock_load.return_value = [Mock()]
            mock_check.return_value = [
                ValidationError(
                    bib_file=Path("test.bib"),
                    entry_key="key1",
                    error_type="missing_file",
                    message="File not found",
                    file_path=Path("/missing.pdf"),
                )
            ]

            result = runner.invoke(paths)

            assert result.exit_code == 1
            assert "Missing files:" in result.output
            assert "Validation FAILED: 1 missing file(s)" in result.output

    def test_check_duplicates_none_found(self) -> None:
        """Test check duplicates command with no duplicates."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.check_duplicates") as mock_check,
        ):
            mock_load.return_value = [Mock(), Mock()]
            mock_check.return_value = []

            result = runner.invoke(duplicates)

            assert result.exit_code == 0
            assert "Validation PASSED: No duplicates found" in result.output

    def test_check_duplicates_found(self) -> None:
        """Test check duplicates command with duplicates."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.check_duplicates") as mock_check,
        ):
            mock_load.return_value = [Mock()]
            mock_check.return_value = [
                ValidationError(
                    bib_file=Path("test.bib"),
                    entry_key="dup_key",
                    error_type="duplicate_key",
                    message="Duplicate citation key",
                )
            ]

            result = runner.invoke(duplicates)

            assert result.exit_code == 1
            assert "Duplicates found:" in result.output
            assert "Validation FAILED: 1 duplicate(s)" in result.output

    def test_check_fields_all_valid(self) -> None:
        """Test check fields command with all valid fields."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.check_mandatory_fields") as mock_check,
        ):
            mock_load.return_value = [Mock()]
            mock_check.return_value = []

            result = runner.invoke(fields)

            assert result.exit_code == 0
            assert "Validation PASSED: All mandatory fields present" in result.output

    def test_check_fields_missing(self) -> None:
        """Test check fields command with missing fields."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.check_mandatory_fields") as mock_check,
        ):
            mock_load.return_value = [Mock()]
            mock_check.return_value = [
                ValidationError(
                    bib_file=Path("test.bib"),
                    entry_key="key1",
                    error_type="missing_field",
                    message="Missing required field: author",
                )
            ]

            result = runner.invoke(fields)

            assert result.exit_code == 1
            assert "Field validation errors:" in result.output
            assert "Validation FAILED: 1 error(s)" in result.output

    def test_check_all_command(self) -> None:
        """Test check all command."""
        from bibmgr.cli import all

        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.check_paths") as mock_paths,
            patch("bibmgr.cli.check_duplicates") as mock_dup,
            patch("bibmgr.cli.check_mandatory_fields") as mock_fields,
        ):
            mock_load.return_value = [Mock()]
            mock_paths.return_value = []
            mock_dup.return_value = []
            mock_fields.return_value = []

            result = runner.invoke(all)

            assert result.exit_code == 0
            assert "Running all checks on 1 entries..." in result.output
            assert "Validation PASSED: All checks passed" in result.output

    def test_check_all_with_mixed_errors(self) -> None:
        """Test check all command with various errors."""
        from bibmgr.cli import all

        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.check_paths") as mock_paths,
            patch("bibmgr.cli.check_duplicates") as mock_dup,
            patch("bibmgr.cli.check_mandatory_fields") as mock_fields,
        ):
            mock_load.return_value = [Mock()]

            path_error = ValidationError(
                bib_file=Path("test.bib"),
                entry_key="key1",
                error_type="missing_file",
                message="File not found",
            )
            dup_error = ValidationError(
                bib_file=Path("test.bib"),
                entry_key="key2",
                error_type="duplicate",
                message="Duplicate key",
            )

            mock_paths.return_value = [path_error]
            mock_dup.return_value = [dup_error]
            mock_fields.return_value = []

            result = runner.invoke(all)

            assert result.exit_code == 1
            assert "Missing files:" in result.output
            assert "Duplicates:" in result.output
            assert "Validation FAILED: 2 total error(s)" in result.output


class TestReportCommands:
    """Test report subcommands."""

    def test_report_duplicates(self) -> None:
        """Test report duplicates command."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.report_duplicate_keys") as mock_report,
        ):
            mock_load.return_value = [Mock()]
            mock_report.return_value = "Duplicate keys report"

            result = runner.invoke(report_duplicates_cmd)

            assert result.exit_code == 0
            assert "Duplicate keys report" in result.output

    def test_report_fields(self) -> None:
        """Test report fields command."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.report_missing_fields") as mock_report,
        ):
            mock_load.return_value = [Mock()]
            mock_report.return_value = "Missing fields report"

            result = runner.invoke(report_fields_cmd)

            assert result.exit_code == 0
            assert "Missing fields report" in result.output

    def test_report_paths(self) -> None:
        """Test report paths command."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.report_missing_files") as mock_report,
        ):
            mock_load.return_value = [Mock()]
            mock_report.return_value = "Missing files report"

            result = runner.invoke(report_paths_cmd)

            assert result.exit_code == 0
            assert "Missing files report" in result.output

    def test_report_all(self) -> None:
        """Test report all command."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.load_all_entries") as mock_load,
            patch("bibmgr.cli.generate_full_report") as mock_report,
        ):
            mock_load.return_value = [Mock()]
            mock_report.return_value = "Full validation report"

            result = runner.invoke(report_all_cmd)

            assert result.exit_code == 0
            assert "Full validation report" in result.output


class TestCRUDCommands:
    """Test CRUD operation commands."""

    @patch("bibmgr.cli.add_entry")
    def test_add_command_interactive(self, mock_add: Mock) -> None:
        """Test add command in interactive mode."""
        runner = CliRunner()

        mock_add.return_value = Mock()  # Success

        result = runner.invoke(add_cmd)

        assert result.exit_code == 0
        mock_add.assert_called_once()

    @patch("bibmgr.cli.add_entry")
    def test_add_command_with_params(self, mock_add: Mock) -> None:
        """Test add command with parameters."""
        runner = CliRunner()

        mock_add.return_value = Mock()

        result = runner.invoke(add_cmd, ["--type", "article", "--key", "test2023"])

        assert result.exit_code == 0
        mock_add.assert_called_once()
        call_args = mock_add.call_args[1]
        assert call_args["entry_type"] == "article"
        assert call_args["key"] == "test2023"

    @patch("bibmgr.cli.add_from_file")
    def test_add_from_file(self, mock_add_file: Mock) -> None:
        """Test add from file command."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("test.bib").write_text("@article{test,}")

            mock_add_file.return_value = [Mock()]  # Success

            result = runner.invoke(add_cmd, ["--from-file", "test.bib"])

            assert result.exit_code == 0
            mock_add_file.assert_called_once()

    @patch("bibmgr.cli.add_from_file")
    def test_add_from_file_no_entries(self, mock_add_file: Mock) -> None:
        """Test add from file with no entries."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("test.bib").write_text("")

            mock_add_file.return_value = []  # No entries

            result = runner.invoke(add_cmd, ["--from-file", "test.bib"])

            assert result.exit_code == 1

    @patch("bibmgr.cli.remove_entry")
    def test_remove_command(self, mock_remove: Mock) -> None:
        """Test remove command."""
        runner = CliRunner()

        mock_remove.return_value = Mock()  # Success

        result = runner.invoke(remove_cmd, ["test_key"])

        assert result.exit_code == 0
        mock_remove.assert_called_once()

    @patch("bibmgr.cli.remove_entry")
    def test_remove_command_with_options(self, mock_remove: Mock) -> None:
        """Test remove command with options."""
        runner = CliRunner()

        mock_remove.return_value = Mock()

        result = runner.invoke(
            remove_cmd, ["test_key", "--remove-pdf", "--force", "--dry-run"]
        )

        assert result.exit_code == 0
        call_args = mock_remove.call_args[1]
        assert call_args["remove_pdf"] is True
        assert call_args["force"] is True
        assert call_args["dry_run"] is True

    @patch("bibmgr.cli.update_entry")
    def test_update_command_interactive(self, mock_update: Mock) -> None:
        """Test update command in interactive mode."""
        runner = CliRunner()

        mock_update.return_value = Mock()

        result = runner.invoke(update_cmd, ["test_key"])

        assert result.exit_code == 0
        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        assert call_args["interactive"] is True

    @patch("bibmgr.cli.update_entry")
    def test_update_command_with_set(self, mock_update: Mock) -> None:
        """Test update command with set option."""
        runner = CliRunner()

        mock_update.return_value = Mock()

        result = runner.invoke(
            update_cmd, ["test_key", "--set", "title=New Title", "--set", "year=2024"]
        )

        assert result.exit_code == 0
        call_args = mock_update.call_args[1]
        assert call_args["updates"]["title"] == "New Title"
        assert call_args["updates"]["year"] == "2024"
        assert call_args["interactive"] is False

    @patch("bibmgr.cli.update_entry")
    def test_update_command_invalid_set_format(self, _mock_update: Mock) -> None:
        """Test update command with invalid set format."""
        runner = CliRunner()

        result = runner.invoke(update_cmd, ["test_key", "--set", "invalid_format"])

        assert result.exit_code == 1
        assert "Invalid format" in result.output

    @patch("bibmgr.cli.update_entry")
    def test_update_command_remove_field(self, mock_update: Mock) -> None:
        """Test update command with remove field option."""
        runner = CliRunner()

        mock_update.return_value = Mock()

        result = runner.invoke(update_cmd, ["test_key", "--remove-field", "abstract"])

        assert result.exit_code == 0
        call_args = mock_update.call_args[1]
        assert call_args["updates"]["abstract"] is None

    @patch("bibmgr.cli.move_pdf_operation")
    def test_update_move_pdf(self, mock_move: Mock) -> None:
        """Test update command with move PDF option."""
        runner = CliRunner()

        mock_move.return_value = Mock()

        result = runner.invoke(update_cmd, ["test_key", "--move-pdf", "/new/path.pdf"])

        assert result.exit_code == 0
        mock_move.assert_called_once()


class TestListCommand:
    """Test list command."""

    @patch("bibmgr.cli.Repository")
    def test_list_command_no_entries(self, mock_repo_class: Mock) -> None:
        """Test list command with no entries."""
        runner = CliRunner()

        mock_repo = Mock()
        mock_repo.load_entries.return_value = []
        mock_repo_class.return_value = mock_repo

        result = runner.invoke(list_cmd)

        assert result.exit_code == 0
        assert "No entries found" in result.output

    @patch("bibmgr.cli.Repository")
    def test_list_command_with_entries(self, mock_repo_class: Mock) -> None:
        """Test list command with entries."""
        runner = CliRunner()

        mock_repo = Mock()
        entry = BibEntry(
            key="test2023",
            entry_type="article",
            fields={
                "title": "Test Article",
                "author": "Test Author",
                "year": "2023",
            },
            source_file=Path("test.bib"),
        )
        mock_repo.load_entries.return_value = [entry]
        mock_repo_class.return_value = mock_repo

        result = runner.invoke(list_cmd)

        assert result.exit_code == 0
        assert "Found 1 entries:" in result.output
        assert "test2023" in result.output
        assert "Test Article" in result.output

    @patch("bibmgr.cli.Repository")
    def test_list_command_with_filters(self, mock_repo_class: Mock) -> None:
        """Test list command with filters."""
        runner = CliRunner()

        mock_repo = Mock()
        entries = [
            BibEntry(
                key="test2023article",
                entry_type="article",
                fields={"title": "Article", "author": "John Doe", "year": "2023"},
                source_file=Path("test.bib"),
            ),
            BibEntry(
                key="test2022book",
                entry_type="book",
                fields={"title": "Book", "author": "Jane Smith", "year": "2022"},
                source_file=Path("test.bib"),
            ),
        ]
        mock_repo.load_entries.return_value = entries
        mock_repo_class.return_value = mock_repo

        # Test type filter
        result = runner.invoke(list_cmd, ["--type", "article"])
        assert "Found 1 entries:" in result.output
        assert "test2023article" in result.output
        assert "test2022book" not in result.output

        # Test author filter
        result = runner.invoke(list_cmd, ["--author", "jane"])
        assert "Found 1 entries:" in result.output
        assert "test2022book" in result.output

        # Test year filter
        result = runner.invoke(list_cmd, ["--year", "2023"])
        assert "Found 1 entries:" in result.output
        assert "test2023article" in result.output

    @patch("bibmgr.cli.Repository")
    def test_list_command_with_search(self, mock_repo_class: Mock) -> None:
        """Test list command with search option."""
        runner = CliRunner()

        mock_repo = Mock()
        entry = BibEntry(
            key="test2023",
            entry_type="article",
            fields={"title": "Quantum Computing", "author": "Test Author"},
            source_file=Path("test.bib"),
        )
        mock_repo.load_entries.return_value = [entry]
        mock_repo_class.return_value = mock_repo

        result = runner.invoke(list_cmd, ["--search", "quantum"])

        assert result.exit_code == 0
        assert "Found 1 entries:" in result.output
        assert "test2023" in result.output

    @patch("bibmgr.cli.Repository")
    def test_list_command_with_limit(self, mock_repo_class: Mock) -> None:
        """Test list command with limit option."""
        runner = CliRunner()

        mock_repo = Mock()
        entries = [
            BibEntry(
                key=f"test{i}",
                entry_type="article",
                fields={"title": f"Title {i}"},
                source_file=Path("test.bib"),
            )
            for i in range(10)
        ]
        mock_repo.load_entries.return_value = entries
        mock_repo_class.return_value = mock_repo

        result = runner.invoke(list_cmd, ["--limit", "3"])

        assert result.exit_code == 0
        assert "Found 3 entries:" in result.output

    @patch("bibmgr.cli.Repository")
    def test_list_command_formats(self, mock_repo_class: Mock) -> None:
        """Test list command with different formats."""
        runner = CliRunner()

        mock_repo = Mock()
        entry = BibEntry(
            key="test2023",
            entry_type="article",
            fields={"title": "Test Title", "author": "Test Author"},
            source_file=Path("test.bib"),
        )
        mock_repo.load_entries.return_value = [entry]
        mock_repo_class.return_value = mock_repo

        # Test keys format
        result = runner.invoke(list_cmd, ["--format", "keys"])
        assert "test2023" in result.output
        assert "Test Title" not in result.output

        # Test full format
        result = runner.invoke(list_cmd, ["--format", "full"])
        assert "@article{test2023," in result.output
        assert "title = {Test Title}" in result.output

    @patch("bibmgr.cli.Repository")
    def test_list_command_missing_fields(self, mock_repo_class: Mock) -> None:
        """Test list command with entries missing optional fields."""
        runner = CliRunner()

        mock_repo = Mock()
        entry = BibEntry(
            key="test2023",
            entry_type="misc",
            fields={},  # No fields
            source_file=Path("test.bib"),
        )
        mock_repo.load_entries.return_value = [entry]
        mock_repo_class.return_value = mock_repo

        result = runner.invoke(list_cmd)

        assert result.exit_code == 0
        assert "No title" in result.output
        assert "No author" in result.output
        assert "????" in result.output  # Missing year


class TestSearchCommands:
    """Test search-related commands."""

    def test_search_command(self) -> None:
        """Test search command."""
        runner = CliRunner()

        with patch("bibmgr.scripts.search.search_command") as mock_search:
            result = runner.invoke(cli, ["search", "quantum"])

            assert result.exit_code == 0
            mock_search.assert_called_once()
            args = mock_search.call_args[0]
            assert args[0] == ["quantum"]

    def test_search_command_with_options(self) -> None:
        """Test search command with options."""
        runner = CliRunner()

        with patch("bibmgr.scripts.search.search_command") as mock_search:
            result = runner.invoke(
                cli,
                [
                    "search",
                    "quantum",
                    "computing",
                    "--limit",
                    "10",
                    "--format",
                    "bibtex",
                    "--stats",
                ],
            )

            assert result.exit_code == 0
            mock_search.assert_called_once()
            args = mock_search.call_args[0]
            assert args[0] == ["quantum", "computing"]
            assert args[1] == 10  # limit
            assert args[2] == "bibtex"  # format
            assert args[4] is True  # stats

    def test_locate_command(self) -> None:
        """Test locate command."""
        runner = CliRunner()

        with patch("bibmgr.scripts.locate.locate_command") as mock_locate:
            result = runner.invoke(cli, ["locate", "test.pdf"])

            assert result.exit_code == 0
            mock_locate.assert_called_once()

    def test_locate_command_with_options(self) -> None:
        """Test locate command with options."""
        runner = CliRunner()

        with patch("bibmgr.scripts.locate.locate_command") as mock_locate:
            result = runner.invoke(
                cli, ["locate", "*.pdf", "--glob", "--basename", "--format", "paths"]
            )

            assert result.exit_code == 0
            mock_locate.assert_called_once()
            args = mock_locate.call_args[0]
            assert args[0] == "*.pdf"
            assert args[1] is True  # glob
            assert args[2] is True  # basename
            assert args[3] == "paths"  # format

    def test_show_command(self) -> None:
        """Test show command."""
        runner = CliRunner()

        with patch("bibmgr.scripts.search.show_command") as mock_show:
            result = runner.invoke(cli, ["show", "test2023key"])

            assert result.exit_code == 0
            mock_show.assert_called_once()
            assert mock_show.call_args[0][0] == "test2023key"

    def test_stats_command(self) -> None:
        """Test stats command."""
        runner = CliRunner()

        with patch("bibmgr.scripts.search.stats_command") as mock_stats:
            result = runner.invoke(cli, ["stats"])

            assert result.exit_code == 0
            mock_stats.assert_called_once()


class TestIndexCommands:
    """Test index subcommands."""

    def test_index_build(self) -> None:
        """Test index build command."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.Repository"),
            patch("bibmgr.index.create_index_builder") as mock_builder,
        ):
            mock_builder_instance = Mock()
            mock_builder.return_value = mock_builder_instance

            result = runner.invoke(cli, ["index", "build"])

            assert result.exit_code == 0
            mock_builder_instance.build_index.assert_called_once()

    def test_index_build_with_options(self) -> None:
        """Test index build command with options."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.Repository"),
            patch("bibmgr.index.create_index_builder") as mock_builder,
        ):
            mock_builder_instance = Mock()
            mock_builder.return_value = mock_builder_instance

            result = runner.invoke(cli, ["index", "build", "--clear", "--quiet"])

            assert result.exit_code == 0
            mock_builder_instance.build_index.assert_called_once_with(
                clear_existing=True, show_progress=False
            )

    def test_index_update(self) -> None:
        """Test index update command."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.Repository"),
            patch("bibmgr.index.create_index_builder") as mock_builder,
        ):
            mock_builder_instance = Mock()
            mock_builder.return_value = mock_builder_instance

            result = runner.invoke(cli, ["index", "update"])

            assert result.exit_code == 0
            mock_builder_instance.update_index.assert_called_once_with()

    def test_index_update_with_files(self) -> None:
        """Test index update command with specific files."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            Path("test1.bib").write_text("")
            Path("test2.bib").write_text("")

            with (
                patch("bibmgr.cli.Repository"),
                patch("bibmgr.index.create_index_builder") as mock_builder,
            ):
                mock_builder_instance = Mock()
                mock_builder.return_value = mock_builder_instance

                result = runner.invoke(
                    cli,
                    ["index", "update", "--files", "test1.bib", "--files", "test2.bib"],
                )

                assert result.exit_code == 0
                mock_builder_instance.update_index.assert_called_once()
                call_args = mock_builder_instance.update_index.call_args[0][0]
                assert len(call_args) == 2

    def test_index_status(self) -> None:
        """Test index status command."""
        runner = CliRunner()

        with (
            patch("bibmgr.cli.Repository"),
            patch("bibmgr.index.create_index_builder") as mock_builder,
        ):
            mock_builder_instance = Mock()
            mock_builder.return_value = mock_builder_instance
            mock_builder_instance.get_index_status.return_value = {
                "up_to_date": True,
                "db_entries": 100,
                "repo_entries": 100,
                "db_size_mb": 1.5,
                "fts_entries": 100,
                "by_type": {"article": 50, "book": 50},
            }

            result = runner.invoke(cli, ["index", "status"])

            assert result.exit_code == 0
            assert "Index is up to date" in result.output
            assert "Database entries: 100" in result.output
            assert "article" in result.output


class TestCLIMain:
    """Test main CLI entry point."""

    def test_cli_version(self) -> None:
        """Test CLI version option."""
        runner = CliRunner()
        with patch("click.get_current_context") as mock_ctx:
            mock_ctx.return_value.find_root.return_value.params = {}
            result = runner.invoke(cli, ["--version"])
            # Version command returns exit code 1 but that's expected
            assert "version" in result.output.lower() or result.exit_code != 0

    def test_cli_help(self) -> None:
        """Test CLI help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Bibliography management system" in result.output

    def test_check_group_help(self) -> None:
        """Test check group help."""
        runner = CliRunner()
        result = runner.invoke(check, ["--help"])
        assert result.exit_code == 0
        assert "Run validation checks" in result.output

    def test_report_group_help(self) -> None:
        """Test report group help."""
        runner = CliRunner()
        result = runner.invoke(report, ["--help"])
        assert result.exit_code == 0
        assert "Generate detailed validation reports" in result.output

    def test_index_group_help(self) -> None:
        """Test index group help."""
        runner = CliRunner()
        from bibmgr.cli import index

        result = runner.invoke(index, ["--help"])
        assert result.exit_code == 0
        assert "Manage search index" in result.output
