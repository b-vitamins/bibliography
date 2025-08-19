#!/usr/bin/env python3
"""
Sort BibTeX entries by year in descending order (newest first).
Processes one or more .bib files to ensure entries are ordered from latest to oldest.

Usage: 
    sort-by-year.py file.bib [file2.bib ...]
    sort-by-year.py --in-place file.bib
    sort-by-year.py --all
"""

import argparse
import sys
from pathlib import Path

import bibtexparser
from bibtexparser.bwriter import BibTexWriter


def get_entry_year(entry: dict) -> int:
    """Extract year from entry, returning 0 if not found."""
    year_str = entry.get("year", "0")
    try:
        # Handle year ranges like "2023-2024" by taking the first year
        if "-" in year_str:
            year_str = year_str.split("-")[0]
        return int(year_str.strip())
    except ValueError:
        return 0


def sort_entries_by_year(entries: list[dict]) -> list[dict]:
    """Sort entries by year in descending order (newest first)."""
    return sorted(entries, key=get_entry_year, reverse=True)


def process_file(filepath: Path, in_place: bool = False) -> bool:
    """Process a single BibTeX file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse BibTeX
        parser = bibtexparser.bparser.BibTexParser()
        parser.ignore_nonstandard_types = False
        parser.homogenize_fields = False
        bib_db = bibtexparser.loads(content, parser)
        
        if not bib_db.entries:
            print(f"✓ {filepath}: No entries to sort", file=sys.stderr)
            return True
        
        # Check if already sorted
        original_years = [get_entry_year(e) for e in bib_db.entries]
        sorted_years = sorted(original_years, reverse=True)
        
        if original_years == sorted_years:
            print(f"✓ {filepath}: Already sorted (newest first)")
            return True
        
        # Sort entries
        sorted_entries = sort_entries_by_year(bib_db.entries)
        bib_db.entries = sorted_entries
        
        # Write output
        writer = BibTexWriter()
        writer.indent = "  "
        writer.order_entries_by = None  # Preserve our sort order
        writer.align_values = False
        output = bibtexparser.dumps(bib_db, writer)
        
        if in_place:
            # Create backup
            backup_path = filepath.with_suffix(".bib.backup")
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            # Write sorted content
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(output)
            
            print(f"✓ {filepath}: Sorted {len(bib_db.entries)} entries (backup: {backup_path})")
        else:
            # Output to stdout
            print(output, end="")
        
        return True
        
    except FileNotFoundError:
        print(f"✗ {filepath}: File not found", file=sys.stderr)
        return False
    except Exception as e:
        print(f"✗ {filepath}: {e}", file=sys.stderr)
        return False


def find_all_bib_files() -> list[Path]:
    """Find all .bib files in by-domain/ and by-format/ directories."""
    bib_files = []
    for base_dir in ["by-domain", "by-format"]:
        if Path(base_dir).exists():
            bib_files.extend(Path(base_dir).rglob("*.bib"))
    return sorted(bib_files)


def main():
    parser = argparse.ArgumentParser(
        description="Sort BibTeX entries by year (newest first)"
    )
    parser.add_argument(
        "files", 
        nargs="*", 
        help="BibTeX files to sort"
    )
    parser.add_argument(
        "--in-place", "-i",
        action="store_true",
        help="Modify files in place (creates .backup files)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all .bib files in by-domain/ and by-format/"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files are sorted without modifying"
    )
    
    args = parser.parse_args()
    
    # Determine which files to process
    if args.all:
        files = find_all_bib_files()
        if not files:
            print("No .bib files found in by-domain/ or by-format/", file=sys.stderr)
            sys.exit(1)
    elif args.files:
        files = [Path(f) for f in args.files]
    else:
        parser.print_help()
        sys.exit(1)
    
    # Process files
    success_count = 0
    total_count = len(files)
    
    for filepath in files:
        if args.check:
            # Just check if sorted
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                parser = bibtexparser.bparser.BibTexParser()
                parser.ignore_nonstandard_types = False
                parser.homogenize_fields = False
                bib_db = bibtexparser.loads(content, parser)
                
                original_years = [get_entry_year(e) for e in bib_db.entries]
                sorted_years = sorted(original_years, reverse=True)
                
                if original_years == sorted_years:
                    print(f"✓ {filepath}: Sorted")
                    success_count += 1
                else:
                    print(f"✗ {filepath}: Not sorted")
            except Exception as e:
                print(f"✗ {filepath}: Error checking: {e}", file=sys.stderr)
        else:
            if process_file(filepath, args.in_place):
                success_count += 1
    
    # Summary for multiple files
    if total_count > 1 and args.in_place:
        print(f"\nProcessed {success_count}/{total_count} files successfully")
    
    # Exit with error if any files failed
    sys.exit(0 if success_count == total_count else 1)


if __name__ == "__main__":
    main()