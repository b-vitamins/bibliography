#!/usr/bin/env python3
"""
Export enrichment tracking database to a version-control friendly JSON format.
Captures complete state for reconstruction on other machines.

Usage: export-tracking.py [output_file]
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def export_database(
    db_path: str = "bibliography.db", output_file: str = "enrichment-tracking.json"
) -> bool:
    """Export all enrichment data to JSON format."""

    if not Path(db_path).exists():
        print("No tracking database found. Nothing to export.", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get all enrichment log entries
        cursor.execute("""
            SELECT 
                file_path,
                entry_key,
                timestamp,
                status,
                openalex_id,
                error_message,
                enrichment_version
            FROM enrichment_log
            ORDER BY timestamp
        """)

        entries: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            entry: dict[str, Any] = dict(row)
            # Ensure timestamp is ISO format string
            if entry["timestamp"]:
                # SQLite stores as string already, just verify format
                try:
                    datetime.fromisoformat(entry["timestamp"].replace(" ", "T"))
                except ValueError:
                    # If not valid ISO, try to parse and convert
                    entry["timestamp"] = datetime.now().isoformat()
            entries.append(entry)

        # Create export data structure
        export_data: dict[str, Any] = {
            "export_version": "1.0",
            "export_timestamp": datetime.now().isoformat(),
            "database_path": str(db_path),
            "total_entries": len(entries),
            "enrichment_log": entries,
        }

        # Write to file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Exported {len(entries)} enrichment records to {output_file}")
        return True

    except Exception as e:
        print(f"Error exporting database: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()


def main() -> None:
    output_file = sys.argv[1] if len(sys.argv) > 1 else "enrichment-tracking.json"
    success = export_database(output_file=output_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
