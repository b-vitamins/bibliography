#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from core.bibtex_io import parse_bib_file


def verify_bib_file(file_path: str | Path) -> bool:
    """Verify that a BibTeX file can be parsed correctly."""
    file_path = Path(file_path)

    if not file_path.exists():
        print(f"Error: File {file_path} does not exist")
        return False

    try:
        bib_db = parse_bib_file(file_path)

        entry_count = len(bib_db.entries)
        comment_count = len(bib_db.comments)
        string_count = len(bib_db.strings)
        preamble_count = len(bib_db.preambles)

        print(
            f"✓ {file_path}: {entry_count} entries, {string_count} strings, "
            f"{comment_count} comments, {preamble_count} preambles"
        )
        return True

    except Exception as e:
        print(f"✗ {file_path}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify BibTeX files are valid")
    parser.add_argument("files", nargs="+", help="BibTeX files to verify")

    args = parser.parse_args()

    success_count = 0
    total_count = len(args.files)

    for file_path in args.files:
        if verify_bib_file(file_path):
            success_count += 1

    print(f"\nVerified {success_count}/{total_count} files successfully")
    if success_count < total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
