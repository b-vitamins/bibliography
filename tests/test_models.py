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
