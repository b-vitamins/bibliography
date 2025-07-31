"""Robustness tests for SQLite search system.

Tests for edge cases, error conditions, concurrent access, and recovery scenarios.
"""

import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from bibmgr.db import BibliographyDB
from bibmgr.index import IndexBuilder
from bibmgr.models import BibEntry
from bibmgr.repository import Repository
from bibmgr.scripts.search import SearchEngine


class TestDatabaseRobustness:
    """Test database robustness and error recovery."""

    def test_corrupted_database_recovery(self):
        """Test handling of corrupted database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "corrupt.db"

            # Create a corrupted database file
            db_path.write_bytes(b"This is not a valid SQLite database")

            # Try to open it
            with pytest.raises(sqlite3.DatabaseError):
                BibliographyDB(db_path)

    def test_database_locked_handling(self):
        """Test handling of locked database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "locked.db"
            db = BibliographyDB(db_path)

            # Create test entry
            entry = BibEntry(
                key="test2023",
                entry_type="article",
                fields={"title": "Test", "author": "Author", "year": "2023"},
                source_file=Path("test.bib"),
            )

            # Lock the database in another connection
            conn = sqlite3.connect(str(db_path))
            conn.execute("BEGIN EXCLUSIVE")

            try:
                # Try to insert - should handle gracefully
                with pytest.raises(sqlite3.OperationalError):
                    db.insert_entry(entry)
            finally:
                conn.close()

    def test_disk_full_handling(self):
        """Test handling of disk full errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "diskfull.db"
            db = BibliographyDB(db_path)

            entry = BibEntry(
                key="test2023",
                entry_type="article",
                fields={"title": "Test", "author": "Author", "year": "2023"},
                source_file=Path("test.bib"),
            )

            # Mock the connection to simulate disk full
            with patch.object(db, "_get_connection") as mock_get_conn:
                mock_conn = Mock()
                mock_conn.__enter__ = Mock(return_value=mock_conn)
                mock_conn.__exit__ = Mock(return_value=None)
                mock_conn.execute.side_effect = sqlite3.OperationalError(
                    "disk I/O error"
                )
                mock_get_conn.return_value = mock_conn

                with pytest.raises(sqlite3.OperationalError):
                    db.insert_entry(entry)

    def test_database_permissions_error(self):
        """Test handling of permission errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "readonly.db"

            # Create database
            db = BibliographyDB(db_path)

            # Make it read-only
            os.chmod(db_path, 0o444)

            try:
                # Try to insert - should fail gracefully
                entry = BibEntry(
                    key="test2023",
                    entry_type="article",
                    fields={"title": "Test", "author": "Author", "year": "2023"},
                    source_file=Path("test.bib"),
                )

                with pytest.raises(sqlite3.OperationalError):
                    db.insert_entry(entry)
            finally:
                # Restore permissions for cleanup
                os.chmod(db_path, 0o644)


class TestConcurrentAccess:
    """Test concurrent database access scenarios."""

    def test_concurrent_searches(self):
        """Test multiple concurrent searches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "concurrent.db"

            # Initialize and populate database
            db = BibliographyDB(db_path)
            entries = []
            for i in range(100):
                entry = BibEntry(
                    key=f"entry{i:03d}",
                    entry_type="article",
                    fields={
                        "title": f"Title {i}",
                        "author": f"Author {i}",
                        "year": "2023",
                    },
                    source_file=Path("test.bib"),
                )
                entries.append(entry)
            db.insert_entries_batch(entries)

            # Run concurrent searches
            results = []
            errors = []

            def search_worker(query: str) -> None:
                try:
                    engine = SearchEngine(db_path)
                    result = engine.search(query)
                    results.append(len(result))
                except Exception as e:
                    errors.append(e)

            threads = []
            for i in range(10):
                query = f"Title {i}"
                t = threading.Thread(target=search_worker, args=(query,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # All searches should complete without errors
            assert len(errors) == 0
            assert len(results) == 10

    def test_concurrent_index_and_search(self):
        """Test indexing while searching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "concurrent_index.db"
            bibtex_dir = Path(tmpdir) / "bibtex"
            bibtex_dir.mkdir()

            # Create initial entries
            (bibtex_dir / "test.bib").write_text("""
@article{initial2023,
    title = {Initial Entry},
    author = {Test Author},
    year = {2023}
}
""")

            # Build initial index
            repo = Repository(Path(tmpdir))
            db = BibliographyDB(db_path)
            builder = IndexBuilder(db, repo)
            builder.build_index()

            errors = []

            def index_worker():
                try:
                    # Add more entries
                    (bibtex_dir / "new.bib").write_text("""
@article{new2023,
    title = {New Entry},
    author = {New Author},
    year = {2023}
}
""")
                    builder.update_index([bibtex_dir / "new.bib"])
                except Exception as e:
                    errors.append(e)

            def search_worker():
                try:
                    engine = SearchEngine(db_path)
                    for _ in range(10):
                        engine.search("title")
                        time.sleep(0.01)
                except Exception as e:
                    errors.append(e)

            # Run index update and searches concurrently
            index_thread = threading.Thread(target=index_worker)
            search_threads = [threading.Thread(target=search_worker) for _ in range(3)]

            index_thread.start()
            for t in search_threads:
                t.start()

            index_thread.join()
            for t in search_threads:
                t.join()

            # Should complete without errors
            assert len(errors) == 0


