#!/usr/bin/env python3
"""
Automatically retry failed enrichments with exponential backoff.

This script queries the tracking database for failed enrichment attempts
and retries them using enrich-single-entry.py with intelligent backoff.

Usage examples:
  - retry-failed-enrichments.py                      # retry all failed entries
  - retry-failed-enrichments.py --older-than 7       # retry failures older than 7 days
  - retry-failed-enrichments.py --file file.bib      # retry only failures from specific file
  - retry-failed-enrichments.py --batch-size 10      # process in batches of 10
  - retry-failed-enrichments.py --dry-run            # show what would be retried
  - retry-failed-enrichments.py --max-retries 5      # limit total retry attempts per entry
"""

import argparse
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple


class FailedEntry(NamedTuple):
    """Failed entry details from database."""
    file_path: str
    entry_key: str
    last_attempt: str
    error_message: str
    retry_count: int


def get_retry_count(cursor: sqlite3.Cursor, file_path: str, entry_key: str) -> int:
    """Get the number of previous retry attempts for an entry."""
    cursor.execute(
        """
        SELECT COUNT(*) FROM enrichment_log
        WHERE file_path = ? AND entry_key = ? AND status = 'failed'
        """,
        (file_path, entry_key)
    )
    return cursor.fetchone()[0]


def get_failed_entries(
    cursor: sqlite3.Cursor,
    file_path: str | None = None,
    older_than_days: int | None = None,
    max_retries: int | None = None
) -> list[FailedEntry]:
    """Find failed entries based on criteria."""
    query = """
        SELECT 
            file_path,
            entry_key,
            last_attempt,
            error_message
        FROM latest_enrichment_status
        WHERE latest_status = 'failed'
    """
    params = []
    
    if older_than_days is not None:
        cutoff_date = datetime.now() - timedelta(days=older_than_days)
        query += " AND datetime(last_attempt) < datetime(?)"
        params.append(cutoff_date.isoformat())
    
    if file_path:
        query += " AND file_path = ?"
        params.append(file_path)
    
    query += " ORDER BY last_attempt ASC"
    
    cursor.execute(query, params)
    results = []
    
    for row in cursor.fetchall():
        retry_count = get_retry_count(cursor, row[0], row[1])
        
        # Filter by max retries if specified
        if max_retries is not None and retry_count >= max_retries:
            continue
            
        results.append(FailedEntry(
            file_path=row[0],
            entry_key=row[1],
            last_attempt=row[2],
            error_message=row[3] or "Unknown error",
            retry_count=retry_count
        ))
    
    return results


def calculate_backoff(retry_count: int) -> int:
    """Calculate exponential backoff delay in seconds."""
    # Base delay of 2 seconds, exponentially increasing up to 5 minutes
    base_delay = 2
    max_delay = 300  # 5 minutes
    delay = min(base_delay * (2 ** retry_count), max_delay)
    return delay


