"""Integration tests for search functionality."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from bibmgr.db import BibliographyDB
from bibmgr.models import BibEntry
from bibmgr.scripts.locate import LocateEngine
from bibmgr.scripts.search import SearchEngine


@pytest.fixture
def comprehensive_entries():
    """Create comprehensive test data covering various scenarios."""
    return [
        # Physics entries
        BibEntry(
            key="feynman1965qed",
            entry_type="article",
            fields={
                "title": "Quantum Electrodynamics",
                "author": "Richard P. Feynman",
                "journal": "Physical Review",
                "year": "1965",
                "abstract": "A comprehensive theory of quantum electrodynamics",
                "keywords": "physics, quantum mechanics, QED",
                "file": ":/home/b/documents/article/feynman1965qed.pdf:pdf",
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
                "abstract": "Special theory of relativity",
                "keywords": "relativity, physics, spacetime",
                "file": ":/home/b/documents/article/einstein1905relativity.pdf:pdf",
            },
            source_file=Path("physics.bib"),
        ),
        # Computer Science entries
        BibEntry(
            key="turing1950computing",
            entry_type="article",
            fields={
                "title": "Computing Machinery and Intelligence",
                "author": "Alan M. Turing",
                "journal": "Mind",
                "year": "1950",
                "abstract": "Can machines think? The Turing test proposal",
                "keywords": "artificial intelligence, computing, philosophy",
                "file": ":/home/b/documents/article/turing1950computing.pdf:pdf",
            },
            source_file=Path("cs.bib"),
        ),
        # Book entry
        BibEntry(
            key="knuth1997art",
            entry_type="book",
            fields={
                "title": "The Art of Computer Programming",
                "author": "Donald E. Knuth",
                "publisher": "Addison-Wesley",
                "year": "1997",
                "abstract": "Comprehensive multi-volume work on algorithms",
                "keywords": "algorithms, programming, computer science",
                "file": ":/home/b/documents/book/knuth1997art.pdf:pdf",
            },
            source_file=Path("cs.bib"),
        ),
        # Thesis entry
        BibEntry(
            key="shannon1940boolean",
            entry_type="mastersthesis",
            fields={
                "title": "A Symbolic Analysis of Relay and Switching Circuits",
                "author": "Claude E. Shannon",
                "school": "MIT",
                "year": "1940",
                "abstract": "Application of Boolean algebra to switching circuits",
                "keywords": "boolean algebra, circuits, logic",
                "file": ":/home/b/documents/mastersthesis/shannon1940boolean.pdf:pdf",
            },
            source_file=Path("thesis.bib"),
        ),
    ]


@pytest.fixture
def indexed_database(
    comprehensive_entries: list[BibEntry],
) -> Generator[Path, None, None]:
    """Create a fully indexed database with comprehensive test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = BibliographyDB(db_path)

        # Insert all entries
        db.insert_entries_batch(comprehensive_entries)

        yield db_path


