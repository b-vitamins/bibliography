#!/usr/bin/env python3
"""
Track enrichment attempts in the SQLite database.
Can be called by enrichment workflows to log results.

Usage: track-enrichment.py <file_path> <entry_key> <status> [openalex_id] [error_msg]
"""

import sqlite3
import sys
from pathlib import Path


def log_enrichment(
    file_path: str,
    entry_key: str,
    status: str,
    openalex_id: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Log an enrichment attempt to the database with atomic transaction."""
    # Skip temporary files outside the repository
    path_obj = Path(file_path)
    if path_obj.is_absolute() and not path_obj.is_relative_to(Path.cwd()):
        print(f"⚠ Skipping tracking for external file: {file_path}")
        return

    # Skip files in tmp/ directory
    if str(path_obj).startswith("tmp/") or "/tmp/" in str(path_obj):
        print(f"⚠ Skipping tracking for temporary file: {file_path}")
        return

    db_path = "bibliography.db"

    # Initialize DB if it doesn't exist
    if not Path(db_path).exists():
        import subprocess

        subprocess.run([sys.executable, "scripts/init-tracking-db.py", db_path])

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Start transaction explicitly
        conn.execute("BEGIN TRANSACTION")

        cursor.execute(
            """
            INSERT INTO enrichment_log
                (file_path, entry_key, status, openalex_id, error_message)
            VALUES (?, ?, ?, ?, ?)
        """,
            (file_path, entry_key, status, openalex_id, error_msg),
        )

        # Commit only if everything succeeded
        conn.commit()
        print(f"✓ Logged {status} for {entry_key} in {file_path}")

    except sqlite3.IntegrityError:
        # Rollback transaction
        conn.rollback()
        # Entry already logged for this timestamp (within same second)
        print(f"⚠ Entry already logged recently: {entry_key}")
    except Exception as e:
        # Rollback transaction on any error
        conn.rollback()
        print(f"✗ Error logging enrichment: {e}", file=sys.stderr)
        print(f"✗ Transaction rolled back - database unchanged", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


def main() -> None:
    if len(sys.argv) < 4:
        print(
            "Usage: track-enrichment.py <file_path> <entry_key> <status> "
            "[openalex_id] [error_msg]",
            file=sys.stderr,
        )
        print("Status must be: success, failed, or skipped", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    entry_key = sys.argv[2]
    status = sys.argv[3]
    openalex_id = sys.argv[4] if len(sys.argv) > 4 else None
    error_msg = sys.argv[5] if len(sys.argv) > 5 else None

    if status not in ["success", "failed", "skipped"]:
        print(
            f"Error: Invalid status '{status}'. Must be success, failed, or skipped",
            file=sys.stderr,
        )
        sys.exit(1)

    log_enrichment(file_path, entry_key, status, openalex_id, error_msg)


if __name__ == "__main__":
    main()
