#!/usr/bin/env python3
"""
Track bijection (bidirectional consistency) between BibTeX entries and PDF files.

Uses SQLite database (bibliography.db) to efficiently track:
1. BibTeX entries and their expected PDF locations
2. PDF files and their corresponding entries
3. Bijection status and inconsistencies

Integrates with tracking.json for version control.
"""

import argparse
import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime
import hashlib
import re
from glob import glob
from typing import Dict, List, Tuple, Optional, Any, Union
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

# Database file
DB_FILE = "bibliography.db"

# Base directory for all PDFs
BASE_DIR = Path("/home/b/documents")

# Mapping of BibTeX entry types to subdirectories
TYPE_TO_DIR = {
    "article": "articles",
    "inproceedings": "inproceedings",
    "phdthesis": "phdthesis",
    "mastersthesis": "mastersthesis",
    "book": "books",
    "incollection": "incollection",
    "inbook": "inbook",
    "proceedings": "proceedings",
    "techreport": "techreports",
    "unpublished": "unpublished",
    "misc": "misc",
    "online": "online",
    "manual": "manuals",
    "booklet": "booklets",
    "conference": "conferences",
    "phdproposal": "phdproposal",
    "masterthesis": "mastersthesis",  # Alternative spelling
}


def init_database() -> None:
    """Initialize the bijection tracking tables."""
    conn: sqlite3.Connection = sqlite3.connect(DB_FILE)
    c: sqlite3.Cursor = conn.cursor()

    # Table for BibTeX entry tracking
    c.execute("""
        CREATE TABLE IF NOT EXISTS bib_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            entry_key TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            has_pdf_field BOOLEAN,
            pdf_url TEXT,
            has_file_field BOOLEAN,
            file_field_path TEXT,
            expected_pdf_path TEXT NOT NULL,
            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_path, entry_key)
        )
    """)

    # Table for PDF file tracking
    c.execute("""
        CREATE TABLE IF NOT EXISTS pdf_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_path TEXT UNIQUE NOT NULL,
            file_size INTEGER,
            file_hash TEXT,
            entry_key TEXT,
            entry_type TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT  -- 'matched', 'orphaned', 'mismatched'
        )
    """)

    # Table for bijection status
    c.execute("""
        CREATE TABLE IF NOT EXISTS bijection_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_entries INTEGER,
            total_pdfs INTEGER,
            perfect_matches INTEGER,
            entries_missing_pdf INTEGER,
            entries_missing_file_field INTEGER,
            orphaned_pdfs INTEGER,
            bijection_score REAL
        )
    """)

    # Create indices for performance
    c.execute("CREATE INDEX IF NOT EXISTS idx_entries_key ON bib_entries(entry_key)")
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_entries_path ON bib_entries(expected_pdf_path)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_pdfs_key ON pdf_files(entry_key)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pdfs_status ON pdf_files(status)")

    conn.commit()
    conn.close()


def get_file_hash(file_path: str, quick: bool = True) -> Optional[str]:
    """Get hash of file (quick mode only hashes first/last 1MB)."""
    if not Path(file_path).exists():
        return None

    file_size = Path(file_path).stat().st_size
    hasher = hashlib.md5()

    with open(file_path, "rb") as f:
        if quick and file_size > 2 * 1024 * 1024:
            # For large files, hash first and last 1MB
            hasher.update(f.read(1024 * 1024))
            f.seek(-1024 * 1024, 2)
            hasher.update(f.read())
        else:
            # For small files or full mode, hash entire file
            while chunk := f.read(8192):
                hasher.update(chunk)

    return hasher.hexdigest()


def get_expected_pdf_path(entry_type: str, entry_key: str) -> str:
    """Get the expected PDF path for a BibTeX entry."""
    subdir = TYPE_TO_DIR.get(entry_type.lower(), "misc")
    return str(BASE_DIR / subdir / f"{entry_key}.pdf")