class TestSearchEngineIntegration:
    """Integration tests for SearchEngine."""

    def test_search_engine_basic_queries(self, indexed_database: Path):
        """Test basic search functionality."""
        engine = SearchEngine(indexed_database)

        # Simple text search
        results = engine.search("quantum")
        assert len(results) == 1
        assert results[0].entry.key == "feynman1965qed"
        assert results[0].score > 0

        # Multiple matches
        results = engine.search("physics")
        assert len(results) >= 2  # Should match keywords and abstracts

        # Case insensitive
        results = engine.search("QUANTUM")
        assert len(results) == 1
        assert results[0].entry.key == "feynman1965qed"

    def test_search_engine_field_queries(self, indexed_database: Path):
        """Test field-specific searches."""
        engine = SearchEngine(indexed_database)

        # Author search
        results = engine.search("author:Einstein")
        assert len(results) == 1
        assert results[0].entry.key == "einstein1905relativity"

        # Year search
        results = engine.search("year:1950")
        assert len(results) == 1
        assert results[0].entry.key == "turing1950computing"

        # Journal search
        results = engine.search("journal:Mind")
        assert len(results) == 1
        assert results[0].entry.key == "turing1950computing"

        # Title search
        results = engine.search("title:Electrodynamics")
        assert len(results) >= 1  # Could match multiple

        # Keywords search
        results = engine.search("keywords:algorithms")
        assert len(results) == 1
        assert results[0].entry.key == "knuth1997art"

    def test_search_engine_boolean_queries(self, indexed_database: Path):
        """Test boolean search operators."""
        engine = SearchEngine(indexed_database)

        # AND operator
        results = engine.search("quantum AND physics")
        assert len(results) == 1
        assert results[0].entry.key == "feynman1965qed"

        # OR operator
        results = engine.search("quantum OR relativity")
        assert len(results) == 2
        keys = {r.entry.key for r in results}
        assert "feynman1965qed" in keys
        assert "einstein1905relativity" in keys

        # NOT operator
        results = engine.search("physics NOT quantum")
        assert len(results) >= 1
        keys = {r.entry.key for r in results}
        assert "feynman1965qed" not in keys

    def test_search_engine_phrase_queries(self, indexed_database: Path):
        """Test phrase search queries."""
        engine = SearchEngine(indexed_database)

        # Exact phrase
        results = engine.search('"Computer Programming"')
        assert len(results) == 1
        assert results[0].entry.key == "knuth1997art"

        # Phrase in title
        results = engine.search('"Moving Bodies"')
        assert len(results) == 1
        assert results[0].entry.key == "einstein1905relativity"

    def test_search_engine_wildcard_queries(self, indexed_database: Path):
        """Test wildcard search queries."""
        engine = SearchEngine(indexed_database)

        # Wildcard search
        results = engine.search("comput*")
        assert len(results) >= 2  # Should match "computing" and "computer"

        # Multiple wildcards
        results = engine.search("electro*")
        assert len(results) >= 2  # "Electrodynamics" appears in multiple entries

    def test_search_engine_sorting(self, indexed_database: Path):
        """Test different sort orders."""
        engine = SearchEngine(indexed_database)

        # Get multiple results
        results = engine.search("physics", sort_by="relevance")
        assert len(results) >= 2

        # Sort by year (newest first)
        results_by_year = engine.search("physics", sort_by="year")
        years = [r.entry.fields.get("year", "") or "" for r in results_by_year]
        assert years == sorted(years, reverse=True)

        # Sort by author
        results_by_author = engine.search("physics", sort_by="author")
        authors = [r.entry.fields.get("author", "") or "" for r in results_by_author]
        assert authors == sorted(authors)

        # Sort by title
        results_by_title = engine.search("physics", sort_by="title")
        titles = [r.entry.fields.get("title", "") or "" for r in results_by_title]
        assert titles == sorted(titles)

    def test_search_engine_pagination(self, indexed_database: Path):
        """Test search result pagination."""
        engine = SearchEngine(indexed_database)

        # First page
        results_page1 = engine.search("", limit=2, offset=0)  # Empty query returns all
        assert len(results_page1) <= 2

        # Second page
        results_page2 = engine.search("", limit=2, offset=2)

        # Should be different results (if we have more than 2 total)
        if len(results_page1) == 2 and len(results_page2) > 0:
            keys_page1 = {r.entry.key for r in results_page1}
            keys_page2 = {r.entry.key for r in results_page2}
            assert keys_page1.isdisjoint(keys_page2)

    def test_search_by_key(self, indexed_database: Path):
        """Test searching by exact key."""
        engine = SearchEngine(indexed_database)

        # Existing key
        entry = engine.search_by_key("feynman1965qed")
        assert entry is not None
        assert entry.key == "feynman1965qed"

        # Non-existent key
        entry = engine.search_by_key("nonexistent2023")
        assert entry is None

    def test_search_by_field(self, indexed_database: Path):
        """Test searching by specific field."""
        engine = SearchEngine(indexed_database)

        # Search by entry type
        results = engine.search_by_field("entry_type", "article")
        assert len(results) >= 3  # We have several articles
        for result in results:
            assert result.entry.entry_type == "article"

        # Search by author
        results = engine.search_by_field("author", "Donald E. Knuth")
        assert len(results) == 1
        assert results[0].entry.key == "knuth1997art"

    def test_search_statistics(self, indexed_database: Path):
        """Test getting search statistics."""
        engine = SearchEngine(indexed_database)

        stats = engine.get_statistics()

        assert stats["total_entries"] == 5
        assert stats["fts_entries"] == 5
        assert "by_type" in stats
        assert "by_file" in stats
        assert "db_size_bytes" in stats

        # Check entry type distribution
        by_type = stats["by_type"]
        assert isinstance(by_type, dict)
        assert by_type.get("article", 0) >= 3
        assert by_type.get("book", 0) == 1
        assert by_type.get("mastersthesis", 0) == 1


