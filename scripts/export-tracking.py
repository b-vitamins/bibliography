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


def normalize_timestamp(raw: Any) -> str | None:
    """Normalize timestamp-like values without introducing current-time drift."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    candidate = text.replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(candidate)
        return parsed.isoformat()
    except ValueError:
        # Preserve original value if it is not ISO-like.
        return text


def export_database(
    db_path: str = "bibliography.db", output_file: str = "tracking.json"
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
            ORDER BY timestamp, file_path, entry_key
        """)

        entries: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            entry: dict[str, Any] = dict(row)
            entry["timestamp"] = normalize_timestamp(entry.get("timestamp"))
            entries.append(entry)

        export_timestamp = entries[-1]["timestamp"] if entries else None

        # Create export data structure
        export_data: dict[str, Any] = {
            "export_version": "1.0",
            "export_timestamp": export_timestamp,
            "database_path": str(db_path),
            "total_entries": len(entries),
            "enrichment_log": entries,
        }

        rendered = json.dumps(export_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

        existing = None
        output_path = Path(output_file)
        if output_path.exists():
            existing = output_path.read_text(encoding="utf-8")

        # Avoid rewriting file when exported content is unchanged.
        if existing == rendered:
            print(f"✓ Tracking export already up to date: {output_file}")
            return True

        output_path.write_text(rendered, encoding="utf-8")

        print(f"✓ Exported {len(entries)} enrichment records to {output_file}")
        return True

    except Exception as e:
        print(f"Error exporting database: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()


def main() -> None:
    output_file = sys.argv[1] if len(sys.argv) > 1 else "tracking.json"
    success = export_database(output_file=output_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
