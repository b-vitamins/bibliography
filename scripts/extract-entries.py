#!/usr/bin/env python3
"""
Extract BibTeX entries from a file and write them as individual files.
Creates tmp/<basename>/entry-N.bib for each entry.
"""

import shutil
import sys
from pathlib import Path


def find_entry_end(lines: list[str], start_idx: int) -> int:
    """Find the end line of a BibTeX entry by tracking brace depth."""
    brace_depth = 0
    in_quotes = False
    escape_next = False

    for i in range(start_idx, len(lines)):
        line = lines[i]

        for char in line:
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not in_quotes:
                in_quotes = True
            elif char == '"' and in_quotes:
                in_quotes = False
            elif char == "{" and not in_quotes:
                brace_depth += 1
            elif char == "}" and not in_quotes:
                brace_depth -= 1
                if brace_depth == 0:
                    return i

    return -1  # Entry not properly closed


def should_skip_entry(entry_type: str) -> bool:
    """Check if this entry type should be skipped."""
    skip_types = ["@string", "@preamble", "@comment"]
    return any(entry_type.lower().startswith(t) for t in skip_types)


def extract_and_write_entries(filepath: str | Path, output_dir: Path) -> int:
    """Extract all BibTeX entries and write them as individual files."""
    entries_written = 0

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return entries_written

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    i = 0
    entry_num = 1

    while i < len(lines):
        line = lines[i].strip()

        # Look for entry start
        if line.startswith("@"):
            # Check if we should skip this entry type
            entry_type = line.split("{")[0]
            if should_skip_entry(entry_type):
                i += 1
                continue

            start_idx = i

            # Find the closing brace
            end_idx = find_entry_end(lines, i)

            if end_idx != -1:
                # Extract entry text
                entry_text = "".join(lines[start_idx : end_idx + 1])

                # Write to individual file
                entry_file = output_dir / f"entry-{entry_num}.bib"
                with open(entry_file, "w", encoding="utf-8") as f:
                    f.write(entry_text)

                entries_written += 1
                entry_num += 1
                i = end_idx + 1
            else:
                # Malformed entry, skip to next @ or end of file
                print(f"Warning: Unclosed entry at line {i + 1}", file=sys.stderr)
                i += 1
        else:
            i += 1

    return entries_written


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: extract-entries.py <bibfile>", file=sys.stderr)
        sys.exit(1)

    filepath = Path(sys.argv[1])

    if not filepath.exists():
        print(f"Error: File '{filepath}' not found", file=sys.stderr)
        sys.exit(1)

    # Create output directory based on input filename
    basename = filepath.stem
    output_dir = Path("tmp") / basename

    # Clean existing directory if it exists
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # Extract and write entries
    entries_written = extract_and_write_entries(filepath, output_dir)

    # Print summary
    print(f"Extracted {entries_written} entries to {output_dir}/")
    print(f"Files: entry-1.bib through entry-{entries_written}.bib")


if __name__ == "__main__":
    main()