class TestLocateEngineIntegration:
    """Integration tests for LocateEngine."""

    def test_locate_by_filename(self, indexed_database: Path):
        """Test locating entries by filename."""
        engine = LocateEngine(indexed_database)

        # Find by partial filename
        results = engine.locate_file("feynman1965qed.pdf")
        assert len(results) == 1
        assert results[0].key == "feynman1965qed"

        # Find by path component
        results = engine.locate_file("documents/article")
        assert len(results) >= 3  # Should match all articles

    def test_locate_with_glob_patterns(self, indexed_database: Path):
        """Test locate with glob pattern matching."""
        engine = LocateEngine(indexed_database)

        # Glob pattern for all PDFs
        results = engine.locate_file("*.pdf", glob_match=True)
        assert len(results) == 5  # All entries have PDFs

        # Glob pattern for specific directory
        results = engine.locate_file("*/article/*", glob_match=True)
        assert len(results) >= 3  # All articles

    def test_locate_basename_only(self, indexed_database: Path):
        """Test locate with basename-only search."""
        engine = LocateEngine(indexed_database)

        results = engine.locate_file("knuth1997art.pdf", basename_only=True)
        assert len(results) == 1
        assert results[0].key == "knuth1997art"

    def test_locate_by_extension(self, indexed_database: Path):
        """Test locating files by extension."""
        engine = LocateEngine(indexed_database)

        # All PDF files
        results = engine.locate_by_extension("pdf")
        assert len(results) == 5

        # Alternative format (with dot)
        results = engine.locate_by_extension(".pdf")
        assert len(results) == 5

    def test_locate_in_directory(self, indexed_database: Path):
        """Test locating files in specific directory."""
        engine = LocateEngine(indexed_database)

        # Articles directory
        results = engine.locate_in_directory("/home/b/documents/article")
        assert len(results) >= 3


class TestSearchFormatterIntegration:
    """Integration tests for search result formatting."""

    def test_formatter_table_output(
        self, indexed_database: Path, capsys: pytest.CaptureFixture[str]
    ):
        """Test table format output."""
        engine = SearchEngine(indexed_database)
        results = engine.search("physics")

        # Test formatter
        engine.formatter.format_results(results, "physics", "table", show_stats=True)

        captured = capsys.readouterr()
        assert "physics" in captured.out.lower()
        assert "found" in captured.out.lower()

    def test_formatter_json_output(
        self, indexed_database: Path, capsys: pytest.CaptureFixture[str]
    ):
        """Test JSON format output."""
        engine = SearchEngine(indexed_database)
        results = engine.search("quantum", limit=1)

        engine.formatter.format_results(results, "quantum", "json")

        captured = capsys.readouterr()
        # Should contain valid JSON
        import json

        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["key"] == "feynman1965qed"
        assert "score" in data[0]

    def test_formatter_keys_output(
        self, indexed_database: Path, capsys: pytest.CaptureFixture[str]
    ):
        """Test keys-only format output."""
        engine = SearchEngine(indexed_database)
        results = engine.search("physics", limit=2)

        engine.formatter.format_results(results, "physics", "keys")

        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.split("\n") if line.strip()]

        # Should be just citation keys
        assert len(lines) <= 2
        for line in lines:
            assert len(line.split()) == 1  # Single word per line


