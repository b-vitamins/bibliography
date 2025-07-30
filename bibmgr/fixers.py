"""Fix operations for bibliography validation errors."""

from dataclasses import dataclass
from pathlib import Path

import bibtexparser  # type: ignore[import-untyped]
from bibtexparser.bwriter import BibTexWriter  # type: ignore[import-untyped]

from .models import BibEntry


@dataclass(frozen=True)
class Fix:
    """Represents a fix to be applied."""

    bib_file: Path
    entry_key: str
    fix_type: str
    description: str
    old_value: str | None = None
    new_value: str | None = None


def fix_duplicate_keys(entries: list[BibEntry]) -> list[Fix]:
    """Generate fixes for duplicate citation keys.

    Strategy: Append incrementing numbers to duplicate keys.
    """
    fixes = []
    seen_keys: dict[str, BibEntry] = {}
    key_counters: dict[str, int] = {}

    for entry in entries:
        if entry.key in seen_keys:
            # This is a duplicate
            if entry.key not in key_counters:
                key_counters[entry.key] = 2
            else:
                key_counters[entry.key] += 1

            new_key = f"{entry.key}_{key_counters[entry.key]}"

            fixes.append(Fix(
                bib_file=entry.source_file,
                entry_key=entry.key,
                fix_type="rename_key",
                description=f"Rename duplicate key to {new_key}",
                old_value=entry.key,
                new_value=new_key
            ))
        else:
            seen_keys[entry.key] = entry

    return fixes


def fix_missing_fields(entries: list[BibEntry]) -> list[Fix]:
    """Generate fixes for missing mandatory fields.

    Strategy: Add placeholder values for missing fields.
    """
    fixes = []

    # Special handling for technical standards
    for entry in entries:
        if (entry.entry_type.lower() == 'techreport' and
            'author' not in entry.fields and
            'institution' in entry.fields):
                fixes.append(Fix(
                    bib_file=entry.source_file,
                    entry_key=entry.key,
                    fix_type="add_field",
                    description="Add author field from institution",
                    new_value=entry.fields['institution']
                ))

    return fixes


def apply_fixes(fixes: list[Fix], dry_run: bool = True) -> dict[Path, int]:
    """Apply fixes to BibTeX files.

    Returns dict of {file_path: number_of_fixes_applied}
    """
    if dry_run:
        print("\n=== DRY RUN MODE - No files will be modified ===\n")

    # Group fixes by file
    fixes_by_file: dict[Path, list[Fix]] = {}
    for fix in fixes:
        if fix.bib_file not in fixes_by_file:
            fixes_by_file[fix.bib_file] = []
        fixes_by_file[fix.bib_file].append(fix)

    applied_counts = {}

    for bib_file, file_fixes in fixes_by_file.items():
        print(f"\nProcessing {bib_file}:")

        # Load the file
        with open(bib_file, encoding='utf-8') as f:
            bib_database = bibtexparser.load(f)

        applied = 0

        # Apply each fix
        for fix in file_fixes:
            if fix.fix_type == "rename_key":
                # Find the entry and rename it
                for entry in bib_database.entries:
                    if entry.get('ID') == fix.old_value:
                        print(f"  - Renaming key '{fix.old_value}' → '{fix.new_value}'")
                        entry['ID'] = fix.new_value
                        applied += 1
                        break

            elif fix.fix_type == "add_field":
                # Find the entry and add the field
                for entry in bib_database.entries:
                    if entry.get('ID') == fix.entry_key:
                        print(f"  - Adding author field to '{fix.entry_key}'")
                        entry['author'] = fix.new_value
                        applied += 1
                        break

        # Write back to file
        if not dry_run and applied > 0:
            writer = BibTexWriter()
            writer.indent = '  '

            with open(bib_file, 'w', encoding='utf-8') as f:
                f.write(writer.write(bib_database))

        applied_counts[bib_file] = applied

    return applied_counts
