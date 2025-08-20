#!/usr/bin/env python3
"""
Automated single-entry enrichment with tracking.

This script is designed to be called from within Claude Code's environment
where it can programmatically invoke the bibtex-entry-enricher agent.

Usage: enrich-single-entry.py <target_file> <entry_key>

Returns:
  0 - Success (entry enriched and tracked)
  1 - Failure (enrichment failed or entry not found)
  2 - Partial success (enrichment ran but no indicators found)
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode


def extract_entry_by_key(file_path: str, entry_key: str) -> str | None:
    """Extract a single entry from a BibTeX file by its key."""
    parser = BibTexParser()
    parser.customization = convert_to_unicode  # type: ignore[attr-defined]

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        bib_db = bibtexparser.loads(content, parser=parser)

        for entry in bib_db.entries:
            if entry.get("ID") == entry_key:
                # Create a temporary database with just this entry
                temp_db = bibtexparser.bibdatabase.BibDatabase()
                temp_db.entries = [entry]
                return bibtexparser.dumps(temp_db)

        return None
    except Exception as e:
        print(f"Error parsing BibTeX file: {e}", file=sys.stderr)
        return None


def extract_openalex_id(content: str) -> str | None:
    """Extract OpenAlex ID from BibTeX content."""
    match = re.search(r"openalex\s*=\s*\{([^}]+)\}", content, re.IGNORECASE)
    return match.group(1) if match else None


def check_enrichment(content: str) -> bool:
    """Check if entry has enrichment indicators."""
    indicators = ["openalex", "pdf", "abstract"]
    content_lower = content.lower()
    return any(indicator in content_lower for indicator in indicators)


def track_enrichment(
    file_path: str,
    entry_key: str,
    success: bool,
    openalex_id: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Track the enrichment result using the track-enrichment.py script."""
    cmd = [
        sys.executable,
        "scripts/track-enrichment.py",
        file_path,
        entry_key,
        "success" if success else "failed",
    ]
    if openalex_id:
        cmd.append(openalex_id)
    if error_msg:
        cmd.append(error_msg)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout:
            print(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error tracking enrichment: {e.stderr}", file=sys.stderr)


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Usage: enrich-single-entry.py <target_file> <entry_key>", file=sys.stderr
        )
        print(
            "\nThis script enriches a single entry and tracks the result.",
            file=sys.stderr,
        )
        print("Designed to be called from Claude Code environment.", file=sys.stderr)
        sys.exit(1)

    target_file = sys.argv[1]
    entry_key = sys.argv[2]

    # Verify target file exists
    if not Path(target_file).exists():
        print(f"Error: Target file '{target_file}' not found", file=sys.stderr)
        sys.exit(1)

    # Extract the entry
    print(f"Extracting entry '{entry_key}' from {target_file}")
    entry_content = extract_entry_by_key(target_file, entry_key)

    if not entry_content:
        print(f"Error: Entry '{entry_key}' not found in {target_file}", file=sys.stderr)
        track_enrichment(target_file, entry_key, False, error_msg="Entry not found")
        sys.exit(1)

    # Create temporary file for enrichment
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".bib",
        prefix=f"enrich_{entry_key}_",
        dir="tmp",  # Use local tmp directory
        delete=False,
        encoding="utf-8",
    ) as tmp_file:
        tmp_file.write(entry_content)
        tmp_path = tmp_file.name

    try:
        print(f"Created temporary file: {tmp_path}")

        # ENRICHMENT_MARKER: This is where Claude Code should invoke the agent
        # Task(subagent_type="bibtex-entry-enricher", prompt=f"Please enrich the BibTeX entry in the file: {tmp_path}")
        print(f"ENRICHMENT_REQUIRED: {tmp_path}")

        # After enrichment, read back the result
        with open(tmp_path, "r", encoding="utf-8") as f:
            enriched_content = f.read()

        # Check if enriched
        is_enriched = check_enrichment(enriched_content)
        openalex_id = extract_openalex_id(enriched_content) if is_enriched else None

        # Track the result
        if is_enriched:
            print(f"Entry enriched successfully (OpenAlex ID: {openalex_id})")
            track_enrichment(target_file, entry_key, True, openalex_id)

            # Save the enriched entry for later use
            result_path = f"tmp/enriched_{entry_key}.bib"
            with open(result_path, "w", encoding="utf-8") as f:
                f.write(enriched_content)
            print(f"Enriched entry saved to: {result_path}")
            sys.exit(0)
        else:
            print("Entry processed but no enrichment indicators found")
            track_enrichment(
                target_file, entry_key, False, error_msg="No enrichment indicators"
            )
            sys.exit(2)

    except Exception as e:
        print(f"Error during enrichment: {e}", file=sys.stderr)
        track_enrichment(target_file, entry_key, False, error_msg=str(e))
        sys.exit(1)
    finally:
        # Clean up temporary file
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()


if __name__ == "__main__":
    main()
