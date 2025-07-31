"""Tests for SQLite-based search functionality."""

import tempfile
from pathlib import Path

import pytest

from bibmgr.db import BibliographyDB
from bibmgr.models import BibEntry
from bibmgr.query import QueryBuilder, parse_query
from bibmgr.scripts.search import SearchEngine


class TestSQLiteDB:
    """Test SQLite database functionality."""

    def test_db_initialization(self):
        """Test database initialization with FTS5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Check that database file was created
            assert db_path.exists()

            # Check that we can get statistics
            stats = db.get_statistics()
            assert stats["total_entries"] == 0
            assert stats["fts_entries"] == 0

    def test_insert_and_search(self):
        """Test inserting entries and searching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Create test entry
            entry = BibEntry(
                key="test2023example",
                entry_type="article",
                fields={
                    "title": "Test Article About Quantum Computing",
                    "author": "John Smith",
                    "journal": "Test Journal",
                    "year": "2023",
                },
                source_file=Path("test.bib"),
            )

            # Insert entry
            db.insert_entry(entry)

            # Search for it
            results = db.search_fts("quantum")
            assert len(results) == 1
            assert results[0][0].key == "test2023example"

            # Field-specific search
            results = db.search_fts("{author}:Smith")
            assert len(results) == 1
            assert results[0][0].key == "test2023example"

    def test_batch_insert(self):
        """Test batch insertion of entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Create multiple test entries
            entries = []
            for i in range(5):
                entry = BibEntry(
                    key=f"test202{i}example",
                    entry_type="article",
                    fields={
                        "title": f"Test Article {i}",
                        "author": f"Author {i}",
                        "year": "2023",
                    },
                    source_file=Path("test.bib"),
                )
                entries.append(entry)

            # Batch insert
            db.insert_entries_batch(entries)

            # Verify all were inserted
            stats = db.get_statistics()
            assert stats["total_entries"] == 5
            assert stats["fts_entries"] == 5


class TestQueryBuilder:
    """Test FTS5 query building."""

    def test_simple_query(self):
        """Test simple query building."""
        builder = QueryBuilder()

        query = builder.build_query("quantum computing")
        assert query == "quantum computing"
        assert len(builder.get_warnings()) == 0

    def test_field_query(self):
        """Test field-specific query building."""
        builder = QueryBuilder()

        query = builder.build_query("author:smith")
        assert query == "{author}:smith"
        assert len(builder.get_warnings()) == 0

    def test_boolean_query(self):
        """Test boolean query building."""
        builder = QueryBuilder()

        query = builder.build_query("quantum AND computing")
        assert query == "quantum AND computing"
        assert len(builder.get_warnings()) == 0

    def test_phrase_query(self):
        """Test phrase query building."""
        builder = QueryBuilder()

        query = builder.build_query('"path integral"')
        assert query == '"path integral"'
        assert len(builder.get_warnings()) == 0

    def test_wildcard_query(self):
        """Test wildcard query building."""
        builder = QueryBuilder()

        query = builder.build_query("quan*")
        assert query == "quan*"
        assert len(builder.get_warnings()) == 0

    def test_unknown_field_warning(self):
        """Test warning for unknown field."""
        builder = QueryBuilder()

        query = builder.build_query("unknown:value")
        assert query == "value"
        warnings = builder.get_warnings()
        assert len(warnings) == 1
        assert "Unknown field 'unknown'" in warnings[0]


class TestParseQuery:
    """Test query parsing function."""

    def test_parse_query(self):
        """Test parse_query function."""
        query, warnings = parse_query("author:feynman")
        assert query == "{author}:feynman"
        assert len(warnings) == 0

    def test_parse_query_with_warnings(self):
        """Test parse_query with warnings."""
        query, warnings = parse_query("badfield:test")
        assert query == "test"
        assert len(warnings) == 1


class TestSearchEngine:
    """Test search engine functionality."""

    def test_search_engine_initialization(self):
        """Test search engine can be initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = SearchEngine(db_path)

            # Should be able to get statistics
            stats = engine.get_statistics()
            assert "total_entries" in stats

    def test_empty_search(self):
        """Test searching empty database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = SearchEngine(db_path)

            results = engine.search("test query")
            assert len(results) == 0


@pytest.fixture
def sample_entries():
    """Create sample bibliography entries for testing."""
    return [
        BibEntry(
            key="feynman1965quantum",
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
            key="smith2020computing",
            entry_type="article",
            fields={
                "title": "Modern Computing Systems",
                "author": "John Smith",
                "journal": "Computing Today",
                "year": "2020",
            },
            source_file=Path("computing.bib"),
        ),
    ]


class TestIntegratedSearch:
    """Test integrated search functionality."""

    def test_full_search_workflow(self, sample_entries: list[BibEntry]):
        """Test complete search workflow with real entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BibliographyDB(db_path)

            # Insert sample entries
            db.insert_entries_batch(sample_entries)

            # Create search engine
            engine = SearchEngine(db_path)

            # Test different types of searches

            # Simple search
            results = engine.search("quantum")
            assert len(results) == 1
            assert results[0].entry.key == "feynman1965quantum"

            # Author search
            results = engine.search("author:feynman")
            assert len(results) == 1
            assert results[0].entry.key == "feynman1965quantum"

            # Year search
            results = engine.search("year:2020")
            assert len(results) == 1
            assert results[0].entry.key == "smith2020computing"

            # Boolean search
            results = engine.search("quantum OR computing")
            assert len(results) == 2
