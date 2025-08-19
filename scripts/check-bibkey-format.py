#!/usr/bin/env python3
"""
Check BibTeX entries for standardized bibkey format: <authorlastname><year><keyword>

Expected format:
- authorlastname: lowercase, no spaces or special characters
- year: 4 digits
- keyword: lowercase, descriptive word from title/content
- Examples: smith2023transformer, doe2024attention, johnson2022mamba

Reports violations for manual review and fixing.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict
import bibtexparser
from bibtexparser.bparser import BibTexParser


def extract_entry_info(entry: dict) -> Dict[str, str]:
    """Extract relevant information from entry for analysis."""
    info = {
        'key': entry.get('ID', ''),
        'type': entry.get('ENTRYTYPE', ''),
        'author': entry.get('author', ''),
        'year': entry.get('year', ''),
        'title': entry.get('title', '')
    }
    return info


def check_bibkey_format(bibkey: str) -> Tuple[bool, List[str]]:
    """
    Check if bibkey follows the standard format.
    Returns (is_valid, list_of_issues)
    """
    issues = []
    
    # Check if entirely lowercase
    if bibkey != bibkey.lower():
        issues.append("contains uppercase letters")
    
    # Check basic pattern: authorname + year + keyword
    # More flexible pattern to catch various formats
    pattern = r'^([a-z]+)(\d{4})([a-z]+)$'
    match = re.match(pattern, bibkey.lower())
    
    if not match:
        # Try to identify specific issues
        if re.search(r'[_\-\.]', bibkey):
            issues.append("contains special characters (_, -, .)")
        if re.search(r'\s', bibkey):
            issues.append("contains spaces")
        if re.search(r'[A-Z]', bibkey) and bibkey not in ['BID', 'ID']:  # Common parser artifacts
            issues.append("mixed case detected")
        
        # Check if year is present
        year_match = re.search(r'\d{4}', bibkey)
        if not year_match:
            issues.append("missing 4-digit year")
        elif not re.search(r'[a-z]+\d{4}', bibkey.lower()):
            issues.append("year not properly positioned after author")
        
        # Check structure
        if not re.search(r'^[a-zA-Z]', bibkey):
            issues.append("doesn't start with author name")
        
        if year_match and not re.search(r'\d{4}[a-zA-Z]+', bibkey):
            issues.append("missing keyword after year")
    else:
        # Even if pattern matches, check for quality
        author_part, year_part, keyword_part = match.groups()
        
        if len(author_part) < 2:
            issues.append("author name too short (less than 2 chars)")
        if len(keyword_part) < 3:
            issues.append("keyword too short or non-descriptive")
        
        # Check if keyword seems generic
        generic_keywords = ['paper', 'article', 'work', 'study', 'research', 'book', 'thesis']
        if keyword_part in generic_keywords:
            issues.append(f"keyword '{keyword_part}' is too generic")
    
    return (len(issues) == 0, issues)


def suggest_fixes(entry_info: Dict[str, str], current_key: str) -> List[str]:
    """Suggest possible corrections for the bibkey."""
    suggestions = []
    
    # Extract author last name
    author = entry_info['author']
    year = entry_info['year']
    title = entry_info['title']
    
    if author and year:
        # Try to extract first author's last name
        # Handle various author formats
        if ' and ' in author:
            first_author = author.split(' and ')[0].strip()
        else:
            first_author = author.strip()
        
        # Extract last name (handle "Last, First" and "First Last" formats)
        if ',' in first_author:
            last_name = first_author.split(',')[0].strip()
        else:
            parts = first_author.split()
            if parts:
                last_name = parts[-1]
            else:
                last_name = first_author
        
        # Clean last name
        last_name = re.sub(r'[^a-zA-Z]', '', last_name).lower()
        
        if last_name and len(last_name) >= 3:
            # Extract potential keywords from title
            if title:
                # Remove common words and extract significant terms
                title_lower = title.lower()
                # Remove special characters and split
                words = re.findall(r'\b[a-z]+\b', title_lower)
                
                # Filter significant words (length > 4, not common words)
                common_words = {'this', 'that', 'with', 'from', 'have', 'been', 
                              'were', 'their', 'other', 'some', 'would', 'there',
                              'which', 'about', 'after', 'through', 'could', 'while'}
                keywords = [w for w in words if len(w) > 4 and w not in common_words]
                
                # Suggest top 3 keywords
                for kw in keywords[:3]:
                    suggested_key = f"{last_name}{year}{kw}"
                    if suggested_key != current_key.lower():
                        suggestions.append(suggested_key)
    
    return suggestions


def check_file(filepath: Path) -> List[Tuple[str, Dict[str, str], List[str], List[str]]]:
    """
    Check a single .bib file for bibkey format violations.
    Returns list of (bibkey, entry_info, issues, suggestions).
    """
    violations = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse BibTeX
        parser = BibTexParser()
        parser.ignore_nonstandard_types = False
        parser.homogenize_fields = False
        bib_db = bibtexparser.loads(content, parser)
        
        for entry in bib_db.entries:
            bibkey = entry.get('ID', '')
            if not bibkey:
                continue
            
            is_valid, issues = check_bibkey_format(bibkey)
            
            if not is_valid:
                entry_info = extract_entry_info(entry)
                suggestions = suggest_fixes(entry_info, bibkey)
                violations.append((bibkey, entry_info, issues, suggestions))
    
    except Exception as e:
        print(f"✗ Error processing {filepath}: {e}")
        return []
    
    return violations


def main():
    """Main function to check bibkey format violations."""
    if len(sys.argv) < 2:
        print("Usage: python3 check-bibkey-format.py <file1.bib> [file2.bib ...]")
        print("\nChecks BibTeX entries for standardized key format:")
        print("  <authorlastname><year><keyword> (all lowercase)")
        print("\nExample: smith2023transformer")
        sys.exit(1)
    
    total_files = 0
    total_entries = 0
    total_violations = 0
    all_violations = []
    
    for filepath in sys.argv[1:]:
        path = Path(filepath)
        if not path.exists():
            print(f"✗ File not found: {filepath}")
            continue
        
        if not path.suffix == '.bib':
            print(f"✗ Not a .bib file: {filepath}")
            continue
        
        violations = check_file(path)
        total_files += 1
        
        if violations:
            all_violations.append((path, violations))
            total_violations += len(violations)
        
        # Count total entries
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            parser = BibTexParser()
            parser.ignore_nonstandard_types = False
            bib_db = bibtexparser.loads(content, parser)
            total_entries += len(bib_db.entries)
        except:
            pass
    
    # Report results
    if all_violations:
        print(f"\nBibkey Format Violations Found: {total_violations}")
        print("=" * 80)
        
        for filepath, violations in all_violations:
            print(f"\n{filepath}: {len(violations)} violations")
            print("-" * 80)
            
            for bibkey, entry_info, issues, suggestions in violations:
                print(f"\n  ❌ {bibkey}")
                print(f"     Type: {entry_info['type']}")
                if entry_info['author']:
                    print(f"     Author: {entry_info['author'][:50]}...")
                if entry_info['year']:
                    print(f"     Year: {entry_info['year']}")
                if entry_info['title']:
                    print(f"     Title: {entry_info['title'][:60]}...")
                
                print(f"     Issues: {', '.join(issues)}")
                
                if suggestions:
                    print(f"     Suggested keys: {', '.join(suggestions)}")
    else:
        print(f"\n✓ All bibkeys follow the standard format!")
    
    # Summary
    print(f"\n{'=' * 80}")
    print(f"Summary:")
    print(f"  Files checked: {total_files}")
    print(f"  Total entries: {total_entries}")
    print(f"  Valid entries: {total_entries - total_violations}")
    print(f"  Violations: {total_violations} ({total_violations/total_entries*100:.1f}%)")
    
    # Exit with error code if violations found
    sys.exit(1 if total_violations > 0 else 0)


if __name__ == "__main__":
    main()