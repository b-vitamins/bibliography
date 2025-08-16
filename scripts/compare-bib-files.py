#!/usr/bin/env python3

import sys
import re
from pathlib import Path


def extract_entry_keys(bib_file):
    """Extract all entry keys from a BibTeX file."""
    keys = []
    entry_pattern = re.compile(r'^@\w+\s*\{\s*([^,\s]+)', re.IGNORECASE)
    
    try:
        with open(bib_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line.startswith('@'):
                    match = entry_pattern.match(line)
                    if match:
                        key = match.group(1).strip()
                        keys.append((key, line_num))
    except FileNotFoundError:
        print(f"Error: File '{bib_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading '{bib_file}': {e}")
        sys.exit(1)
    
    return keys


def find_missing_entries(original_file, enriched_file):
    """Find entries in original that are missing from enriched."""
    original_keys = extract_entry_keys(original_file)
    enriched_keys = extract_entry_keys(enriched_file)
    
    original_key_set = {key for key, _ in original_keys}
    enriched_key_set = {key for key, _ in enriched_keys}
    
    missing_keys = original_key_set - enriched_key_set
    
    missing_entries = []
    for key, line_num in original_keys:
        if key in missing_keys:
            missing_entries.append((key, line_num))
    
    return missing_entries


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 compare-bib-files.py <original.bib> <enriched.bib>")
        print("Example: python3 compare-bib-files.py award.bib award.bib.enriched")
        sys.exit(1)
    
    original_file = sys.argv[1]
    enriched_file = sys.argv[2]
    
    if not Path(original_file).exists():
        print(f"Error: Original file '{original_file}' does not exist.")
        sys.exit(1)
    
    if not Path(enriched_file).exists():
        print(f"Error: Enriched file '{enriched_file}' does not exist.")
        sys.exit(1)
    
    missing_entries = find_missing_entries(original_file, enriched_file)
    
    if not missing_entries:
        original_count = len(extract_entry_keys(original_file))
        enriched_count = len(extract_entry_keys(enriched_file))
        print(f"All entries from {original_file} are present in {enriched_file}")
        print(f"Original: {original_count} entries, Enriched: {enriched_count} entries")
    else:
        print(f"Missing entries from {original_file} (not in {enriched_file}):")
        print("Entry Number | Line Number | Entry Key")
        print("-" * 45)
        
        for i, (key, line_num) in enumerate(missing_entries, 1):
            print(f"{i:12} | {line_num:11} | {key}")
        
        print(f"\nTotal missing: {len(missing_entries)} entries")


if __name__ == "__main__":
    main()