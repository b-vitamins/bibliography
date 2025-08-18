#!/usr/bin/env python3
"""Finalize the addition of an enriched BibTeX entry to the target file.

Reads the enriched entry, appends it to the target, and cleans up.

Usage: finalize-entry.py target.bib tmp/pending-enrichment/entry.bib
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def verify_enrichment(entry_text: str) -> bool:
    """Check if entry has been enriched (has openalex field)."""
    return "openalex" in entry_text.lower()


def extract_entry_key(entry_text: str) -> str | None:
    """Extract the entry key from BibTeX entry."""
    match = re.match(r"@\w+\{([^,\s]+)", entry_text.strip())
    return match.group(1) if match else None


def extract_openalex_id(entry_text: str) -> str | None:
    """Extract OpenAlex ID from entry."""
    match = re.search(r"openalex\s*=\s*\{([^}]+)\}", entry_text, re.IGNORECASE)
    return match.group(1) if match else None


def track_enrichment(
    target_file: Path,
    entry_key: str,
    success: bool,
    openalex_id: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Log enrichment to tracking database."""
    try:
        status = "success" if success else "failed"
        cmd = [
            sys.executable,
            "scripts/track-enrichment.py",
            str(target_file),
            entry_key,
            status,
        ]
        if openalex_id:
            cmd.append(openalex_id)
        if error_msg:
            cmd.append(error_msg)
        subprocess.run(cmd, capture_output=True)
    except Exception:
        pass  # Don't fail if tracking fails


def main() -> None:
    """Execute the main script logic."""
    if len(sys.argv) != 3:
        print("Usage: finalize-entry.py target.bib enriched_entry.bib", file=sys.stderr)
        sys.exit(1)

    target_file = Path(sys.argv[1])
    enriched_file = Path(sys.argv[2])

    try:
        # Check files exist
        if not target_file.exists():
            result = {
                "status": "error",
                "message": f"Target file '{target_file}' does not exist",
                "action_required": "check_target",
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        if not enriched_file.exists():
            result = {
                "status": "error",
                "message": f"Enriched file '{enriched_file}' does not exist",
                "action_required": "check_enrichment",
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        # Read enriched entry
        with enriched_file.open(encoding="utf-8") as f:
            enriched_entry = f.read().strip()

        if not enriched_entry:
            result = {
                "status": "error",
                "message": "Enriched file is empty",
                "action_required": "check_enrichment",
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        # Extract entry key for tracking
        entry_key = extract_entry_key(enriched_entry)

        # Verify enrichment happened
        is_enriched = verify_enrichment(enriched_entry)
        if not is_enriched:
            result = {
                "status": "warning",
                "message": (
                    "Entry does not appear to be enriched (no openalex field found)"
                ),
                "action_required": "verify_enrichment",
            }
            # Continue anyway - user might want to add it

        # Append to target file with proper spacing
        with target_file.open("a", encoding="utf-8") as f:
            # Ensure there's a blank line before the new entry
            f.write("\n\n")
            f.write(enriched_entry)
            if not enriched_entry.endswith("\n"):
                f.write("\n")

        # Track enrichment in database (ensure relative path)
        if entry_key:
            # Convert to relative path for consistent tracking
            relative_target = (
                target_file.relative_to(Path.cwd())
                if target_file.is_absolute()
                else target_file
            )

            if is_enriched:
                openalex_id = extract_openalex_id(enriched_entry)
                track_enrichment(relative_target, entry_key, True, openalex_id)
            else:
                track_enrichment(
                    relative_target,
                    entry_key,
                    False,
                    error_msg="No openalex field",
                )

        # Clean up temporary file
        if enriched_file.parent.name == "pending-enrichment":
            shutil.rmtree(enriched_file.parent, ignore_errors=True)

        # Success output
        result = {
            "status": "success",
            "message": f"Entry successfully added to {target_file}",
            "action_required": "none",
            "verification": f"tail -20 {target_file}",
        }
        print(json.dumps(result, indent=2))

    except Exception as e:
        result = {"status": "error", "message": str(e), "action_required": "debug"}
        print(json.dumps(result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
