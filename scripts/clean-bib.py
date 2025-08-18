#!/usr/bin/env python3

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import convert_to_unicode  # type: ignore[import-untyped]


def clean_entry_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Clean individual entry fields of common artifacts."""
    for field, value in entry.items():
        if isinstance(value, str):
            # Remove literal EOF markers
            value = re.sub(r"\bEOF\b", "", value)
            # Remove other control characters
            value = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", value)
            # Remove excess whitespace
            value = " ".join(value.split())
            # Clean up common shell artifacts
            value = value.replace("\\n", " ").replace("\\t", " ")
            entry[field] = value
    return entry


def clean_bib_file(
    input_path: str | Path, output_path: str | Path | None = None, backup: bool = True
) -> bool:
    """Clean a BibTeX file of stray characters and artifacts."""
    input_path = Path(input_path)

    if not input_path.exists():
        print(f"Error: File {input_path} does not exist")
        return False

    if output_path is None:
        output_path = input_path.with_suffix(".bib.clean")
    else:
        output_path = Path(output_path)

    # Create backup if requested
    if backup and not str(input_path).endswith(".bib.clean"):
        backup_path = input_path.with_suffix(".bib.backup")
        if not backup_path.exists():
            import shutil

            shutil.copy2(input_path, backup_path)
            print(f"Created backup: {backup_path}")

    try:
        # Configure parser for robust parsing
        parser = BibTexParser(common_strings=True)
        parser.customization = convert_to_unicode  # type: ignore[attr-defined]
        parser.ignore_nonstandard_types = False  # type: ignore[attr-defined]

        # Read and parse the BibTeX file
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Clean the raw content first
        # Remove literal EOF markers that might be in the text
        content = re.sub(r"\bEOF\b", "", content)
        # Remove control characters except newlines and tabs
        content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content)

        # Parse the cleaned content
        bib_db = bibtexparser.loads(content, parser=parser)  # type: ignore[no-untyped-call]

        # Clean individual entries
        cleaned_entries: list[dict[str, Any]] = []
        for entry in bib_db.entries:  # type: ignore[arg-type]
            cleaned_entry = clean_entry_fields(entry)  # type: ignore[arg-type]
            cleaned_entries.append(cleaned_entry)

        # Create new database with cleaned entries
        clean_db = BibDatabase()
        clean_db.entries = cleaned_entries
        clean_db.comments = bib_db.comments  # type: ignore[arg-type]
        clean_db.preambles = bib_db.preambles  # type: ignore[arg-type]
        clean_db.strings = bib_db.strings  # type: ignore[arg-type]

        # Configure writer for clean output
        writer = BibTexWriter()
        writer.indent = "  "
        writer.align_values = True
        writer.order_entries_by = ("ID",)
        writer.add_trailing_comma = False
        writer.common_strings = False

        # Write cleaned BibTeX
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(writer.write(clean_db))  # type: ignore[no-untyped-call]

        print(f"Cleaned {len(bib_db.entries)} entries: {input_path} → {output_path}")  # type: ignore[arg-type]
        return True

    except Exception as e:
        print(f"Error processing {input_path}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean BibTeX files of stray characters and artifacts"
    )
    parser.add_argument("files", nargs="+", help="BibTeX files to clean")
    parser.add_argument(
        "--output", "-o", help="Output file (only valid for single input file)"
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Do not create backup files"
    )
    parser.add_argument("--in-place", action="store_true", help="Modify files in place")

    args = parser.parse_args()

    if len(args.files) > 1 and args.output:
        print("Error: --output can only be used with a single input file")
        sys.exit(1)

    success_count = 0
    total_count = len(args.files)

    for file_path in args.files:
        if args.in_place:
            output_path = file_path
        elif args.output:
            output_path = args.output
        else:
            output_path = None

        if clean_bib_file(file_path, output_path, backup=not args.no_backup):
            success_count += 1

    print(f"\nCleaned {success_count}/{total_count} files successfully")
    if success_count < total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