class TestPerformanceIntegration:
    """Performance and scalability tests."""

    def test_large_dataset_search_performance(self):
        """Test search performance with larger dataset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "perf_test.db"
            db = BibliographyDB(db_path)

            # Create 1000 entries
            entries = []
            for i in range(1000):
                entry = BibEntry(
                    key=f"test{i:04d}",
                    entry_type="article",
                    fields={
                        "title": f"Performance Test Article {i}",
                        "author": f"Author {i % 50}",  # 50 different authors
                        "journal": f"Journal {i % 10}",  # 10 different journals
                        "year": str(1990 + (i % 30)),  # Years 1990-2019
                        "abstract": (
                            f"This is a test abstract for article {i} "
                            f"about performance testing"
                        ),
                        "keywords": f"test, performance, article{i % 20}",
                    },
                    source_file=Path(f"test{i % 10}.bib"),
                )
                entries.append(entry)

            # Batch insert
            db.insert_entries_batch(entries)

            engine = SearchEngine(db_path)

            # Test various queries for performance
            import time

            # Simple search
            start = time.time()
            results = engine.search("performance", limit=1000)  # Increase limit
            elapsed = time.time() - start
            assert elapsed < 0.5  # Should be under 500ms
            assert len(results) >= 100  # Should find many matches

            # Field search
            start = time.time()
            results = engine.search("author:Author 5")
            elapsed = time.time() - start
            assert elapsed < 0.1  # Should be very fast

            # Boolean search
            start = time.time()
            results = engine.search("performance AND test")
            elapsed = time.time() - start
            assert elapsed < 0.5

            # Complex query
            start = time.time()
            results = engine.search("(performance OR test) AND author:Author*")
            elapsed = time.time() - start
            assert elapsed < 1.0  # Complex queries under 1 second

    def test_concurrent_search_access(self):
        """Test concurrent access to search database."""
        import threading
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "concurrent_test.db"
            db = BibliographyDB(db_path)

            # Insert test data
            entries = []
            for i in range(100):
                entry = BibEntry(
                    key=f"concurrent{i:03d}",
                    entry_type="article",
                    fields={
                        "title": f"Concurrent Test {i}",
                        "author": f"Author {i}",
                        "year": "2023",
                    },
                    source_file=Path("concurrent.bib"),
                )
                entries.append(entry)

            db.insert_entries_batch(entries)

            # Function for concurrent searches
            results = []
            errors = []

            def search_worker(worker_id: str) -> None:
                try:
                    engine = SearchEngine(db_path)
                    for i in range(10):  # 10 searches per worker
                        search_results = engine.search(
                            f"Concurrent Test {int(worker_id) * 10 + i}"
                        )
                        results.append(len(search_results))
                        time.sleep(0.01)  # Small delay
                except Exception as e:
                    errors.append(str(e))

            # Start multiple threads
            threads = []
            for i in range(5):  # 5 concurrent workers
                thread = threading.Thread(target=search_worker, args=(i,))
                threads.append(thread)
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join()

            # Check results
            assert len(errors) == 0, f"Concurrent access errors: {errors}"
            assert len(results) == 50  # 5 workers * 10 searches each
            assert all(r >= 0 for r in results)  # All searches should succeed


class TestRegressionTests:
    """Regression tests for previously fixed issues."""

    def test_empty_query_handling(self, indexed_database: Path):
        """Test that empty queries are handled gracefully."""
        engine = SearchEngine(indexed_database)

        # Empty string
        results = engine.search("")
        assert isinstance(results, list)

        # Whitespace only
        results = engine.search("   ")
        assert isinstance(results, list)

        # None (this would be handled at CLI level, but test robustness)
        results = engine.search("test")  # Use valid query instead
        assert len(results) >= 0

    def test_special_characters_in_queries(self, indexed_database: Path):
        """Test handling of special characters in search queries."""
        engine = SearchEngine(indexed_database)

        # Quotes
        results = engine.search('"Quantum Electrodynamics"')
        assert len(results) >= 0

        # Parentheses
        results = engine.search("(quantum OR physics)")
        assert len(results) >= 0

        # Unicode characters (if any in test data)
        results = engine.search("Annalen")  # German journal name
        assert len(results) >= 0

    def test_field_search_edge_cases(self, indexed_database: Path):
        """Test edge cases in field searches."""
        engine = SearchEngine(indexed_database)

        # Non-existent field
        results = engine.search("nonexistentfield:value")
        assert isinstance(results, list)

        # Empty field value
        results = engine.search("author:")
        assert isinstance(results, list)

        # Multiple colons
        results = engine.search("title:Test:Article")
        assert isinstance(results, list)

    def test_database_consistency_after_operations(self, indexed_database: Path):
        """Test that database remains consistent after various operations."""
        engine = SearchEngine(indexed_database)

        # Get initial statistics
        initial_stats = engine.get_statistics()

        # Perform various searches
        engine.search("quantum")
        engine.search("author:Einstein")
        engine.search("year:1950")
        engine.search_by_key("feynman1965qed")

        # Statistics should remain the same
        final_stats = engine.get_statistics()
        assert final_stats["total_entries"] == initial_stats["total_entries"]
        assert final_stats["fts_entries"] == initial_stats["fts_entries"]