def update_bib_entries(bib_file: str) -> int:
    """Update database with entries from a BibTeX file."""
    conn: sqlite3.Connection = sqlite3.connect(DB_FILE)
    c: sqlite3.Cursor = conn.cursor()

    # Parse BibTeX file
    with open(bib_file, "r", encoding="utf-8") as f:
        parser = BibTexParser(common_strings=True, customization=convert_to_unicode)
        bib_db = bibtexparser.load(f, parser=parser)

    # Update each entry
    for entry in bib_db.entries:
        entry_key = entry.get("ID", "unknown")
        entry_type = entry.get("ENTRYTYPE", "misc")
        has_pdf_field = "pdf" in entry
        pdf_url = entry.get("pdf", "")
        has_file_field = "file" in entry

        # Parse file field
        file_field_path = ""
        if has_file_field:
            # Format: :/path/to/file:type
            match = re.match(r"^:(.+):\w+$", entry.get("file", ""))
            if match:
                file_field_path = match.group(1)

        expected_pdf_path = get_expected_pdf_path(entry_type, entry_key)

        # Insert or update entry
        c.execute(
            """
            INSERT OR REPLACE INTO bib_entries 
            (file_path, entry_key, entry_type, has_pdf_field, pdf_url, 
             has_file_field, file_field_path, expected_pdf_path, last_checked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
            (
                bib_file,
                entry_key,
                entry_type,
                has_pdf_field,
                pdf_url,
                has_file_field,
                file_field_path,
                expected_pdf_path,
            ),
        )

    conn.commit()
    conn.close()

    return len(bib_db.entries)


def scan_pdf_directory() -> int:
    """Scan PDF directories and update database."""
    conn: sqlite3.Connection = sqlite3.connect(DB_FILE)
    c: sqlite3.Cursor = conn.cursor()

    pdf_count = 0

    for entry_type, subdir in TYPE_TO_DIR.items():
        dir_path = BASE_DIR / subdir
        if dir_path.exists():
            for pdf_file in dir_path.glob("*.pdf"):
                pdf_path = str(pdf_file)
                entry_key = pdf_file.stem
                file_size = pdf_file.stat().st_size
                file_hash = get_file_hash(pdf_path, quick=True)

                # Check if this PDF matches any entry
                c.execute(
                    """
                    SELECT COUNT(*) FROM bib_entries 
                    WHERE expected_pdf_path = ? OR file_field_path = ?
                """,
                    (pdf_path, pdf_path),
                )

                has_entry = c.fetchone()[0] > 0
                status = "matched" if has_entry else "orphaned"

                # Insert or update PDF record
                c.execute(
                    """
                    INSERT OR REPLACE INTO pdf_files
                    (pdf_path, file_size, file_hash, entry_key, entry_type, status, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (pdf_path, file_size, file_hash, entry_key, entry_type, status),
                )

                pdf_count += 1

    # Mark PDFs not seen in this scan as potentially deleted
    c.execute("""
        UPDATE pdf_files 
        SET status = 'deleted' 
        WHERE last_seen < datetime('now', '-1 minute')
    """)

    conn.commit()
    conn.close()

    return pdf_count


def calculate_bijection() -> Dict[str, Union[int, float]]:
    """Calculate bijection statistics."""
    conn: sqlite3.Connection = sqlite3.connect(DB_FILE)
    c: sqlite3.Cursor = conn.cursor()

    # Total entries
    c.execute("SELECT COUNT(*) FROM bib_entries")
    total_entries: int = c.fetchone()[0]

    # Total PDFs (not deleted)
    c.execute("SELECT COUNT(*) FROM pdf_files WHERE status != 'deleted'")
    total_pdfs: int = c.fetchone()[0]

    # Perfect matches (entry has file field pointing to existing PDF)
    c.execute("""
        SELECT COUNT(DISTINCT be.entry_key)
        FROM bib_entries be
        JOIN pdf_files pf ON be.expected_pdf_path = pf.pdf_path
        WHERE be.has_file_field = 1 AND pf.status = 'matched'
    """)
    perfect_matches = c.fetchone()[0]

    # Entries missing PDF
    c.execute("""
        SELECT COUNT(*)
        FROM bib_entries be
        LEFT JOIN pdf_files pf ON be.expected_pdf_path = pf.pdf_path
        WHERE pf.id IS NULL OR pf.status = 'deleted'
    """)
    entries_missing_pdf = c.fetchone()[0]

    # Entries missing file field (but PDF exists)
    c.execute("""
        SELECT COUNT(*)
        FROM bib_entries be
        JOIN pdf_files pf ON be.expected_pdf_path = pf.pdf_path
        WHERE be.has_file_field = 0 AND pf.status != 'deleted'
    """)
    entries_missing_file_field = c.fetchone()[0]

    # Orphaned PDFs
    c.execute("SELECT COUNT(*) FROM pdf_files WHERE status = 'orphaned'")
    orphaned_pdfs = c.fetchone()[0]

    # Calculate bijection score
    bijection_score = (
        (perfect_matches / total_entries * 100) if total_entries > 0 else 0
    )

    # Store status
    c.execute(
        """
        INSERT INTO bijection_status
        (total_entries, total_pdfs, perfect_matches, entries_missing_pdf,
         entries_missing_file_field, orphaned_pdfs, bijection_score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            total_entries,
            total_pdfs,
            perfect_matches,
            entries_missing_pdf,
            entries_missing_file_field,
            orphaned_pdfs,
            bijection_score,
        ),
    )

    conn.commit()
    conn.close()

    return {
        "total_entries": total_entries,
        "total_pdfs": total_pdfs,
        "perfect_matches": perfect_matches,
        "entries_missing_pdf": entries_missing_pdf,
        "entries_missing_file_field": entries_missing_file_field,
        "orphaned_pdfs": orphaned_pdfs,
        "bijection_score": bijection_score,
    }


def get_action_items() -> Dict[str, List[Tuple[Any, ...]]]:
    """Get actionable items to improve bijection."""
    conn: sqlite3.Connection = sqlite3.connect(DB_FILE)
    c: sqlite3.Cursor = conn.cursor()

    actions: Dict[str, List[Tuple[Any, ...]]] = {}

    # Entries needing file field
    c.execute("""
        SELECT be.entry_key, be.file_path, be.expected_pdf_path
        FROM bib_entries be
        JOIN pdf_files pf ON be.expected_pdf_path = pf.pdf_path
        WHERE be.has_file_field = 0 AND pf.status != 'deleted'
    """)
    actions["needs_file_field"] = c.fetchall()

    # Entries needing PDF download
    c.execute("""
        SELECT be.entry_key, be.file_path, be.pdf_url
        FROM bib_entries be
        LEFT JOIN pdf_files pf ON be.expected_pdf_path = pf.pdf_path
        WHERE be.has_pdf_field = 1 AND (pf.id IS NULL OR pf.status = 'deleted')
    """)
    actions["needs_download"] = c.fetchall()

    # Orphaned PDFs
    c.execute("""
        SELECT pdf_path, entry_key, file_size
        FROM pdf_files
        WHERE status = 'orphaned'
        ORDER BY file_size DESC
    """)
    actions["orphaned_pdfs"] = c.fetchall()

    # Mismatched file fields
    c.execute("""
        SELECT be.entry_key, be.file_path, be.file_field_path, be.expected_pdf_path
        FROM bib_entries be
        WHERE be.has_file_field = 1 
        AND be.file_field_path != be.expected_pdf_path
        AND be.file_field_path != ''
    """)
    actions["mismatched_paths"] = c.fetchall()

    conn.close()
    return actions


def export_to_tracking() -> None:
    """Export bijection data to tracking.json."""
    conn: sqlite3.Connection = sqlite3.connect(DB_FILE)
    c: sqlite3.Cursor = conn.cursor()

    # Get latest status
    c.execute("""
        SELECT * FROM bijection_status
        ORDER BY check_time DESC
        LIMIT 1
    """)
    latest_status = c.fetchone()

    # Get summary counts
    c.execute("SELECT COUNT(*) FROM bib_entries")
    entry_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM pdf_files WHERE status != 'deleted'")
    pdf_count = c.fetchone()[0]

    bijection_data = {
        "last_check": latest_status[1] if latest_status else None,
        "statistics": {
            "total_entries": latest_status[2] if latest_status else 0,
            "total_pdfs": latest_status[3] if latest_status else 0,
            "perfect_matches": latest_status[4] if latest_status else 0,
            "bijection_score": latest_status[8] if latest_status else 0,
        },
        "database_counts": {"tracked_entries": entry_count, "tracked_pdfs": pdf_count},
    }

    conn.close()

    # Merge with existing tracking.json
    tracking_file = Path("tracking.json")
    if tracking_file.exists():
        with open(tracking_file, "r") as f:
            tracking_data = json.load(f)
    else:
        tracking_data = {}

    tracking_data["bijection"] = bijection_data

    with open(tracking_file, "w") as f:
        json.dump(tracking_data, f, indent=2, default=str)


def import_from_tracking() -> bool:
    """Import bijection data from tracking.json (for fresh clones)."""
    tracking_file = Path("tracking.json")
    if not tracking_file.exists():
        print("No tracking.json file found")
        return False

    with open(tracking_file, "r") as f:
        tracking_data = json.load(f)

    if "bijection" not in tracking_data:
        print("No bijection data in tracking.json")
        return False

    # Since bijection needs fresh scan, just report what was tracked
    bij_data = tracking_data["bijection"]
    print(f"Last bijection check: {bij_data.get('last_check', 'Never')}")
    print(f"Previous score: {bij_data['statistics'].get('bijection_score', 0):.1f}%")
    print("Run full update to refresh bijection tracking")

    return True


def update_all(pattern: str) -> int:
    """Update all BibTeX files matching pattern."""

    total_entries = 0
    file_count = 0

    for bib_file in sorted(glob(pattern)):
        if os.path.isfile(bib_file):
            print(f"Processing {bib_file}...")
            entries = update_bib_entries(bib_file)
            total_entries += entries
            file_count += 1

    print(f"Updated {total_entries} entries from {file_count} files")
    return total_entries


def get_detailed_stats() -> Dict[str, List[Tuple[Any, ...]]]:
    """Get detailed statistics by file and directory."""
    conn: sqlite3.Connection = sqlite3.connect(DB_FILE)
    c: sqlite3.Cursor = conn.cursor()

    # Stats by BibTeX file
    c.execute("""
        SELECT 
            file_path,
            COUNT(*) as total,
            SUM(CASE WHEN has_pdf_field THEN 1 ELSE 0 END) as with_pdf_url,
            SUM(CASE WHEN has_file_field THEN 1 ELSE 0 END) as with_file_field,
            SUM(CASE WHEN expected_pdf_path IN (SELECT pdf_path FROM pdf_files WHERE status != 'deleted') THEN 1 ELSE 0 END) as pdf_exists
        FROM bib_entries
        GROUP BY file_path
        ORDER BY file_path
    """)
    by_file = c.fetchall()

    # Stats by entry type (directory)
    c.execute("""
        SELECT 
            entry_type,
            COUNT(*) as total,
            SUM(CASE WHEN has_pdf_field THEN 1 ELSE 0 END) as with_pdf_url,
            SUM(CASE WHEN has_file_field THEN 1 ELSE 0 END) as with_file_field,
            SUM(CASE WHEN expected_pdf_path IN (SELECT pdf_path FROM pdf_files WHERE status != 'deleted') THEN 1 ELSE 0 END) as pdf_exists
        FROM bib_entries
        GROUP BY entry_type
        ORDER BY total DESC
    """)
    by_type = c.fetchall()

    # PDF stats by directory
    c.execute("""
        SELECT 
            entry_type,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'matched' THEN 1 ELSE 0 END) as matched,
            SUM(CASE WHEN status = 'orphaned' THEN 1 ELSE 0 END) as orphaned,
            SUM(file_size) / (1024.0 * 1024.0) as total_size_mb
        FROM pdf_files
        WHERE status != 'deleted'
        GROUP BY entry_type
        ORDER BY total DESC
    """)
    pdf_by_type = c.fetchall()

    conn.close()

    return {"by_file": by_file, "by_type": by_type, "pdf_by_type": pdf_by_type}


def print_top_files(n: int = 5, sort_by: str = "coverage") -> None:
    """Print top N best and worst files by specified criteria."""
    conn: sqlite3.Connection = sqlite3.connect(DB_FILE)
    c: sqlite3.Cursor = conn.cursor()

    # Get stats for all files
    c.execute("""
        SELECT 
            file_path,
            COUNT(*) as total,
            SUM(CASE WHEN expected_pdf_path IN (SELECT pdf_path FROM pdf_files WHERE status != 'deleted') THEN 1 ELSE 0 END) as pdf_exists,
            COUNT(*) - SUM(CASE WHEN expected_pdf_path IN (SELECT pdf_path FROM pdf_files WHERE status != 'deleted') THEN 1 ELSE 0 END) as missing,
            ROUND(100.0 * SUM(CASE WHEN expected_pdf_path IN (SELECT pdf_path FROM pdf_files WHERE status != 'deleted') THEN 1 ELSE 0 END) / COUNT(*), 1) as coverage
        FROM bib_entries
        GROUP BY file_path
    """)

    results: List[Tuple[str, int, int, int, float]] = []
    for row in c.fetchall():
        file_path, total, exists, missing, coverage = row
        file_name = Path(file_path).name
        results.append((file_name, total, exists, missing, coverage))

    conn.close()

    # Sort based on criteria
    if sort_by == "coverage":
        results.sort(key=lambda x: (x[4], x[1]))  # Coverage, then total
    elif sort_by == "total":
        results.sort(key=lambda x: x[1], reverse=True)
    elif sort_by == "missing":
        results.sort(key=lambda x: x[3], reverse=True)

    # Print worst N
    print(f"\n📉 WORST {n} FILES (by {sort_by}):")
    print("-" * 75)
    print(f"{'File':<35} {'Total':>8} {'Has PDF':>8} {'Missing':>8} {'Coverage':>10}")
    print("-" * 75)
    for file_name, total, exists, missing, coverage in results[:n]:
        print(f"{file_name:<35} {total:>8} {exists:>8} {missing:>8} {coverage:>9.1f}%")

    # Print best N
    print(f"\n📈 BEST {n} FILES (by {sort_by}):")
    print("-" * 75)
    print(f"{'File':<35} {'Total':>8} {'Has PDF':>8} {'Missing':>8} {'Coverage':>10}")
    print("-" * 75)

    # For best, reverse the order based on criteria
    if sort_by == "coverage":
        best_results = results[-n:][::-1]
    elif sort_by == "missing":
        best_results = results[:n]  # Best = least missing
    else:
        best_results = results[:n]

    for file_name, total, exists, missing, coverage in best_results:
        print(f"{file_name:<35} {total:>8} {exists:>8} {missing:>8} {coverage:>9.1f}%")


def print_summary(stats: Dict[str, Union[int, float]], actions: Optional[Dict[str, List[Tuple[Any, ...]]]], detailed: bool = False) -> None:
    """Print summary report."""
    print("\n" + "=" * 70)
    print("BIJECTION ANALYSIS SUMMARY")
    print("=" * 70)

    # Overall statistics
    print("\n📊 OVERALL STATISTICS")
    print(f"  BibTeX Entries: {stats['total_entries']}")
    print(f"  PDF Files: {stats['total_pdfs']}")
    print(
        f"  Perfect Matches: {stats['perfect_matches']} ({stats['bijection_score']:.1f}%)"
    )

    # One-way percentages
    entries_with_pdf = stats["total_entries"] - stats["entries_missing_pdf"]
    pdfs_with_entry = stats["total_pdfs"] - stats["orphaned_pdfs"]

    forward_percent = (
        (entries_with_pdf / stats["total_entries"] * 100)
        if stats["total_entries"] > 0
        else 0
    )
    reverse_percent = (
        (pdfs_with_entry / stats["total_pdfs"] * 100) if stats["total_pdfs"] > 0 else 0
    )

    print("\n📈 DIRECTIONAL COVERAGE")
    print(
        f"  Forward (Entries → PDFs): {entries_with_pdf}/{stats['total_entries']} ({forward_percent:.1f}%)"
    )
    print(
        f"  Reverse (PDFs → Entries): {pdfs_with_entry}/{stats['total_pdfs']} ({reverse_percent:.1f}%)"
    )

    print("\n⚠️  ISSUES")
    print(f"  Entries missing PDF: {stats['entries_missing_pdf']}")
    print(f"  Entries missing file field: {stats['entries_missing_file_field']}")
    print(f"  Orphaned PDFs: {stats['orphaned_pdfs']}")

    if detailed:
        detailed_stats = get_detailed_stats()

        # By file breakdown
        print("\n📁 BY BIBTEX FILE")
        print(
            f"{'File':<40} {'Total':>8} {'w/PDF':>8} {'w/File':>8} {'Exists':>8} {'Coverage':>10}"
        )
        print("-" * 85)
        for file_path, total, with_pdf, with_file, exists in detailed_stats["by_file"][
            :15
        ]:
            file_name = Path(file_path).name
            coverage = (exists / total * 100) if total > 0 else 0
            print(
                f"{file_name:<40} {total:>8} {with_pdf:>8} {with_file:>8} {exists:>8} {coverage:>9.1f}%"
            )

        if len(detailed_stats["by_file"]) > 15:
            print(f"... and {len(detailed_stats['by_file']) - 15} more files")

        # By entry type breakdown
        print("\n📚 BY ENTRY TYPE")
        print(
            f"{'Type':<20} {'Total':>8} {'w/PDF':>8} {'w/File':>8} {'Exists':>8} {'Coverage':>10}"
        )
        print("-" * 65)
        for entry_type, total, with_pdf, with_file, exists in detailed_stats["by_type"]:
            coverage = (exists / total * 100) if total > 0 else 0
            print(
                f"{entry_type:<20} {total:>8} {with_pdf:>8} {with_file:>8} {exists:>8} {coverage:>9.1f}%"
            )

        # PDF directory breakdown
        print("\n💾 PDF FILES BY DIRECTORY")
        print(
            f"{'Directory':<20} {'Total':>8} {'Matched':>8} {'Orphaned':>8} {'Size (MB)':>12}"
        )
        print("-" * 60)
        for entry_type, total, matched, orphaned, size_mb in detailed_stats[
            "pdf_by_type"
        ]:
            dir_name = TYPE_TO_DIR.get(entry_type, entry_type)
            print(
                f"{dir_name:<20} {total:>8} {matched:>8} {orphaned:>8} {size_mb:>11.1f}"
            )

    if actions:
        print("\n📋 ACTION ITEMS")
        if actions["needs_file_field"]:
            print(f"  • Add file field to {len(actions['needs_file_field'])} entries")
        if actions["needs_download"]:
            print(f"  • Download {len(actions['needs_download'])} PDFs")
        if actions["orphaned_pdfs"]:
            print(f"  • Handle {len(actions['orphaned_pdfs'])} orphaned PDFs")
        if actions["mismatched_paths"]:
            print(f"  • Fix {len(actions['mismatched_paths'])} mismatched paths")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Track bijection between BibTeX entries and PDFs using database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full update and analysis
  %(prog)s --update "by-*/*.bib"
  
  # Quick check (uses cached data)
  %(prog)s --check
  
  # Get action items
  %(prog)s --actions
  
  # Export to tracking.json
  %(prog)s --export
  
  # Import from tracking.json (after fresh clone)
  %(prog)s --import-data
  
  # JSON output for automation
  %(prog)s --check --json
        """,
    )

    parser.add_argument(
        "--update",
        metavar="PATTERN",
        help="Update database with BibTeX files matching pattern",
    )
    parser.add_argument(
        "--check", action="store_true", help="Check bijection status (uses cached data)"
    )
    parser.add_argument("--actions", action="store_true", help="Show actionable items")
    parser.add_argument("--export", action="store_true", help="Export to tracking.json")
    parser.add_argument(
        "--import-data", action="store_true", help="Import from tracking.json"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--export-lists", action="store_true", help="Export action lists to tmp/"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed breakdown by file and directory",
    )
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Show top N best and worst files by coverage",
    )
    parser.add_argument(
        "--sort-by",
        choices=["coverage", "total", "missing"],
        default="coverage",
        help="Sort criteria for rankings (default: coverage)",
    )

    args = parser.parse_args()

    # Initialize database
    init_database()

    if args.import_data:
        import_from_tracking()
        return

    if args.update:
        # Full update
        print("Updating BibTeX entries...")
        update_all(args.update)

        print("\nScanning PDF files...")
        pdf_count = scan_pdf_directory()
        print(f"Found {pdf_count} PDFs")

    if args.update or args.check:
        # Calculate bijection
        stats = calculate_bijection()

        if args.json:
            output = {"statistics": stats, "timestamp": datetime.now().isoformat()}
            if args.actions:
                actions = get_action_items()
                output["actions"] = {
                    "needs_file_field": len(actions["needs_file_field"]),
                    "needs_download": len(actions["needs_download"]),
                    "orphaned_pdfs": len(actions["orphaned_pdfs"]),
                    "mismatched_paths": len(actions["mismatched_paths"]),
                }
            print(json.dumps(output, indent=2))
        else:
            actions = get_action_items() if args.actions else None
            print_summary(stats, actions, detailed=args.detailed)

            if args.export_lists and actions:
                # Create tmp directory
                Path("tmp").mkdir(exist_ok=True)

                # Export action lists
                if actions["needs_file_field"]:
                    with open("tmp/needs-file-field.txt", "w") as f:
                        for entry_key, file_path, pdf_path in actions[
                            "needs_file_field"
                        ]:
                            f.write(f"{entry_key}\t{file_path}\t{pdf_path}\n")
                    print("\nCreated tmp/needs-file-field.txt")

                if actions["needs_download"]:
                    with open("tmp/needs-download.txt", "w") as f:
                        for entry_key, file_path, pdf_url in actions["needs_download"]:
                            f.write(f"{entry_key}\t{file_path}\t{pdf_url}\n")
                    print("Created tmp/needs-download.txt")

                if actions["orphaned_pdfs"]:
                    with open("tmp/orphaned-pdfs.txt", "w") as f:
                        for pdf_path, entry_key, file_size in actions["orphaned_pdfs"]:
                            size_mb = file_size / (1024 * 1024)
                            f.write(f"{pdf_path}\t{entry_key}\t{size_mb:.1f}MB\n")
                    print("Created tmp/orphaned-pdfs.txt")

    # Handle --top argument (can work independently or with update/check)
    if args.top:
        print_top_files(n=args.top, sort_by=args.sort_by)

    if args.export:
        export_to_tracking()
        print("Exported bijection data to tracking.json")


if __name__ == "__main__":
    main()
