"""Performance benchmarks for SQLite search system.

Measures and validates performance characteristics.
"""

import random
import string
import tempfile
import time
from pathlib import Path
from statistics import mean, stdev

import pytest

from bibmgr.db import BibliographyDB
from bibmgr.index import IndexBuilder
from bibmgr.models import BibEntry
from bibmgr.repository import Repository
from bibmgr.scripts.search import SearchEngine


def generate_random_text(
    words: int = 10, min_length: int = 3, max_length: int = 12
) -> str:
    """Generate random text for testing."""
    text = []
    for _ in range(words):
        length = random.randint(min_length, max_length)
        word = "".join(random.choices(string.ascii_lowercase, k=length))
        text.append(word)
    return " ".join(text)


def generate_test_entries(
    count: int, common_terms: list[str] | None = None, key_offset: int = 0
) -> list[BibEntry]:
    """Generate test bibliography entries."""
    entries = []
    authors = [f"Author {i}" for i in range(10)]
    journals = [f"Journal {i}" for i in range(5)]
    years = [str(y) for y in range(2000, 2024)]

    for i in range(count):
        # Mix of random and common terms
        title_parts = []
        if common_terms and random.random() < 0.3:
            title_parts.append(random.choice(common_terms))
        title_parts.append(generate_random_text(5))

        entry = BibEntry(
            key=f"entry{key_offset + i:06d}",
            entry_type=random.choice(["article", "book", "inproceedings"]),
            fields={
                "title": " ".join(title_parts),
                "author": random.choice(authors),
                "journal": random.choice(journals),
                "year": random.choice(years),
                "abstract": generate_random_text(50) if random.random() < 0.5 else None,
                "keywords": generate_random_text(3) if random.random() < 0.3 else None,
            },
            source_file=Path(f"test{i % 10}.bib"),
        )
        entries.append(entry)

    return entries


class TestSearchPerformance:
    """Benchmark search performance."""

    def test_insert_performance(self):
        """Benchmark entry insertion performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "insert_perf.db"
            db = BibliographyDB(db_path)

            # Test different batch sizes
            batch_sizes = [1, 10, 100, 1000]
            results = {}

            for batch_size in batch_sizes:
                entries = generate_test_entries(batch_size)

                start = time.time()
                if batch_size == 1:
                    db.insert_entry(entries[0])
                else:
                    db.insert_entries_batch(entries)
                elapsed = time.time() - start

                rate = batch_size / elapsed
                results[batch_size] = rate

                print(f"Batch size {batch_size}: {rate:.1f} entries/sec")

            # Batch insertion should be much faster per entry
            assert results[1000] > results[1] * 10

    def test_search_response_time(self):
        """Benchmark search response times."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "search_perf.db"
            db = BibliographyDB(db_path)

            # Add test data
            common_terms = ["quantum", "neural", "algorithm", "theory", "analysis"]
            entries = generate_test_entries(10000, common_terms)
            db.insert_entries_batch(entries)

            engine = SearchEngine(db_path)

            # Test different query types
            queries = {
                "single_term": "quantum",
                "phrase": '"neural network"',
                "boolean": "quantum AND computing",
                "wildcard": "algor*",
                "field": "author:Author",
                "complex": "(quantum OR neural) AND year:2023",
            }

            results = {}
            for query_type, query in queries.items():
                times = []
                for _ in range(10):
                    start = time.time()
                    engine.search(query)
                    elapsed = time.time() - start
                    times.append(elapsed * 1000)  # Convert to ms

                avg_time = mean(times)
                results[query_type] = avg_time
                print(f"{query_type}: {avg_time:.1f}ms (±{stdev(times):.1f}ms)")

            # All queries should complete in reasonable time
            for _query_type, avg_time in results.items():
                assert avg_time < 100  # Under 100ms

    def test_index_build_performance(self):
        """Benchmark index building performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "index_perf.db"
            bibtex_dir = Path(tmpdir) / "bibtex"
            bibtex_dir.mkdir()

            # Create test .bib files
            total_entries = 0
            for i in range(10):
                entries = []
                for j in range(500):
                    idx = i * 500 + j
                    entries.append(f"""
