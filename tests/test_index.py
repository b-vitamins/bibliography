"""Tests for indexing functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from bibmgr.db import BibliographyDB
from bibmgr.index import IndexBuilder, create_index_builder, get_default_db_path
from bibmgr.models import BibEntry
from bibmgr.repository import Repository


class TestIndexBuilder:
    """Test the IndexBuilder class."""

    def test_index_builder_initialization(self):
        """Test IndexBuilder can be initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Mock repository
            repo = Mock(spec=Repository)

            builder = IndexBuilder(db, repo)
            assert builder.db is db
            assert builder.repository is repo

    def test_build_empty_index(self):
        """Test building index with no entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Mock repository with no entries
            repo = Mock(spec=Repository)
            repo.get_all_entries.return_value = []

            builder = IndexBuilder(db, repo)

            # Should handle empty entries gracefully
            builder.build_index(show_progress=False)

            # Verify no entries were indexed
            stats = db.get_statistics()
            assert stats["total_entries"] == 0

    def test_build_index_with_entries(self):
        """Test building index with sample entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Create sample entries
            entries = [
                BibEntry(
                    key="test2023example",
                    entry_type="article",
                    fields={
                        "title": "Test Article",
                        "author": "John Doe",
                        "year": "2023",
                    },
                    source_file=Path("test.bib"),
                )
            ]

            # Mock repository
            repo = Mock(spec=Repository)
            repo.get_all_entries.return_value = entries

            builder = IndexBuilder(db, repo)

            # Build index
            builder.build_index(show_progress=False)

            # Verify entries were indexed
            stats = db.get_statistics()
            assert stats["total_entries"] == 1
            assert stats["fts_entries"] == 1

    def test_build_index_clear_existing(self):
        """Test that clear_existing works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Add initial entry
            entry1 = BibEntry(
                key="initial2023",
                entry_type="article",
                fields={"title": "Initial", "author": "Author1", "year": "2023"},
                source_file=Path("initial.bib"),
            )
            db.insert_entry(entry1)

            # New entries for rebuild
            entries = [
                BibEntry(
                    key="new2023",
                    entry_type="article",
                    fields={"title": "New", "author": "Author2", "year": "2023"},
                    source_file=Path("new.bib"),
                )
            ]

            repo = Mock(spec=Repository)
            repo.get_all_entries.return_value = entries

            builder = IndexBuilder(db, repo)

            # Build with clear_existing=True
            builder.build_index(clear_existing=True, show_progress=False)

            # Should have only new entry
            stats = db.get_statistics()
            assert stats["total_entries"] == 1

            # Should not find the initial entry
            result = db.get_entry_by_key("initial2023")
            assert result is None

            # Should find the new entry
            result = db.get_entry_by_key("new2023")
            assert result is not None

    def test_get_index_status(self):
        """Test getting index status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            entries = [
                BibEntry(
                    key="test2023",
                    entry_type="article",
                    fields={"title": "Test", "author": "Author", "year": "2023"},
                    source_file=Path("test.bib"),
                )
            ]

            repo = Mock(spec=Repository)
            repo.get_all_entries.return_value = entries

            builder = IndexBuilder(db, repo)
            builder.build_index(show_progress=False)

            # Get status
            status = builder.get_index_status()

            assert status["db_entries"] == 1
            assert status["repo_entries"] == 1
            assert status["up_to_date"] is True
            assert "by_type" in status
            assert "db_size_mb" in status

    def test_update_index_specific_files(self):
        """Test updating index for specific files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Initial entry
            entry1 = BibEntry(
                key="existing2023",
                entry_type="article",
                fields={"title": "Existing", "author": "Author1", "year": "2023"},
                source_file=Path("existing.bib"),
            )
            db.insert_entry(entry1)

            # New entries for update
            new_entries = [
                BibEntry(
                    key="updated2023",
                    entry_type="article",
                    fields={"title": "Updated", "author": "Author2", "year": "2023"},
                    source_file=Path("updated.bib"),
                )
            ]

            repo = Mock(spec=Repository)
            repo.load_entries_from_file.return_value = new_entries

            builder = IndexBuilder(db, repo)

            # Update specific file
            builder.update_index([Path("updated.bib")])

            # Should have both entries
            stats = db.get_statistics()
            assert stats["total_entries"] == 2

    def test_check_fts_consistency(self):
        """Test FTS consistency checking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            repo = Mock(spec=Repository)
            repo.get_all_entries.return_value = []

            builder = IndexBuilder(db, repo)

            # Empty database should be consistent
            assert builder.check_fts_consistency() is True

    def test_rebuild_fts_index(self):
        """Test rebuilding FTS index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            repo = Mock(spec=Repository)
            builder = IndexBuilder(db, repo)

            # Should not raise an error
            builder.rebuild_fts_index()


class TestUtilityFunctions:
    """Test utility functions."""

    def test_get_default_db_path(self):
        """Test default database path generation."""
        path = get_default_db_path()

        assert isinstance(path, Path)
        assert path.name == "bibliography.db"
        assert "bibmgr" in str(path)

    @patch.dict("os.environ", {"XDG_CACHE_HOME": "/custom/cache"})
    def test_get_default_db_path_with_xdg(self):
        """Test default path with XDG_CACHE_HOME set."""
        path = get_default_db_path()

        assert str(path).startswith("/custom/cache")
        assert path.name == "bibliography.db"

    def test_create_index_builder(self):
        """Test creating index builder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Mock(spec=Repository)
            db_path = Path(tmpdir) / "test.db"

            builder = create_index_builder(repo, db_path)

            assert isinstance(builder, IndexBuilder)
            assert builder.repository is repo

    def test_create_index_builder_default_path(self):
        """Test creating index builder with default path."""
        repo = Mock(spec=Repository)

        builder = create_index_builder(repo, None)

        assert isinstance(builder, IndexBuilder)
        assert builder.repository is repo


