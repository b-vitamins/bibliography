"""Tests for bibliography validators."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

from bibmgr.models import BibEntry
from bibmgr.validators import (
    check_duplicates,
    check_mandatory_fields,
    check_paths,
    load_bibliography,
)


class TestValidators:
    """Test validation functions."""

    def test_check_duplicates_no_duplicates(self):
        """Test duplicate checker with unique entries."""
        entries = [
            BibEntry(
                key="feynman1965",
                entry_type="article",
                fields={"title": "Test 1"},
                source_file=Path("test1.bib"),
            ),
            BibEntry(
                key="einstein1905",
                entry_type="article",
                fields={"title": "Test 2"},
                source_file=Path("test2.bib"),
            ),
        ]
        errors = check_duplicates(entries)
        assert len(errors) == 0

    def test_check_duplicates_with_duplicates(self):
        """Test duplicate checker with duplicate keys."""
        entries = [
            BibEntry(
                key="duplicate_key",
                entry_type="article",
                fields={"title": "Test 1"},
                source_file=Path("test1.bib"),
            ),
            BibEntry(
                key="duplicate_key",
                entry_type="article",
                fields={"title": "Test 2"},
                source_file=Path("test2.bib"),
            ),
        ]
        errors = check_duplicates(entries)
        assert len(errors) == 1
        assert errors[0].error_type == "duplicate_key"
        assert errors[0].entry_key == "duplicate_key"

    def test_check_mandatory_fields_complete(self):
        """Test mandatory field checker with complete entry."""
        entries = [
            BibEntry(
                key="complete_article",
                entry_type="article",
                fields={
                    "author": "Test Author",
                    "title": "Test Title",
                    "journal": "Test Journal",
                    "year": "2023",
                },
                source_file=Path("test.bib"),
            )
        ]
        errors = check_mandatory_fields(entries)
        assert len(errors) == 0

    def test_check_mandatory_fields_missing(self):
        """Test mandatory field checker with incomplete entry."""
        entries = [
            BibEntry(
                key="incomplete_article",
                entry_type="article",
                fields={"title": "Test Title"},  # Missing author, journal, year
                source_file=Path("test.bib"),
            )
        ]
        errors = check_mandatory_fields(entries)
        assert len(errors) == 1
        assert errors[0].error_type == "missing_fields"
        assert "author" in errors[0].message
        assert "journal" in errors[0].message
        assert "year" in errors[0].message

    def test_check_paths_existing_file(self):
        """Test path checker with existing file."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            temp_path = tf.name
            try:
                entries = [
                    BibEntry(
                        key="test_entry",
                        entry_type="article",
                        fields={"file": f":{temp_path}:pdf"},
                        source_file=Path("test.bib"),
                    )
                ]
                errors = check_paths(entries)
                assert len(errors) == 0
            finally:
                Path(temp_path).unlink()

    def test_check_paths_missing_file(self):
        """Test path checker with missing file."""
        entries = [
            BibEntry(
                key="test_entry",
                entry_type="article",
                fields={"file": ":/nonexistent/file.pdf:pdf"},
                source_file=Path("test.bib"),
            )
        ]
        errors = check_paths(entries)
        assert len(errors) == 1
        assert errors[0].error_type == "missing_file"
        assert errors[0].message == "File not found"

    def test_load_bibliography_success(self):
        """Test loading a valid bibliography file."""
        bib_content = """
        @article{test2023,
            author = {Test Author},
            title = {Test Title},
            journal = {Test Journal},
            year = {2023}
        }
        """

        with (
            patch("builtins.open", mock_open(read_data=bib_content)),
            patch("bibtexparser.load") as mock_load,
        ):
            mock_db = Mock()
            mock_db.entries = [
                {
                    "ID": "test2023",
                    "ENTRYTYPE": "article",
                    "author": "Test Author",
                    "title": "Test Title",
                    "journal": "Test Journal",
                    "year": "2023",
                },
            ]
            mock_load.return_value = mock_db

            entries = list(load_bibliography(Path("test.bib")))

            assert len(entries) == 1
            assert entries[0].key == "test2023"
            assert entries[0].entry_type == "article"

    def test_load_bibliography_parse_error(self):
        """Test loading bibliography with parse error."""
        with (
            patch("builtins.open", mock_open(read_data="invalid")),
            patch("bibtexparser.load") as mock_load,
        ):
            mock_load.side_effect = Exception("Parse error")

            with pytest.raises(ValueError) as exc_info:
                list(load_bibliography(Path("test.bib")))

            assert "Failed to parse test.bib" in str(exc_info.value)

    def test_load_bibliography_file_not_found(self):
        """Test loading non-existent bibliography file."""
        with patch("builtins.open") as mock_open_func:
            mock_open_func.side_effect = FileNotFoundError("No such file")

            with pytest.raises(ValueError) as exc_info:
                list(load_bibliography(Path("nonexistent.bib")))

            assert "Failed to parse" in str(exc_info.value)

    def test_check_duplicates_duplicate_paths(self):
        """Test duplicate file paths detection."""
        entries = [
            BibEntry(
                key="key1",
                entry_type="article",
                fields={"file": "{:/same/path.pdf:pdf}"},
                source_file=Path("file1.bib"),
            ),
            BibEntry(
                key="key2",
                entry_type="book",
                fields={"file": "{:/same/path.pdf:pdf}"},
                source_file=Path("file2.bib"),
            ),
        ]

        errors = check_duplicates(entries)

        assert len(errors) == 1
        assert errors[0].error_type == "duplicate_path"
        assert "first in key1" in errors[0].message

    def test_check_mandatory_fields_unknown_type(self):
        """Test mandatory fields with unknown entry type."""
        entries = [
            BibEntry(
                key="unknown1",
                entry_type="unknowntype",
                fields={"title": "Title"},
                source_file=Path("test.bib"),
            ),
        ]

        errors = check_mandatory_fields(entries)

        assert len(errors) == 1
        assert errors[0].error_type == "unknown_type"
        assert "Unknown entry type: unknowntype" in errors[0].message

    def test_check_mandatory_fields_book_author_editor(self):
        """Test book entries with author/editor alternatives."""
        # Book with author (valid)
        entry1 = BibEntry(
            key="book1",
            entry_type="book",
            fields={
                "title": "Title",
                "publisher": "Pub",
                "year": "2023",
                "author": "Author",
            },
            source_file=Path("test.bib"),
        )

        # Book with editor (valid)
        entry2 = BibEntry(
            key="book2",
            entry_type="book",
            fields={
                "title": "Title",
                "publisher": "Pub",
                "year": "2023",
                "editor": "Editor",
            },
            source_file=Path("test.bib"),
        )

        # Book with neither (invalid)
        entry3 = BibEntry(
            key="book3",
            entry_type="book",
            fields={"title": "Title", "publisher": "Pub", "year": "2023"},
            source_file=Path("test.bib"),
        )

        errors = check_mandatory_fields([entry1, entry2, entry3])

        assert len(errors) == 1
        assert errors[0].entry_key == "book3"
        assert "author/editor" in errors[0].message

    def test_check_mandatory_fields_inbook_special_cases(self):
        """Test inbook entries with special field requirements."""
        # Valid with author and chapter
        entry1 = BibEntry(
            key="inbook1",
            entry_type="inbook",
            fields={
                "title": "Title",
                "publisher": "Pub",
                "year": "2023",
                "author": "Author",
                "chapter": "5",
            },
            source_file=Path("test.bib"),
        )

        # Invalid - missing author/editor
        entry2 = BibEntry(
            key="inbook2",
            entry_type="inbook",
            fields={
                "title": "Title",
                "publisher": "Pub",
                "year": "2023",
                "chapter": "5",
            },
            source_file=Path("test.bib"),
        )

        # Invalid - missing chapter/pages
        entry3 = BibEntry(
            key="inbook3",
            entry_type="inbook",
            fields={
                "title": "Title",
                "publisher": "Pub",
                "year": "2023",
                "author": "Author",
            },
            source_file=Path("test.bib"),
        )

        errors = check_mandatory_fields([entry1, entry2, entry3])

        assert len(errors) == 2
        error_keys = {e.entry_key for e in errors}
        assert error_keys == {"inbook2", "inbook3"}

        # Check specific error messages
        for error in errors:
            if error.entry_key == "inbook2":
                assert "author/editor" in error.message
            elif error.entry_key == "inbook3":
                assert "chapter/pages" in error.message

    def test_check_duplicates_multiple_duplicate_keys(self):
        """Test multiple entries with same key."""
        entries = [
            BibEntry(
                key="dup_key",
                entry_type="article",
                fields={},
                source_file=Path("file1.bib"),
            ),
            BibEntry(
                key="dup_key",
                entry_type="book",
                fields={},
                source_file=Path("file2.bib"),
            ),
            BibEntry(
                key="dup_key",
                entry_type="misc",
                fields={},
                source_file=Path("file3.bib"),
            ),
        ]

        errors = check_duplicates(entries)

        # Should report 2 duplicates (not the first occurrence)
        assert len(errors) == 2
        assert all(e.error_type == "duplicate_key" for e in errors)
        assert all("first in file1.bib" in e.message for e in errors)

    def test_check_paths_no_file_field(self):
        """Test path checking for entries without file field."""
        entries = [
            BibEntry(
                key="no_file",
                entry_type="article",
                fields={"title": "Test"},  # No file field
                source_file=Path("test.bib"),
            ),
            BibEntry(
                key="null_file",
                entry_type="book",
                fields={"file": None},  # Null file field
                source_file=Path("test.bib"),
            ),
        ]

        errors = check_paths(entries)
        assert len(errors) == 0

    def test_load_bibliography_entry_without_id(self):
        """Test loading entry without ID field."""
        with (
            patch("builtins.open", mock_open(read_data="")),
            patch("bibtexparser.load") as mock_load,
        ):
            mock_db = Mock()
            mock_db.entries = [
                {
                    "ENTRYTYPE": "article",
                    "title": "Test",
                    # No ID field
                }
            ]
            mock_load.return_value = mock_db

            entries = list(load_bibliography(Path("test.bib")))

            assert len(entries) == 1
            assert entries[0].key == ""  # Empty key

    def test_check_mandatory_fields_case_insensitive(self):
        """Test entry type case insensitivity."""
        entries = [
            BibEntry(
                key="test1",
                entry_type="Article",  # Capitalized
                fields={
                    "author": "Author",
                    "title": "Title",
                    "journal": "Journal",
                    "year": "2023",
                },
                source_file=Path("test.bib"),
            ),
        ]

        errors = check_mandatory_fields(entries)
        assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