@article{{perf{idx:05d},
    title = {{Performance Test Entry {idx} with some keywords}},
    author = {{Author {idx % 100}}},
    journal = {{Journal of Testing}},
    year = {{{2000 + (idx % 24)}}},
    abstract = {{This is an abstract for entry {idx}. It contains various terms.}}
}}
""")
                    total_entries += 1

                (bibtex_dir / f"perf{i}.bib").write_text("\n".join(entries))

            repo = Repository(Path(tmpdir))
            db = BibliographyDB(db_path)
            builder = IndexBuilder(db, repo)

            # Time index building
            start = time.time()
            builder.build_index(show_progress=False)
            elapsed = time.time() - start

            rate = total_entries / elapsed
            print(
                f"Indexed {total_entries} entries in {elapsed:.2f}s "
                f"({rate:.1f} entries/sec)"
            )

            # Should maintain good performance
            assert rate > 100  # At least 100 entries/sec

    def test_concurrent_search_performance(self):
        """Benchmark concurrent search performance."""
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "concurrent_perf.db"
            db = BibliographyDB(db_path)

            # Add test data
            entries = generate_test_entries(5000)
            db.insert_entries_batch(entries)

            # Test concurrent searches
            num_threads = 10
            searches_per_thread = 20

            times = []

            def search_worker():
                engine = SearchEngine(db_path)
                thread_times = []
                for _ in range(searches_per_thread):
                    query = generate_random_text(2)
                    start = time.time()
                    engine.search(query)
                    elapsed = time.time() - start
                    thread_times.append(elapsed)
                times.extend(thread_times)

            # Run searches concurrently
            start = time.time()
            threads = []
            for _ in range(num_threads):
                t = threading.Thread(target=search_worker)
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            total_elapsed = time.time() - start
            total_searches = num_threads * searches_per_thread
            throughput = total_searches / total_elapsed

            print(f"Concurrent searches: {throughput:.1f} searches/sec")
            print(f"Average response: {mean(times) * 1000:.1f}ms")

            # Should maintain good throughput
            assert throughput > 50  # At least 50 searches/sec


class TestScalability:
    """Test system scalability."""

    def test_large_dataset_handling(self):
        """Test handling of large datasets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "large.db"
            db = BibliographyDB(db_path)

            # Add entries in batches
            batch_size = 1000
            num_batches = 10

            for i in range(num_batches):
                entries = generate_test_entries(batch_size, key_offset=i * batch_size)
                db.insert_entries_batch(entries)

                # Check that performance doesn't degrade
                start = time.time()
                stats = db.get_statistics()
                elapsed = time.time() - start

                assert elapsed < 0.1  # Stats should be fast
                assert stats["total_entries"] == (i + 1) * batch_size

    def test_result_set_pagination(self):
        """Test performance with large result sets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "pagination.db"
            db = BibliographyDB(db_path)

            # Add many entries with common term
            entries = []
            for i in range(5000):
                entry = BibEntry(
                    key=f"page{i:05d}",
                    entry_type="article",
                    fields={
                        "title": f"Common Term Entry {i}",
                        "author": f"Author {i % 100}",
                        "year": "2023",
                    },
                    source_file=Path("test.bib"),
                )
                entries.append(entry)

            db.insert_entries_batch(entries)
            engine = SearchEngine(db_path)

            # Test pagination performance
            page_times = []
            for offset in [0, 100, 1000, 2000]:
                start = time.time()
                results = engine.search("Common", limit=20, offset=offset)
                elapsed = time.time() - start
                page_times.append(elapsed)

                assert len(results) == 20

            # Pagination should not significantly affect performance
            assert max(page_times) < min(page_times) * 2


class TestMemoryEfficiency:
    """Test memory efficiency."""

    def test_streaming_large_results(self):
        """Test memory usage with streaming large results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            db = BibliographyDB(db_path)

            # Add entries with large abstracts
            entries = []
            for i in range(1000):
                entry = BibEntry(
                    key=f"mem{i:04d}",
                    entry_type="article",
                    fields={
                        "title": f"Memory Test {i}",
                        "author": "Test Author",
                        "year": "2023",
                        "abstract": "Large abstract. " * 100,  # ~1.5KB per entry
                    },
                    source_file=Path("test.bib"),
                )
                entries.append(entry)

            db.insert_entries_batch(entries)

            # Process results in chunks
            engine = SearchEngine(db_path)

            processed = 0
            chunk_size = 50

            while True:
                results = engine.search("Memory", limit=chunk_size, offset=processed)
                if not results:
                    break

                processed += len(results)

                # Verify we're getting expected chunks
                assert len(results) <= chunk_size

            assert processed == 1000


class TestOptimizations:
    """Test query and index optimizations."""

    def test_query_optimization(self):
        """Test that queries are optimized properly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "optimize.db"
            db = BibliographyDB(db_path)

            # Add test data
            entries = generate_test_entries(1000)
            db.insert_entries_batch(entries)

            engine = SearchEngine(db_path)

            # Complex query that could be optimized
            complex_query = (
                "(author:Author AND year:2023) OR (author:Author AND year:2022)"
            )

            # Should complete efficiently
            start = time.time()
            engine.search(complex_query)
            elapsed = time.time() - start

            assert elapsed < 0.1  # Under 100ms

    def test_index_optimization(self):
        """Test index optimization after bulk operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "optimize_index.db"
            db = BibliographyDB(db_path)

            # Add and remove many entries
            entries = generate_test_entries(1000)
            db.insert_entries_batch(entries)

            # Delete half
            db.execute_sql("DELETE FROM entries WHERE rowid % 2 = 0")
            db.execute_sql("DELETE FROM entries_fts WHERE rowid % 2 = 0")

            # Optimize
            db.optimize()

            # Search should still be fast
            start = time.time()
            db.search_fts("test")
            elapsed = time.time() - start

            assert elapsed < 0.05  # Under 50ms


@pytest.mark.slow
class TestStressTests:
    """Stress tests (marked as slow)."""

    def test_stress_many_queries(self):
        """Stress test with many rapid queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stress.db"
            db = BibliographyDB(db_path)

            # Add test data
            entries = generate_test_entries(1000)
            db.insert_entries_batch(entries)

            engine = SearchEngine(db_path)

            # Rapid-fire queries
            start = time.time()
            for i in range(1000):
                query = f"test{i % 10}"
                engine.search(query)
            elapsed = time.time() - start

            qps = 1000 / elapsed
            print(f"Stress test: {qps:.1f} queries/sec")

            assert qps > 100  # At least 100 queries/sec


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to see print output
