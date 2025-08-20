#!/usr/bin/env python3
"""
Count BibTeX entries in a file, handling edge cases.
Provides quick count without full parsing.
Now with optional enrichment statistics.
"""

import argparse
import re
import sys
from pathlib import Path


def count_entries(filepath: str | Path) -> int:
    """Count valid BibTeX entries in the file."""
    count = 0
    skip_patterns = [r"^@string\s*{", r"^@preamble\s*{", r"^@comment\s*{"]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("@") and not any(
                    re.match(pattern, line, re.IGNORECASE) for pattern in skip_patterns
                ):
                    count += 1
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 0

    return count


def count_enriched_entries(filepath: str | Path) -> int:
    """Count entries that have been successfully enriched according to the database."""
    import sqlite3

    db_path = "bibliography.db"
    if not Path(db_path).exists():
        return 0  # No database means nothing has been enriched

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(DISTINCT entry_key) 
            FROM latest_enrichment_status 
            WHERE file_path = ? AND latest_status = 'success'
        """,
            (str(filepath),),
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception:
        return 0  # If database query fails, assume nothing is enriched


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count BibTeX entries with optional enrichment stats"
    )
    parser.add_argument("bibfile", help="BibTeX file to analyze")
    parser.add_argument(
        "--enrichment-stats",
        action="store_true",
        help="Show enrichment statistics from tracking database",
    )

    args = parser.parse_args()
    filepath = Path(args.bibfile)

    if not filepath.exists():
        print(f"Error: File '{filepath}' not found", file=sys.stderr)
        sys.exit(1)

    total_count = count_entries(filepath)

    if args.enrichment_stats:
        enriched_count = count_enriched_entries(filepath)
        unenriched_count = total_count - enriched_count

        print(f"Total entries: {total_count}")
        print(f"Enriched entries: {enriched_count}")
        print(f"Unenriched entries: {unenriched_count}")
        if total_count > 0:
            percentage = (enriched_count / total_count) * 100
            print(f"Enrichment percentage: {percentage:.1f}%")
    else:
        print(total_count)


if __name__ == "__main__":
    main()