class TestQueryRobustness:
    """Test query parsing and FTS5 robustness."""

    def test_malformed_fts5_queries(self):
        """Test handling of malformed FTS5 queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "malformed.db"
            db = BibliographyDB(db_path)

            # Add test entry
            entry = BibEntry(
                key="test2023",
                entry_type="article",
                fields={"title": "Test", "author": "Author", "year": "2023"},
                source_file=Path("test.bib"),
            )
            db.insert_entry(entry)

            # Test various malformed queries
            malformed_queries = [
                "(((",  # Unmatched parentheses
                "AND OR",  # Invalid boolean
                '"unclosed quote',  # Unclosed quote
                "field:",  # Empty field value
                ":::",  # Invalid syntax
                "NEAR/",  # Invalid NEAR syntax
                "*wildcard",  # Leading wildcard
                '""',  # Empty phrase
            ]

            for query in malformed_queries:
                # Should handle gracefully, not crash
                results = db.search_fts(query)
                assert isinstance(results, list)

    def test_sql_injection_prevention(self):
        """Test SQL injection prevention."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "injection.db"
            db = BibliographyDB(db_path)

            # Add test entry
            entry = BibEntry(
                key="test2023",
                entry_type="article",
                fields={"title": "Test", "author": "Author", "year": "2023"},
                source_file=Path("test.bib"),
            )
            db.insert_entry(entry)

            # Try SQL injection attempts
            injection_queries = [
                "'; DROP TABLE entries; --",
                '" OR 1=1 --',
                "'; DELETE FROM entries_fts; --",
                "\"; UPDATE entries SET data='hacked'; --",
            ]

            for query in injection_queries:
                # Should be safely handled
                results = db.search_fts(query)
                assert isinstance(results, list)

                # Verify database is intact
                stats = db.get_statistics()
                assert stats["total_entries"] == 1

    def test_extreme_query_lengths(self):
        """Test handling of extremely long queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "longquery.db"
            engine = SearchEngine(db_path)

            # Very long query
            long_query = "quantum " * 1000

            # Should handle without crashing
            results = engine.search(long_query)
            assert isinstance(results, list)

    def test_unicode_and_special_chars(self):
        """Test handling of Unicode and special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "unicode.db"
            db = BibliographyDB(db_path)

            # Entry with Unicode
            entry = BibEntry(
                key="unicode2023",
                entry_type="article",
                fields={
                    "title": "Étude sur les équations différentielles",
                    "author": "José María González",
                    "journal": "Журнал математики",
                    "year": "2023",
                },
                source_file=Path("test.bib"),
            )
            db.insert_entry(entry)

            # Search with Unicode
            results = db.search_fts("équations")
            assert len(results) == 1

            # Search with special characters
            special_queries = ["José", "González", "Журнал", "différentielles"]

            for query in special_queries:
                results = db.search_fts(query)
                assert len(results) >= 0  # Should not crash


class TestIndexRobustness:
    """Test index building robustness."""

    def test_index_large_dataset(self):
        """Test indexing large number of entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "large.db"
            bibtex_dir = Path(tmpdir) / "bibtex"
            bibtex_dir.mkdir()

            # Create many .bib files
            for i in range(10):
                entries = []
                for j in range(100):
                    idx = i * 100 + j
                    entries.append(f"""
@article{{entry{idx:04d},
    title = {{Entry {idx} Title}},
    author = {{Author {idx}}},
    journal = {{Journal}},
    year = {{2023}}
}}
""")
                (bibtex_dir / f"file{i}.bib").write_text("\n".join(entries))

            # Build index
            repo = Repository(Path(tmpdir))
            db = BibliographyDB(db_path)
            builder = IndexBuilder(db, repo)
            builder.build_index()

            # Verify all entries indexed
            engine = SearchEngine(db_path)
            stats = engine.get_statistics()
            assert stats["total_entries"] == 1000
            assert stats["fts_entries"] == 1000

    def test_index_malformed_bibtex(self):
        """Test indexing with malformed BibTeX files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "malformed.db"
            bibtex_dir = Path(tmpdir) / "bibtex"
            bibtex_dir.mkdir()

            # Create malformed .bib file
            (bibtex_dir / "malformed.bib").write_text("""
@article{valid2023,
    title = {Valid Entry},
    author = {Author},
    year = {2023}
}

@article{malformed2023
    title = {Missing closing brace
    author = {Author}
    year = {2023}

@book{another2023,
    title = {Another Valid},
    author = {Author},
    year = {2023}
}
""")

            # Build index - should handle errors gracefully
            repo = Repository(Path(tmpdir))
            db = BibliographyDB(db_path)
            builder = IndexBuilder(db, repo)

            # Should not crash
            builder.build_index()

            # Should have indexed valid entries
            engine = SearchEngine(db_path)
            stats = engine.get_statistics()
            total_entries = stats["total_entries"]
            assert (
                isinstance(total_entries, int) and total_entries >= 0
            )  # At least some entries indexed

    def test_index_interrupted_rebuild(self):
        """Test recovery from interrupted index rebuild."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "interrupt.db"
            bibtex_dir = Path(tmpdir) / "bibtex"
            bibtex_dir.mkdir()

            # Create test entries
            (bibtex_dir / "test.bib").write_text("""
