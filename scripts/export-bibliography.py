#!/usr/bin/env python3
"""
Export bibliography with associated PDF files.

Extracts PDF files referenced in BibTeX entries and copies them to a structured
output directory along with the bibliography file itself.

Usage:
    python3 scripts/export-bibliography.py <bib_file> <output_dir>

Example:
    python3 scripts/export-bibliography.py curated/simulation.bib /home/b/downloads

This creates:
    /home/b/downloads/simulation/
    ├── simulation.bib
    └── [PDFs from file fields that exist locally]
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

import bibtexparser
from bibtexparser.bparser import BibTexParser


def setup_logging(verbose: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_bib_file(bib_path: Path) -> List[dict]:
    """Parse BibTeX file and return entries."""
    try:
        with open(bib_path, "r", encoding="utf-8") as f:
            parser = BibTexParser(common_strings=True)
            bib_db = bibtexparser.load(f, parser=parser)
            return bib_db.entries
    except Exception as e:
        logging.error(f"Failed to parse BibTeX file {bib_path}: {e}")
        sys.exit(1)


def extract_pdf_path(entry: dict) -> str | None:
    """Extract PDF file path from BibTeX entry."""
    file_field = entry.get("file", "")
    if not file_field:
        return None

    # Parse file field format: :path:type or path:type
    # Common formats: ":/path/to/file.pdf:pdf" or "/path/to/file.pdf:pdf"
    if ":" in file_field:
        parts = file_field.split(":")
        if len(parts) >= 2:
            # Find the part that looks like a path
            for part in parts:
                if part and (part.endswith(".pdf") or "/home/" in part):
                    return part.strip()

    # Fallback: treat entire field as path if it looks like one
    if file_field.endswith(".pdf") or "/home/" in file_field:
        return file_field.strip()

    return None


def get_safe_filename(entry_id: str, original_path: str) -> str:
    """Generate safe filename for PDF copy."""
    original_name = Path(original_path).name
    
    # If the original filename already starts with the entry ID, use as-is
    if original_name.lower().startswith(entry_id.lower()):
        safe_name = original_name
    else:
        # Use entry ID as prefix to avoid conflicts
        safe_name = f"{entry_id}_{original_name}"
    
    # Replace problematic characters
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-")
    return safe_name


def copy_pdf_files(entries: List[dict], output_dir: Path) -> Tuple[int, int]:
    """Copy PDF files to output directory. Returns (copied, total_with_files)."""
    copied_count = 0
    total_with_files = 0

    for entry in entries:
        entry_id = entry.get("ID", "unknown")
        pdf_path = extract_pdf_path(entry)

        if not pdf_path:
            continue

        total_with_files += 1
        source_path = Path(pdf_path)

        if not source_path.exists():
            logging.warning(f"Entry {entry_id}: PDF not found at {pdf_path}")
            continue

        if not source_path.is_file():
            logging.warning(f"Entry {entry_id}: Path is not a file: {pdf_path}")
            continue

        try:
            safe_filename = get_safe_filename(entry_id, pdf_path)
            dest_path = output_dir / safe_filename

            # Avoid overwriting if same file already exists
            if dest_path.exists():
                if dest_path.stat().st_size == source_path.stat().st_size:
                    logging.debug(f"Entry {entry_id}: PDF already exists, skipping")
                    copied_count += 1
                    continue
                else:
                    # Add counter to make unique
                    counter = 1
                    stem = dest_path.stem
                    suffix = dest_path.suffix
                    while dest_path.exists():
                        dest_path = output_dir / f"{stem}_{counter}{suffix}"
                        counter += 1

            shutil.copy2(source_path, dest_path)
            logging.info(
                f"Entry {entry_id}: Copied {source_path.name} → {dest_path.name}"
            )
            copied_count += 1

        except Exception as e:
            logging.error(f"Entry {entry_id}: Failed to copy {pdf_path}: {e}")

    return copied_count, total_with_files


def export_bibliography(
    bib_path: Path, output_base: Path, dry_run: bool = False
) -> None:
    """Main export function."""
    if not bib_path.exists():
        logging.error(f"Bibliography file not found: {bib_path}")
        sys.exit(1)

    # Create output directory named after bib file
    bib_name = bib_path.stem
    output_dir = output_base / bib_name

    if dry_run:
        logging.info(f"DRY RUN: Would create directory {output_dir}")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Created output directory: {output_dir}")

    # Parse bibliography
    entries = parse_bib_file(bib_path)
    logging.info(f"Found {len(entries)} entries in bibliography")

    # Copy bibliography file
    if not dry_run:
        dest_bib = output_dir / f"{bib_name}.bib"
        shutil.copy2(bib_path, dest_bib)
        logging.info(f"Copied bibliography: {bib_path.name} → {dest_bib}")

    # Process PDF files
    if dry_run:
        # Count what would be processed
        total_with_files = sum(1 for entry in entries if extract_pdf_path(entry))
        valid_files = 0
        for entry in entries:
            pdf_path = extract_pdf_path(entry)
            if pdf_path and Path(pdf_path).exists():
                valid_files += 1
        logging.info(
            f"DRY RUN: Would process {valid_files}/{total_with_files} PDF files"
        )
    else:
        copied, total_with_files = copy_pdf_files(entries, output_dir)
        logging.info(f"Successfully copied {copied}/{total_with_files} PDF files")

    logging.info(f"Export completed: {output_dir}")


def main() -> None:
    """Command line interface."""
    parser = argparse.ArgumentParser(
        description="Export bibliography with associated PDF files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("bib_file", type=Path, help="Path to BibTeX file")
    parser.add_argument("output_dir", type=Path, help="Output directory path")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without copying"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    export_bibliography(args.bib_file, args.output_dir, args.dry_run)


if __name__ == "__main__":
    main()
