"""Tests for bibliography validators."""

import tempfile
from pathlib import Path

import pytest

from bibmgr.models import BibEntry
from bibmgr.validators import (
    check_duplicates,
    check_mandatory_fields,
    check_paths,
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
        assert "/nonexistent/file.pdf" in errors[0].message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
