#!/usr/bin/env python3
"""
Import enrichment tracking data from JSON export into SQLite database.
Reconstructs complete enrichment history on new machines.

Usage: import-tracking.py [input_file]
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def import_database(
    input_file: str = "tracking.json", db_path: str = "bibliography.db"
) -> bool:
    """Import enrichment data from JSON export."""

    if not Path(input_file).exists():
        print(f"Import file '{input_file}' not found.", file=sys.stderr)
        return False

    # Initialize database if needed
    if not Path(db_path).exists():
        import subprocess

        result = subprocess.run(
            [sys.executable, "scripts/init-tracking-db.py", db_path],
            capture_output=True,
        )
        if result.returncode != 0:
            print("Failed to initialize database", file=sys.stderr)
            return False

    conn: sqlite3.Connection | None = None
    try:
        # Read import data
        with open(input_file, "r", encoding="utf-8") as f:
            import_data: dict[str, Any] = json.load(f)

        if "enrichment_log" not in import_data:
            print("Invalid import file format", file=sys.stderr)
            return False

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Import entries
        imported: int = 0
        skipped: int = 0

        for entry in import_data["enrichment_log"]:
            try:
                cursor.execute(
                    """
                    INSERT INTO enrichment_log 
                    (file_path, entry_key, timestamp, status, openalex_id, 
                     error_message, enrichment_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        entry["file_path"],
                        entry["entry_key"],
                        entry["timestamp"],
                        entry["status"],
                        entry.get("openalex_id"),
                        entry.get("error_message"),
                        entry.get("enrichment_version", "1.0"),
                    ),
                )
                imported += 1
            except sqlite3.IntegrityError:
                # Entry already exists (same timestamp)
                skipped += 1
            except Exception as e:
                entry_key = entry.get("entry_key", "?")
                print(
                    f"Warning: Failed to import entry {entry_key}: {e}", file=sys.stderr
                )

        conn.commit()

        print(f"✓ Import complete: {imported} new records, {skipped} already existed")
        print(f"✓ Total records in database: {imported + skipped}")

        # Show summary statistics
        cursor.execute(
            "SELECT COUNT(DISTINCT file_path) as files, "
            "COUNT(DISTINCT entry_key) as entries FROM enrichment_log"
        )
        stats = cursor.fetchone()
        print(f"✓ Tracking {stats[1]} unique entries across {stats[0]} files")

        return True

    except json.JSONDecodeError as e:
        print(f"Error parsing import file: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error importing data: {e}", file=sys.stderr)
        return False
    finally:
        if conn is not None:
            conn.close()


def main() -> None:
    input_file = sys.argv[1] if len(sys.argv) > 1 else "tracking.json"
    success = import_database(input_file=input_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
