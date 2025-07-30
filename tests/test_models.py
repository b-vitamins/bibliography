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