@pytest.fixture
def sample_repository():
    """Create a mock repository with sample data."""
    repo = Mock(spec=Repository)

    entries = [
        BibEntry(
            key="feynman1965qed",
            entry_type="article",
            fields={
                "title": "Quantum Electrodynamics",
                "author": "Richard P. Feynman",
                "journal": "Physical Review",
                "year": "1965",
            },
            source_file=Path("physics.bib"),
        ),
        BibEntry(
            key="einstein1905relativity",
            entry_type="article",
            fields={
                "title": "On the Electrodynamics of Moving Bodies",
                "author": "Albert Einstein",
                "journal": "Annalen der Physik",
                "year": "1905",
            },
            source_file=Path("physics.bib"),
        ),
    ]

    repo.get_all_entries.return_value = entries
    repo.load_entries_from_file.return_value = entries[:1]  # Just first entry

    return repo


class TestIndexBuilderIntegration:
    """Integration tests for IndexBuilder."""

    def test_full_index_workflow(self, sample_repository: Repository) -> None:
        """Test complete indexing workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            builder = IndexBuilder(db, sample_repository)

            # Build initial index
            builder.build_index(show_progress=False)

            # Verify indexing worked
            stats = db.get_statistics()
            assert stats["total_entries"] == 2
            assert stats["fts_entries"] == 2

            # Check we can search indexed entries
            results = db.search_fts("quantum")
            assert len(results) == 1
            assert results[0][0].key == "feynman1965qed"

            # Check status
            status = builder.get_index_status()
            assert status["up_to_date"] is True
            assert status["db_entries"] == 2
            assert status["repo_entries"] == 2

    def test_batch_processing_performance(self):
        """Test batch processing with many entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Create many entries to test batching
            entries = []
            for i in range(2500):  # More than default batch size of 1000
                entry = BibEntry(
                    key=f"test{i:04d}",
                    entry_type="article",
                    fields={
                        "title": f"Test Article {i}",
                        "author": f"Author {i}",
                        "year": "2023",
                    },
                    source_file=Path("test.bib"),
                )
                entries.append(entry)

            repo = Mock(spec=Repository)
            repo.get_all_entries.return_value = entries

            builder = IndexBuilder(db, repo)

            # Build index (should use batching)
            import time

            start_time = time.time()
            builder.build_index(show_progress=False)
            elapsed = time.time() - start_time

            # Verify all entries were indexed
            stats = db.get_statistics()
            assert stats["total_entries"] == 2500
            assert stats["fts_entries"] == 2500

            # Performance should be reasonable (under 5 seconds for 2500 entries)
            assert elapsed < 5.0
