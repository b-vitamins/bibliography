#!/usr/bin/env python3
"""
Prepare a single BibTeX entry for enrichment.
Checks for duplicates and creates a temporary file for agent processing.

Usage: prepare-entry.py target.bib "@article{key2024, ...}"
       prepare-entry.py target.bib entry.bib
"""

import json
import re
import sys
from pathlib import Path


def extract_entry_key(entry_text: str) -> str | None:
    """Extract the entry key from a BibTeX entry."""
    match = re.match(r"@\w+\{([^,\s]+)", entry_text.strip())
    return match.group(1) if match else None


def check_duplicate(target_file: Path, entry_key: str) -> bool:
    """Check if entry key already exists in target file."""
    if not target_file.exists():
        return False

    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Look for the entry key in the file
    pattern = rf"@\w+\{{{entry_key}\s*,"
    return bool(re.search(pattern, content, re.IGNORECASE))


def read_entry(entry_source: str) -> str:
    """Read entry from string or file."""
    # Check if it's a file path
    if not entry_source.startswith("@") and Path(entry_source).exists():
        with open(entry_source, "r", encoding="utf-8") as f:
            return f.read().strip()
    else:
        return entry_source.strip()


def main() -> None:
    if len(sys.argv) != 3:
        print('Usage: prepare-entry.py target.bib "@article{...}"', file=sys.stderr)
        print("       prepare-entry.py target.bib entry.bib", file=sys.stderr)
        sys.exit(1)

    target_file = Path(sys.argv[1])
    entry_source = sys.argv[2]

    # Prepare output directory
    output_dir = Path("tmp/pending-enrichment")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "entry.bib"

    try:
        # Read the entry
        entry_text = read_entry(entry_source)

        # Extract entry key
        entry_key = extract_entry_key(entry_text)
        if not entry_key:
            result = {
                "status": "error",
                "message": "Could not extract entry key from BibTeX entry",
                "action_required": "fix_entry",
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        # Check target file exists
        if not target_file.exists():
            result = {
                "status": "error",
                "message": f"Target file '{target_file}' does not exist",
                "action_required": "create_file",
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        # Check for duplicates
        if check_duplicate(target_file, entry_key):
            result = {
                "status": "error",
                "message": (
                    f"Entry with key '{entry_key}' already exists in {target_file}"
                ),
                "action_required": "use_different_key",
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        # Write entry to temporary file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(entry_text)
            f.write("\n")

        # Success output
        result = {
            "status": "ready",
            "action_required": "enrichment",
            "entry_key": entry_key,
            "target_file": str(target_file),
            "temp_file": str(output_file),
            "next_step": (
                "Run enrichment via Claude, then: "
                f"python3 scripts/finalize-entry.py {target_file} {output_file}"
            ),
        }
        print(json.dumps(result, indent=2))

    except Exception as e:
        result = {"status": "error", "message": str(e), "action_required": "debug"}
        print(json.dumps(result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
