"""SQLite database for bibliography entries with FTS5 support.

This module follows Guix's locate.scm pattern for efficient database-backed search.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import BibEntry


class BibliographyDB:
    """SQLite database for bibliography entries with FTS5 full-text search."""

    def __init__(self, db_path: Path):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema with FTS5 virtual table."""
        with self._get_connection() as conn:
            # Check if FTS5 is available
            cursor = conn.execute("PRAGMA compile_options")
            compile_options = [row[0] for row in cursor.fetchall()]
            if not any("FTS5" in opt for opt in compile_options):
                raise RuntimeError("SQLite FTS5 extension not available")

            # Create schema version table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """)

            # Insert schema version if not exists
            conn.execute("""
                INSERT OR IGNORE INTO schema_version (version, description)
                VALUES (1, 'Initial schema with FTS5 support')
            """)

            # Create main entries table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    entry_type TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    data TEXT NOT NULL,  -- JSON serialized fields
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create FTS5 virtual table for full-text search
            # Using porter tokenizer for better stemming
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                    key,
                    title,
                    author,
                    abstract,
                    keywords,
                    journal,
                    year,
                    tokenize='porter unicode61'
                )
            """)

            # Create triggers to keep FTS index in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                    INSERT INTO entries_fts(
                        key, title, author, abstract, keywords, journal, year
                    )
                    VALUES (
                        new.key,
                        COALESCE(json_extract(new.data, '$.title'), ''),
                        COALESCE(json_extract(new.data, '$.author'), ''),
                        COALESCE(json_extract(new.data, '$.abstract'), ''),
                        COALESCE(json_extract(new.data, '$.keywords'), ''),
                        COALESCE(json_extract(new.data, '$.journal'), ''),
                        COALESCE(json_extract(new.data, '$.year'), '')
                    );
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                    DELETE FROM entries_fts WHERE key = old.key;
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
                    DELETE FROM entries_fts WHERE key = old.key;
                    INSERT INTO entries_fts(
                        key, title, author, abstract, keywords, journal, year
                    )
                    VALUES (
                        new.key,
                        COALESCE(json_extract(new.data, '$.title'), ''),
                        COALESCE(json_extract(new.data, '$.author'), ''),
                        COALESCE(json_extract(new.data, '$.abstract'), ''),
                        COALESCE(json_extract(new.data, '$.keywords'), ''),
                        COALESCE(json_extract(new.data, '$.journal'), ''),
                        COALESCE(json_extract(new.data, '$.year'), '')
                    );
                    UPDATE entries SET updated_at = CURRENT_TIMESTAMP WHERE id = new.id;
                END
            """)

            # Create indexes for efficient lookups
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_key ON entries(key)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_type ON entries(entry_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_source ON entries(source_file)"
            )

            conn.commit()

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Get database connection with proper settings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        # Use WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode = WAL")
        # Optimize for performance
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = 10000")
        conn.execute("PRAGMA temp_store = MEMORY")
        try:
            yield conn
        finally:
            conn.close()

    def clear_all(self) -> None:
        """Clear all entries from database."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM entries")
            conn.commit()

    def insert_entry(self, entry: BibEntry) -> None:
        """Insert a single entry into database.

        Args:
            entry: BibEntry to insert
        """
        with self._get_connection() as conn:
            data = json.dumps(entry.fields, ensure_ascii=False)
            conn.execute(
                """
                INSERT OR REPLACE INTO entries (key, entry_type, source_file, data)
                VALUES (?, ?, ?, ?)
            """,
                (entry.key, entry.entry_type, str(entry.source_file), data),
            )
            conn.commit()

    def insert_entries_batch(
        self, entries: list[BibEntry], batch_size: int = 1000
    ) -> None:
        """Insert entries in batches for better performance.

        Args:
            entries: List of BibEntry objects to insert
            batch_size: Number of entries per batch
        """
        with self._get_connection() as conn:
            # Prepare data for batch insert
            for i in range(0, len(entries), batch_size):
                batch = entries[i : i + batch_size]
                values = []

                for entry in batch:
                    data = json.dumps(entry.fields, ensure_ascii=False)
                    values.append(
                        (entry.key, entry.entry_type, str(entry.source_file), data)
                    )

                # Bulk insert
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO entries (key, entry_type, source_file, data)
                    VALUES (?, ?, ?, ?)
                """,
                    values,
                )

            conn.commit()

    def get_entry_by_key(self, key: str) -> BibEntry | None:
        """Get entry by citation key.

        Args:
            key: Citation key to search for

        Returns:
            BibEntry if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT key, entry_type, source_file, data
                FROM entries
                WHERE key = ?
            """,
                (key,),
            )

            row = cursor.fetchone()
            if row:
                return self._row_to_entry(row)
            return None

    def get_entries_by_file(self, file_path: str) -> list[BibEntry]:
        """Get all entries from a specific source file.

        Args:
            file_path: Path to source .bib file

        Returns:
            List of entries from that file
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT key, entry_type, source_file, data
                FROM entries
                WHERE source_file = ?
                ORDER BY key
            """,
                (str(file_path),),
            )

            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def search_fts(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> list[tuple[BibEntry, float]]:
        """Search entries using FTS5 MATCH operator.

        Args:
            query: FTS5 query string
            limit: Maximum results to return
            offset: Offset for pagination

        Returns:
            List of (entry, rank) tuples sorted by relevance
        """
        with self._get_connection() as conn:
            if not query or not query.strip():
                # Empty query - return recent entries
                cursor = conn.execute(
                    """
                    SELECT e.key, e.entry_type, e.source_file, e.data, 50.0 as rank
                    FROM entries e
                    ORDER BY e.id DESC
                    LIMIT ? OFFSET ?
                """,
                    (limit, offset),
                )
            else:
                try:
                    # FTS5 search with ranking
                    cursor = conn.execute(
                        """
                        SELECT e.key, e.entry_type, e.source_file, e.data,
                               bm25(entries_fts) as rank
                        FROM entries e
                        JOIN entries_fts ON e.key = entries_fts.key
                        WHERE entries_fts MATCH ?
                        ORDER BY rank DESC
                        LIMIT ? OFFSET ?
                    """,
                        (query, limit, offset),
                    )
                except Exception:
                    # If FTS5 query fails, return empty results
                    cursor = conn.execute(
                        """
                        SELECT e.key, e.entry_type, e.source_file, e.data, 0.0 as rank
                        FROM entries e
                        WHERE 0 = 1
                        LIMIT ? OFFSET ?
                    """,
                        (limit, offset),
                    )

            results = []
            for row in cursor:
                entry = self._row_to_entry(row)
                # Convert BM25 score to 0-100 scale (higher is better)
                rank = max(0, min(100, 100 - abs(row["rank"]) * 10))
                results.append((entry, rank))

            return results

    def search_by_field(
        self, field: str, value: str, limit: int = 20
    ) -> list[BibEntry]:
        """Search entries by specific field value.

        Args:
            field: Field name to search
            value: Value to match
            limit: Maximum results

        Returns:
            List of matching entries
        """
        with self._get_connection() as conn:
            if field in ["key", "entry_type", "source_file"]:
                # Direct column search
                cursor = conn.execute(
                    f"""
                    SELECT key, entry_type, source_file, data
                    FROM entries
                    WHERE {field} = ?
                    LIMIT ?
                """,
                    (value, limit),
                )
            else:
                # JSON field search
                cursor = conn.execute(
                    """
                    SELECT key, entry_type, source_file, data
                    FROM entries
                    WHERE json_extract(data, '$.' || ?) = ?
                    LIMIT ?
                """,
                    (field, value, limit),
                )

            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def locate_file(
        self, file_pattern: str, glob_match: bool = False
    ) -> list[BibEntry]:
        """Find entries by file path (like guix locate).

        Args:
            file_pattern: File pattern to search for
            glob_match: Whether to use GLOB matching

        Returns:
            List of entries containing matching files
        """
        with self._get_connection() as conn:
            if glob_match:
                # Use GLOB for pattern matching
                cursor = conn.execute(
                    """
                    SELECT DISTINCT e.key, e.entry_type, e.source_file, e.data
                    FROM entries e
                    WHERE json_extract(e.data, '$.file') GLOB ?
                    ORDER BY e.key
                """,
                    (f"*{file_pattern}*",),
                )
            else:
                # Exact substring match
                cursor = conn.execute(
                    """
                    SELECT DISTINCT e.key, e.entry_type, e.source_file, e.data
                    FROM entries e
                    WHERE json_extract(e.data, '$.file') LIKE ?
                    ORDER BY e.key
                """,
                    (f"%{file_pattern}%",),
                )

            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def get_statistics(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary with database statistics
        """
        with self._get_connection() as conn:
            stats = {}

            # Total entries
            cursor = conn.execute("SELECT COUNT(*) FROM entries")
            stats["total_entries"] = cursor.fetchone()[0]

            # Entries by type
            cursor = conn.execute("""
                SELECT entry_type, COUNT(*) as count
                FROM entries
                GROUP BY entry_type
                ORDER BY count DESC
            """)
            stats["by_type"] = dict(cursor.fetchall())

            # Entries by source file
            cursor = conn.execute("""
                SELECT source_file, COUNT(*) as count
                FROM entries
                GROUP BY source_file
                ORDER BY count DESC
            """)
            stats["by_file"] = dict(cursor.fetchall())

            # Database file size
            stats["db_size_bytes"] = (
                self.db_path.stat().st_size if self.db_path.exists() else 0
            )

            # FTS5 statistics
            cursor = conn.execute("SELECT COUNT(*) FROM entries_fts")
            stats["fts_entries"] = cursor.fetchone()[0]

            return stats

    def _row_to_entry(self, row: sqlite3.Row) -> BibEntry:
        """Convert database row to BibEntry object.

        Args:
            row: SQLite row from entries table

        Returns:
            BibEntry object
        """
        fields = json.loads(row["data"])
        return BibEntry(
            key=row["key"],
            entry_type=row["entry_type"],
            fields=fields,
            source_file=Path(row["source_file"]),
        )

    def execute_sql(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        """Execute arbitrary SQL (for testing purposes).

        Args:
            sql: SQL query to execute
            params: Query parameters
        """
        with self._get_connection() as conn:
            if params:
                conn.execute(sql, params)
            else:
                conn.execute(sql)
            conn.commit()

    def optimize(self) -> None:
        """Optimize database and rebuild FTS index."""
        with self._get_connection() as conn:
            # Rebuild FTS index
            conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
            # Optimize FTS index
            conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('optimize')")
            conn.commit()

        # Vacuum needs to be outside of transaction
        conn = sqlite3.connect(self.db_path)
        conn.execute("VACUUM")
        conn.close()

    def rebuild_fts_from_entries(self) -> None:
        """Rebuild FTS table from entries table to fix inconsistencies."""
        with self._get_connection() as conn:
            # Delete all FTS entries
            conn.execute("DELETE FROM entries_fts")

            # Re-insert all entries from main table
            conn.execute("""
                INSERT INTO entries_fts(
                    key, title, author, abstract, keywords, journal, year
                )
                SELECT
                    key,
                    COALESCE(json_extract(data, '$.title'), ''),
                    COALESCE(json_extract(data, '$.author'), ''),
                    COALESCE(json_extract(data, '$.abstract'), ''),
                    COALESCE(json_extract(data, '$.keywords'), ''),
                    COALESCE(json_extract(data, '$.journal'), ''),
                    COALESCE(json_extract(data, '$.year'), '')
                FROM entries
            """)
            conn.commit()
