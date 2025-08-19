#!/usr/bin/env python3
"""
Initialize or update the enrichment tracking SQLite database.
Creates bibliography.db with proper schema for tracking enrichment history.
"""

import sqlite3
import sys


def init_database(db_path: str = "bibliography.db") -> None:
    """Initialize the enrichment tracking database with atomic transaction."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Start transaction explicitly
        conn.execute("BEGIN TRANSACTION")

        # Create enrichment tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enrichment_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                entry_key TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT CHECK(status IN ('success', 'failed', 'skipped')) NOT NULL,
                openalex_id TEXT,
                error_message TEXT,
                enrichment_version TEXT DEFAULT '1.0',
                UNIQUE(file_path, entry_key, timestamp)
            )
        """)

        # Create index for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entry_lookup 
            ON enrichment_log(file_path, entry_key)
        """)

        # Create a view for latest status per entry
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS latest_enrichment_status AS
            SELECT 
                file_path,
                entry_key,
                MAX(timestamp) as last_attempt,
                status as latest_status,
                openalex_id,
                error_message,
                enrichment_version
            FROM enrichment_log
            GROUP BY file_path, entry_key
        """)

        # Create stats view
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS enrichment_stats AS
            SELECT 
                file_path,
                COUNT(DISTINCT entry_key) as total_entries,
                COUNT(DISTINCT CASE WHEN latest_status = 'success' THEN entry_key END)
                    as successful,
                COUNT(DISTINCT CASE WHEN latest_status = 'failed' THEN entry_key END)
                    as failed,
                COUNT(DISTINCT CASE WHEN latest_status = 'skipped' THEN entry_key END)
                    as skipped
            FROM latest_enrichment_status
            GROUP BY file_path
        """)

        # Commit only if all schema creation succeeded
        conn.commit()
        print(f"✓ Initialized tracking database: {db_path}")

    except Exception as e:
        # Rollback transaction on any error
        conn.rollback()
        print(f"✗ Error initializing database: {e}", file=sys.stderr)
        print(f"✗ Transaction rolled back - database unchanged", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "bibliography.db"
    init_database(db_path)
