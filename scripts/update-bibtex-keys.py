#!/usr/bin/env python3
"""Update BibTeX keys to follow lastname-year-keyword format."""

import re
import sys
from pathlib import Path


def extract_keyword_from_title(title):
    """Extract a meaningful keyword from the title."""
    # Remove BibTeX formatting
    title = re.sub(r'[{}]', '', title)
    title = re.sub(r'\\[a-zA-Z]+', '', title)
    
    # Common words to skip
    skip_words = {
        'a', 'an', 'the', 'of', 'for', 'in', 'on', 'at', 'to', 'with', 'by',
        'from', 'using', 'via', 'through', 'over', 'under', 'and', 'or',
        'as', 'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has',
        'into', 'onto', 'upon', 'about', 'against', 'between', 'during'
    }
    
    # Split into words and find the first meaningful word
    words = title.lower().split()
    for word in words:
        # Clean punctuation
        word = re.sub(r'[^a-z0-9]', '', word)
        if word and len(word) > 2 and word not in skip_words:
            return word
    
    # Fallback to first word if no meaningful word found
    if words:
        return re.sub(r'[^a-z0-9]', '', words[0])
    return 'paper'


def update_bibtex_keys(filepath):
    """Update BibTeX keys in the file to lastname-year-keyword format."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all entries
    entry_pattern = r'(@[a-zA-Z]+{)([^,]+)(,.*?)(\n})'
    entries = list(re.finditer(entry_pattern, content, re.DOTALL))
    
    # Process from end to beginning to maintain positions
    for match in reversed(entries):
        entry_type = match.group(1)
        old_key = match.group(2)
        entry_content = match.group(3)
        closing = match.group(4)
        
        # Extract author lastname
        author_match = re.search(r'author\s*=\s*{([^}]+)}', entry_content, re.IGNORECASE)
        if author_match:
            authors = author_match.group(1)
            # Get first author's last name
            if ' and ' in authors:
                first_author = authors.split(' and ')[0].strip()
            else:
                first_author = authors.strip()
            
            # Handle different name formats
            if ',' in first_author:
                # Format: Last, First
                lastname = first_author.split(',')[0].strip()
            else:
                # Format: First Last or First Middle Last
                parts = first_author.split()
                if parts:
                    lastname = parts[-1]
                else:
                    lastname = 'unknown'
        else:
            lastname = 'unknown'
        
        # Extract year
        year_match = re.search(r'year\s*=\s*{?(\d{4})}?', entry_content, re.IGNORECASE)
        if year_match:
            year = year_match.group(1)
        else:
            year = '0000'
        
        # Extract keyword from title (NOT booktitle)
        title_match = re.search(r'(?<!book)title\s*=\s*{([^}]+(?:{[^}]*}[^}]*)*)}', entry_content, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            keyword = extract_keyword_from_title(title)
        else:
            keyword = 'paper'
        
        # Clean and format the components
        lastname = re.sub(r'[^a-zA-Z]', '', lastname).lower()
        keyword = keyword.lower()
        
        # Create new key
        new_key = f"{lastname}{year}{keyword}"
        
        # Replace in content
        new_entry = f"{entry_type}{new_key}{entry_content}{closing}"
        content = content[:match.start()] + new_entry + content[match.end():]
        
        print(f"  {old_key} -> {new_key}")
    
    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return len(entries)


def main():
    """Process bibliography files."""
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        # Default files
        files = [
            'curated/distributed-graphics.bib',
            'curated/embodiment.bib',
            'curated/semantic-communication.bib',
            'curated/simulation.bib',
            'curated/visual-reasoning.bib'
        ]
    
    for filepath in files:
        path = Path(filepath)
        if path.exists():
            print(f"\nProcessing {filepath}:")
            count = update_bibtex_keys(path)
            print(f"  Updated {count} entries")
        else:
            print(f"File not found: {filepath}")


if __name__ == '__main__':
    main()