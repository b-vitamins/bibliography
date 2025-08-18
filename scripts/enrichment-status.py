#!/usr/bin/env python3
"""
Query enrichment status from the tracking database.
Shows comprehensive statistics and identifies entries needing attention.

Usage: enrichment-status.py [file.bib] [--retry-candidates] [--never-tried]
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_file_stats(cursor: sqlite3.Cursor, file_path: str | None = None) -> list[sqlite3.Row]:
    """Get enrichment statistics for a file or all files."""
    if file_path:
        cursor.execute(
            """
            SELECT * FROM enrichment_stats WHERE file_path = ?
        """,
            (file_path,),
        )
    else:
        cursor.execute("SELECT * FROM enrichment_stats ORDER BY file_path")

    return cursor.fetchall()


def get_retry_candidates(
    cursor: sqlite3.Cursor, days_old: int = 7, file_path: str | None = None
) -> list[sqlite3.Row]:
    """Find failed entries older than specified days."""
    cutoff_date = datetime.now() - timedelta(days=days_old)

    query = """
        SELECT file_path, entry_key, last_attempt, error_message
        FROM latest_enrichment_status
        WHERE latest_status = 'failed'
        AND datetime(last_attempt) < datetime(?)
    """
    params = [cutoff_date.isoformat()]

    if file_path:
        query += " AND file_path = ?"
        params.append(file_path)

    cursor.execute(query, params)
    return cursor.fetchall()


def get_never_tried(cursor: sqlite3.Cursor, file_path: str) -> list[str]:
    """Find entries in file that were never enriched."""
    # This requires parsing the actual bib file
    # For now, return entries with 'skipped' status
    cursor.execute(
        """
        SELECT entry_key FROM latest_enrichment_status
        WHERE file_path = ? AND latest_status = 'skipped'
    """,
        (file_path,),
    )

    return [row[0] for row in cursor.fetchall()]


def get_recent_activity(cursor: sqlite3.Cursor, days: int = 30) -> list[sqlite3.Row]:
    """Get recent enrichment activity."""
    cutoff_date = datetime.now() - timedelta(days=days)

    cursor.execute(
        """
        SELECT 
            DATE(timestamp) as date,
            COUNT(*) as attempts,
            COUNT(CASE WHEN status = 'success' THEN 1 END) as successes,
            COUNT(CASE WHEN status = 'failed' THEN 1 END) as failures
        FROM enrichment_log
        WHERE datetime(timestamp) > datetime(?)
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
        LIMIT 10
    """,
        (cutoff_date.isoformat(),),
    )

    return cursor.fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description="Query enrichment tracking database")
    parser.add_argument("file", nargs="?", help="Specific BibTeX file to analyze")
    parser.add_argument(
        "--retry-candidates",
        action="store_true",
        help="Show entries that failed and should be retried",
    )
    parser.add_argument(
        "--never-tried",
        action="store_true",
        help="Show entries that were never enriched",
    )
    parser.add_argument(
        "--recent", action="store_true", help="Show recent enrichment activity"
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    args = parser.parse_args()

    db_path = "bibliography.db"
    if not Path(db_path).exists():
        print(
            "No tracking database found. Run: python3 scripts/init-tracking-db.py",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if args.recent:
            activity = get_recent_activity(cursor)
            if args.json:
                print(json.dumps([dict(row) for row in activity], indent=2))
            else:
                print("Recent Enrichment Activity (last 30 days):")
                print("-" * 50)
                for row in activity:
                    print(
                        f"{row['date']}: {row['attempts']} attempts, "
                        f"{row['successes']} success, {row['failures']} failed"
                    )

        elif args.retry_candidates:
            candidates = get_retry_candidates(cursor, file_path=args.file)
            if args.json:
                print(json.dumps([dict(row) for row in candidates], indent=2))
            else:
                print("Failed entries older than 7 days:")
                print("-" * 80)
                for row in candidates:
                    print(
                        f"{row['file_path']} | {row['entry_key']} | "
                        f"Last: {row['last_attempt']} | {row['error_message']}"
                    )

        elif args.never_tried and args.file:
            never_tried = get_never_tried(cursor, args.file)
            if args.json:
                print(json.dumps(never_tried, indent=2))
            else:
                print(f"Entries never enriched in {args.file}:")
                for key in never_tried:
                    print(f"  - {key}")

        else:
            # Show general stats
            stats = get_file_stats(cursor, args.file)

            if args.json:
                print(json.dumps([dict(row) for row in stats], indent=2))
            else:
                print("Enrichment Statistics:")
                print("-" * 80)
                print(
                    f"{'File':<40} {'Total':>8} "
                    f"{'Success':>8} {'Failed':>8} {'Skipped':>8}"
                )
                print("-" * 80)

                total_entries = 0
                total_success = 0
                total_failed = 0

                for row in stats:
                    print(
                        f"{row['file_path']:<40} {row['total_entries']:>8} "
                        f"{row['successful']:>8} {row['failed']:>8} {row['skipped']:>8}"
                    )
                    total_entries += row["total_entries"]
                    total_success += row["successful"]
                    total_failed += row["failed"]

                if len(stats) > 1:
                    print("-" * 80)
                    print(
                        f"{'TOTAL':<40} {total_entries:>8} "
                        f"{total_success:>8} {total_failed:>8}"
                    )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
