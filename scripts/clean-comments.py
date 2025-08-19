#!/usr/bin/env python3
"""
Remove all @comment entries and inline comments from BibTeX files.
Uses bibtexparser to ensure clean, noise-free output.

Usage:
    clean-comments.py file.bib [file2.bib ...]
    clean-comments.py --in-place file.bib
    clean-comments.py --all
"""

import argparse
import sys
from pathlib import Path

import bibtexparser
from bibtexparser.bwriter import BibTexWriter


def clean_file(filepath: Path, in_place: bool = False) -> bool:
    """Process a single BibTeX file to remove all comments."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse BibTeX
        parser = bibtexparser.bparser.BibTexParser()
        parser.ignore_nonstandard_types = False
        parser.homogenize_fields = False
        bib_db = bibtexparser.loads(content, parser)
        
        # Count original entries and comments
        original_count = len(bib_db.entries)
        comment_count = len(bib_db.comments)
        
        # Clear all comments (both @comment entries and inline comments)
        bib_db.comments = []
        
        # Write clean output
        writer = BibTexWriter()
        writer.indent = "  "
        writer.order_entries_by = None  # Preserve existing order
        writer.align_values = False
        output = bibtexparser.dumps(bib_db, writer)
        
        if in_place:
            # Only modify if there were comments to remove
            if comment_count > 0:
                # Create backup
                backup_path = filepath.with_suffix(".bib.backup")
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(content)
                
                # Write clean content
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(output)
                
                print(f"✓ {filepath}: Removed {comment_count} comments, kept {original_count} entries (backup: {backup_path})")
            else:
                print(f"✓ {filepath}: No comments found, file unchanged")
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
        description="Remove all @comment entries and inline comments from BibTeX files"
    )
    parser.add_argument(
        "files", 
        nargs="*", 
        help="BibTeX files to clean"
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
        if clean_file(filepath, args.in_place):
            success_count += 1
    
    # Summary for multiple files
    if total_count > 1 and args.in_place:
        print(f"\nProcessed {success_count}/{total_count} files successfully")
    
    # Exit with error if any files failed
    sys.exit(0 if success_count == total_count else 1)


if __name__ == "__main__":
    main()