def retry_enrichment(entry: FailedEntry, dry_run: bool = False) -> bool:
    """Retry enriching a single entry."""
    if dry_run:
        print(f"[DRY RUN] Would retry: {entry.file_path} - {entry.entry_key}")
        return True
    
    # Check if file exists
    if not Path(entry.file_path).exists():
        print(f"✗ File not found: {entry.file_path}")
        return False
    
    # Calculate and apply backoff
    if entry.retry_count > 0:
        delay = calculate_backoff(entry.retry_count)
        print(f"  Waiting {delay}s (retry #{entry.retry_count + 1})...")
        time.sleep(delay)
    
    # Run enrichment
    cmd = [
        sys.executable,
        "scripts/enrich-single-entry.py",
        entry.file_path,
        entry.entry_key
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60  # 1 minute timeout per entry
        )
        
        if result.returncode == 0:
            print(f"✓ Successfully enriched: {entry.entry_key}")
            return True
        elif result.returncode == 2:
            print(f"⚠ Partial success: {entry.entry_key} (no indicators found)")
            return False
        else:
            print(f"✗ Failed to enrich: {entry.entry_key}")
            if result.stderr:
                print(f"  Error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"✗ Timeout enriching: {entry.entry_key}")
        # Track the timeout
        track_cmd = [
            sys.executable,
            "scripts/track-enrichment.py",
            entry.file_path,
            entry.entry_key,
            "failed",
            "",
            "Enrichment timeout after 60 seconds"
        ]
        subprocess.run(track_cmd, capture_output=True)
        return False
    except Exception as e:
        print(f"✗ Error enriching {entry.entry_key}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retry failed enrichment attempts with exponential backoff"
    )
    parser.add_argument(
        "--file",
        help="Retry only failures from specific BibTeX file"
    )
    parser.add_argument(
        "--older-than",
        type=int,
        metavar="DAYS",
        help="Retry only failures older than specified days"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Number of entries to process in one batch (default: 20)"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        help="Maximum total retry attempts per entry"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be retried without actually doing it"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=1,
        help="Base delay between entries in seconds (default: 1)"
    )
    
    args = parser.parse_args()
    
    # Check database exists
    db_path = "bibliography.db"
    if not Path(db_path).exists():
        print(
            "No tracking database found. Run: python3 scripts/init-tracking-db.py",
            file=sys.stderr
        )
        sys.exit(1)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get failed entries
        failed_entries = get_failed_entries(
            cursor,
            file_path=args.file,
            older_than_days=args.older_than,
            max_retries=args.max_retries
        )
        
        if not failed_entries:
            print("No failed entries found matching criteria.")
            return
        
        # Display summary
        print(f"Found {len(failed_entries)} failed entries to retry")
        if args.dry_run:
            print("[DRY RUN MODE - No actual enrichment will be performed]")
        print("-" * 80)
        
        # Show sample of entries
        for i, entry in enumerate(failed_entries[:5]):
            print(
                f"{entry.file_path} | {entry.entry_key} | "
                f"Retries: {entry.retry_count} | Last: {entry.last_attempt}"
            )
        if len(failed_entries) > 5:
            print(f"... and {len(failed_entries) - 5} more")
        print("-" * 80)
        
        # Process in batches
        total_processed = 0
        total_success = 0
        
        for batch_start in range(0, len(failed_entries), args.batch_size):
            batch_end = min(batch_start + args.batch_size, len(failed_entries))
            batch = failed_entries[batch_start:batch_end]
            
            print(f"\nProcessing batch {batch_start + 1}-{batch_end} of {len(failed_entries)}")
            
            for i, entry in enumerate(batch):
                print(f"\n[{batch_start + i + 1}/{len(failed_entries)}] "
                      f"Retrying: {entry.file_path} - {entry.entry_key}")
                
                success = retry_enrichment(entry, dry_run=args.dry_run)
                
                if success:
                    total_success += 1
                total_processed += 1
                
                # Delay between entries (unless it's the last one or dry run)
                if not args.dry_run and i < len(batch) - 1:
                    time.sleep(args.delay)
            
            # Show progress
            if not args.dry_run:
                print(f"\nBatch complete: {total_success}/{total_processed} successful")
                
                # Longer delay between batches
                if batch_end < len(failed_entries):
                    batch_delay = args.delay * 5
                    print(f"Waiting {batch_delay}s before next batch...")
                    time.sleep(batch_delay)
        
        # Final summary
        print("\n" + "=" * 80)
        if args.dry_run:
            print(f"DRY RUN COMPLETE: Would retry {len(failed_entries)} entries")
        else:
            print(f"RETRY COMPLETE: {total_success}/{total_processed} successful")
            if total_success < total_processed:
                print(f"Run again to retry the {total_processed - total_success} remaining failures")
                
    finally:
        conn.close()


if __name__ == "__main__":
    main()