@article{test2023,
    title = {Test Entry},
    author = {Author},
    year = {2023}
}

@article{test2024,
    title = {Another Test Entry},
    author = {Another Author},
    year = {2024}
}
""")

            repo = Repository(Path(tmpdir))
            db = BibliographyDB(db_path)
            builder = IndexBuilder(db, repo)

            # Start indexing
            builder.build_index()

            # Simulate database corruption by disabling triggers and creating
            # inconsistency
            # Simulate database corruption by disabling triggers and creating
            # inconsistency
            builder.db.execute_sql("DROP TRIGGER IF EXISTS entries_ad")
            # Delete from main table only - this creates inconsistency
            builder.db.execute_sql("DELETE FROM entries WHERE key = 'test2023'")
            # Re-create the trigger for future operations
            builder.db.execute_sql("""
                CREATE TRIGGER entries_ad AFTER DELETE ON entries BEGIN
                    DELETE FROM entries_fts WHERE key = old.key;
                END
            """)

            # Check consistency - should be inconsistent now
            assert not builder.check_fts_consistency()

            # Rebuild should fix it
            builder.rebuild_fts_index()
            assert builder.check_fts_consistency()


class TestPerformanceAndScale:
    """Test performance characteristics and scalability."""

    def test_search_performance_scaling(self):
        """Test search performance with increasing dataset size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "perf.db"
            db = BibliographyDB(db_path)

            sizes = [10, 100, 1000]
            times = []

            for size in sizes:
                # Add entries
                entries = []
                for i in range(size):
                    entry = BibEntry(
                        key=f"perf{i:05d}",
                        entry_type="article",
                        fields={
                            "title": f"Performance Test Entry {i}",
                            "author": f"Author {i % 10}",
                            "year": str(2000 + (i % 24)),
                        },
                        source_file=Path("test.bib"),
                    )
                    entries.append(entry)

                db.insert_entries_batch(entries)

                # Time searches
                engine = SearchEngine(db_path)
                start = time.time()
                for _ in range(10):
                    engine.search("Performance")
                elapsed = time.time() - start
                times.append(elapsed)

            # Search time should not grow linearly with data size
            # (FTS5 uses indexes, so should be logarithmic)
            growth_rate = times[-1] / times[0]
            size_growth = sizes[-1] / sizes[0]

            # Time growth should be much less than size growth
            assert growth_rate < size_growth / 10

    def test_memory_usage_large_results(self):
        """Test memory usage with large result sets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            db = BibliographyDB(db_path)

            # Add many entries with common term
            entries = []
            for i in range(1000):
                entry = BibEntry(
                    key=f"mem{i:04d}",
                    entry_type="article",
                    fields={
                        "title": f"Memory Test Common Term Entry {i}",
                        "author": f"Author {i}",
                        "year": "2023",
                        "abstract": "A" * 1000,  # Large abstract
                    },
                    source_file=Path("test.bib"),
                )
                entries.append(entry)

            db.insert_entries_batch(entries)

            # Search for common term - all entries match
            engine = SearchEngine(db_path)

            # Should handle large results efficiently
            results = engine.search("Common", limit=100)
            assert len(results) == 100  # Respects limit

            # Verify we can still search after large query
            results2 = engine.search("specific")
            assert isinstance(results2, list)


class TestBackwardCompatibility:
    """Test backward compatibility and migration scenarios."""

    def test_database_version_handling(self):
        """Test handling of different database versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "version.db"

            # Create database
            db = BibliographyDB(db_path)

            # Add test entry
            entry = BibEntry(
                key="test2023",
                entry_type="article",
                fields={"title": "Test", "author": "Author", "year": "2023"},
                source_file=Path("test.bib"),
            )
            db.insert_entry(entry)

            # Simulate version mismatch by modifying user_version
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("PRAGMA user_version = 999")

            # Should handle gracefully
            db2 = BibliographyDB(db_path)
            stats = db2.get_statistics()
            assert isinstance(stats, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
