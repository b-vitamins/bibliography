#!/usr/bin/env python3
"""
Track enrichment results after batch processing.
Analyzes enriched entries and updates the tracking database.

Usage: track-batch-enrichment.py file.bib tmp/file/
"""

import re
import subprocess
import sys
from pathlib import Path


def extract_entry_key(content: str) -> str | None:
    """Extract entry key from BibTeX content."""
    match = re.match(r"@\w+\{([^,\s]+)", content.strip())
    return match.group(1) if match else None


def extract_openalex_id(content: str) -> str | None:
    """Extract OpenAlex ID from BibTeX content."""
    match = re.search(r"openalex\s*=\s*\{([^}]+)\}", content, re.IGNORECASE)
    return match.group(1) if match else None


def check_enrichment(content: str) -> bool:
    """Check if entry has enrichment indicators."""
    indicators = ["openalex", "pdf", "abstract"]
    content_lower = content.lower()
    return any(indicator in content_lower for indicator in indicators)


def track_entry(
    file_path: str, entry_key: str, success: bool, openalex_id: str | None = None
) -> bool:
    """Track enrichment status for a single entry."""
    try:
        status = "success" if success else "failed"
        cmd = [
            sys.executable,
            "scripts/track-enrichment.py",
            file_path,
            entry_key,
            status,
        ]
        if openalex_id:
            cmd.append(openalex_id)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: track-batch-enrichment.py file.bib tmp/file/", file=sys.stderr)
        sys.exit(1)
    
    bib_file = Path(sys.argv[1])
    tmp_dir = Path(sys.argv[2])
    
    if not bib_file.exists():
        print(f"Error: BibTeX file '{bib_file}' not found", file=sys.stderr)
        sys.exit(1)
    
    if not tmp_dir.exists():
        print(f"Error: Temporary directory '{tmp_dir}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Process all entry files in tmp directory
    entry_files = sorted(tmp_dir.glob("entry-*.bib"))
    if not entry_files:
        print(f"Error: No entry files found in '{tmp_dir}'", file=sys.stderr)
        sys.exit(1)
    
    tracked = 0
    failed = 0
    
    for entry_file in entry_files:
        try:
            with open(entry_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            entry_key = extract_entry_key(content)
            if not entry_key:
                print(f"Warning: Could not extract key from {entry_file}", file=sys.stderr)
                failed += 1
                continue
            
            # Check if enriched
            is_enriched = check_enrichment(content)
            openalex_id = extract_openalex_id(content) if is_enriched else None
            
            # Track the result
            if track_entry(str(bib_file), entry_key, is_enriched, openalex_id):
                tracked += 1
                status = "enriched" if is_enriched else "not enriched"
                print(f"✓ Tracked {entry_key}: {status}")
            else:
                failed += 1
                print(f"✗ Failed to track {entry_key}", file=sys.stderr)
                
        except Exception as e:
            print(f"Error processing {entry_file}: {e}", file=sys.stderr)
            failed += 1
    
    print(f"\nSummary: {tracked} entries tracked, {failed} failures")
    
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()