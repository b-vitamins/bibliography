#!/usr/bin/env python3
"""
Count BibTeX entries in a file, handling edge cases.
Provides quick count without full parsing.
"""

import sys
import re
from pathlib import Path


def count_entries(filepath):
    """Count valid BibTeX entries in the file."""
    count = 0
    skip_patterns = [r'^@string\s*{', r'^@preamble\s*{', r'^@comment\s*{']
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('@'):
                    # Check if it's a type we should skip
                    if not any(re.match(pattern, line, re.IGNORECASE) for pattern in skip_patterns):
                        count += 1
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 0
    
    return count


def main():
    if len(sys.argv) != 2:
        print("Usage: count-entries.py <bibfile>", file=sys.stderr)
        sys.exit(1)
    
    filepath = Path(sys.argv[1])
    
    if not filepath.exists():
        print(f"Error: File '{filepath}' not found", file=sys.stderr)
        sys.exit(1)
    
    count = count_entries(filepath)
    print(count)


if __name__ == "__main__":
    main()