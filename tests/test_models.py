"""Tests for bibliography models."""

from pathlib import Path

from bibmgr.models import BibEntry, ValidationError


class TestModels:
    """Test data models."""

    def test_bibentry_creation(self):
        """Test BibEntry creation."""
        entry = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"title": "Test Title", "author": "Test Author"},
            source_file=Path("test.bib"),
        )
        assert entry.key == "test_key"
        assert entry.entry_type == "article"
        assert entry.fields["title"] == "Test Title"
        assert entry.fields["author"] == "Test Author"
        assert entry.source_file == Path("test.bib")

    def test_bibentry_equality(self):
        """Test BibEntry equality comparison."""
        entry1 = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"title": "Test"},
            source_file=Path("test.bib"),
        )
        entry2 = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"title": "Test"},
            source_file=Path("test.bib"),
        )
        entry3 = BibEntry(
            key="different_key",
            entry_type="article",
            fields={"title": "Test"},
            source_file=Path("test.bib"),
        )
        assert entry1 == entry2
        assert entry1 != entry3

    def test_validation_error_creation(self):
        """Test ValidationError creation."""
        error = ValidationError(
            bib_file=Path("test.bib"),
            entry_key="test_key",
            error_type="test_error",
            message="Test error message",
        )
        assert error.bib_file == Path("test.bib")
        assert error.entry_key == "test_key"
        assert error.error_type == "test_error"
        assert error.message == "Test error message"

    def test_bibentry_update_field(self):
        """Test BibEntry update_field method."""
        entry = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"title": "Old Title"},
            source_file=Path("test.bib"),
        )
        entry.update_field("title", "New Title")
        assert entry.fields["title"] == "New Title"

        entry.update_field("author", "Test Author")
        assert entry.fields["author"] == "Test Author"

    def test_bibentry_remove_field(self):
        """Test BibEntry remove_field method."""
        entry = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"title": "Test", "author": "Author"},
            source_file=Path("test.bib"),
        )
        entry.remove_field("author")
        assert "author" not in entry.fields
        assert "title" in entry.fields

    def test_bibentry_set_file_path(self):
        """Test BibEntry set_file_path method."""
        entry = BibEntry(
            key="test_key",
            entry_type="article",
            fields={},
            source_file=Path("test.bib"),
        )
        entry.set_file_path(Path("/home/user/file.pdf"))
        assert entry.fields["file"] == "{:/home/user/file.pdf:pdf}"
        assert entry.file_path == Path("/home/user/file.pdf")

    def test_bibentry_to_bibtex(self):
        """Test BibEntry to_bibtex method."""
        entry = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"title": "Test Title", "author": "Test Author", "year": "2023"},
            source_file=Path("test.bib"),
        )
        bibtex = entry.to_bibtex()
        assert "@article{test_key," in bibtex
        assert "author = {Test Author}" in bibtex
        assert "title = {Test Title}" in bibtex
        assert "year = {2023}" in bibtex

    def test_bibentry_copy(self):
        """Test BibEntry copy method."""
        entry = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"title": "Test"},
            source_file=Path("test.bib"),
        )
        copy = entry.copy()
        assert copy == entry
        assert copy is not entry
        assert copy.fields is not entry.fields

        # Modify copy shouldn't affect original
        copy.update_field("title", "Modified")
        assert entry.fields["title"] == "Test"
        assert copy.fields["title"] == "Modified"

    def test_validation_error_str_with_file_path(self):
        """Test ValidationError string representation with file path."""
        error = ValidationError(
            bib_file=Path("test.bib"),
            entry_key="test_key",
            error_type="missing_file",
            message="File not found",
            file_path=Path("/path/to/file.pdf"),
        )
        str_repr = str(error)
        assert "test.bib[test_key]" in str_repr
        assert "missing_file" in str_repr
        assert "File not found" in str_repr
        assert "/path/to/file.pdf" in str_repr

    def test_validation_error_str_without_file_path(self):
        """Test ValidationError string representation without file path."""
        error = ValidationError(
            bib_file=Path("test.bib"),
            entry_key="test_key",
            error_type="missing_field",
            message="Missing title",
        )
        str_repr = str(error)
        assert "test.bib[test_key]" in str_repr
        assert "missing_field" in str_repr
        assert "Missing title" in str_repr
        assert ".pdf" not in str_repr

    def test_bibentry_file_path_none_field(self):
        """Test file_path property when file field is None."""
        entry = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"file": None},
            source_file=Path("test.bib"),
        )
        assert entry.file_path is None

    def test_bibentry_file_path_different_formats(self):
        """Test file_path extraction with different formats."""
        # Test format without leading colon
        entry1 = BibEntry(
            key="test1",
            entry_type="article",
            fields={"file": "/path/to/file.pdf:pdf"},
            source_file=Path("test.bib"),
        )
        assert entry1.file_path == Path("/path/to/file.pdf")

        # Test format with just path
        entry2 = BibEntry(
            key="test2",
            entry_type="article",
            fields={"file": "/path/to/file.pdf"},
            source_file=Path("test.bib"),
        )
        assert entry2.file_path == Path("/path/to/file.pdf")

        # Test empty path
        entry3 = BibEntry(
            key="test3",
            entry_type="article",
            fields={"file": "::pdf"},
            source_file=Path("test.bib"),
        )
        assert entry3.file_path is None

    def test_bibentry_validate_mandatory_fields_with_alternatives(self):
        """Test validate_mandatory_fields with author/editor alternatives."""
        # Book with editor but no author
        entry = BibEntry(
            key="test_book",
            entry_type="book",
            fields={
                "title": "Test Book",
                "editor": "Test Editor",
                "publisher": "Test Pub",
                "year": "2023",
            },
            source_file=Path("test.bib"),
        )
        missing = entry.validate_mandatory_fields()
        assert len(missing) == 0  # Should be valid with editor

        # Book with neither author nor editor
        entry2 = BibEntry(
            key="test_book2",
            entry_type="book",
            fields={"title": "Test Book", "publisher": "Test Pub", "year": "2023"},
            source_file=Path("test.bib"),
        )
        missing2 = entry2.validate_mandatory_fields()
        # Note: The MANDATORY_FIELDS dict doesn't include author/editor for book type
        # This is handled separately in the validators module
        assert len(missing2) == 0  # Based on current implementation

    def test_bibentry_validate_mandatory_fields_unknown_type(self):
        """Test validate_mandatory_fields with unknown entry type."""
        entry = BibEntry(
            key="test_unknown",
            entry_type="unknown_type",
            fields={"title": "Test"},
            source_file=Path("test.bib"),
        )
        missing = entry.validate_mandatory_fields()
        assert len(missing) == 0  # Unknown types have no mandatory fields

    def test_bibentry_to_bibtex_with_braces(self):
        """Test to_bibtex when values already have braces."""
        entry = BibEntry(
            key="test_key",
            entry_type="article",
            fields={"title": "{Test Title}", "author": "Test Author"},
            source_file=Path("test.bib"),
        )
        bibtex = entry.to_bibtex()
        # Should not double-wrap already braced values
        assert "title = {Test Title}" in bibtex
        # Should wrap unbraced values
        assert "author = {Test Author}" in bibtex

    def test_bibentry_to_bibtex_empty_fields(self):
        """Test to_bibtex with no fields."""
        entry = BibEntry(
            key="test_key",
            entry_type="misc",
            fields={},
            source_file=Path("test.bib"),
        )
        bibtex = entry.to_bibtex()
        assert "@misc{test_key" in bibtex
        assert bibtex.endswith("}")
        assert bibtex.count("\n") == 1  # Only one newline
