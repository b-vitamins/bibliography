"""Validation functions for bibliography entries."""

from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

import bibtexparser  # type: ignore[import-untyped]

from .models import BibEntry, ValidationError

# Mandatory fields per entry type (based on DESIGN.md)
MANDATORY_FIELDS: dict[str, set[str]] = {
    'article': {'author', 'title', 'journal', 'year'},
    'book': {'title', 'publisher', 'year'},  # author OR editor required
    'booklet': {'title'},
    'conference': {'author', 'title', 'booktitle', 'year'},
    'inbook': {'title', 'publisher', 'year'},  # author/editor & chapter/pages required
    'incollection': {'author', 'title', 'booktitle', 'publisher', 'year'},
    'inproceedings': {'author', 'title', 'booktitle', 'year'},
    'manual': {'title'},
    'mastersthesis': {'author', 'title', 'school', 'year'},
    'misc': set(),  # No mandatory fields
    'phdthesis': {'author', 'title', 'school', 'year'},
    'proceedings': {'title', 'year'},
    'techreport': {'author', 'title', 'institution', 'year'},
    'unpublished': {'author', 'title', 'note'},
}


def load_bibliography(bib_path: Path) -> Iterator[BibEntry]:
    """Load bibliography entries from a .bib file."""
    try:
        with open(bib_path, encoding='utf-8') as f:
            bib_database = bibtexparser.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse {bib_path}: {e}") from e

    for entry in bib_database.entries:
        # Create fields dict excluding ID and ENTRYTYPE
        fields = {k: v for k, v in entry.items()
                  if k not in ['ID', 'ENTRYTYPE']}

        yield BibEntry(
            key=entry.get('ID', ''),
            entry_type=entry.get('ENTRYTYPE', ''),
            fields=fields,
            source_file=bib_path
        )


def check_paths(entries: list[BibEntry]) -> list[ValidationError]:
    """Check that all file paths exist."""
    errors = []

    for entry in entries:
        file_path = entry.file_path
        if file_path and not file_path.exists():
            errors.append(ValidationError(
                bib_file=entry.source_file,
                entry_key=entry.key,
                error_type="missing_file",
                message="File not found",
                file_path=file_path
            ))

    return errors


def check_duplicates(entries: list[BibEntry]) -> list[ValidationError]:
    """Check for duplicate citation keys and file paths."""
    errors = []

    # Check duplicate keys
    key_locations: dict[str, list[BibEntry]] = defaultdict(list)
    for entry in entries:
        key_locations[entry.key].append(entry)

    for _key, locations in key_locations.items():
        if len(locations) > 1:
            for entry in locations[1:]:  # Skip first occurrence
                errors.append(ValidationError(
                    bib_file=entry.source_file,
                    entry_key=entry.key,
                    error_type="duplicate_key",
                    message=f"Duplicate key (first in {locations[0].source_file.name})"
                ))

    # Check duplicate file paths
    path_locations: dict[Path, list[BibEntry]] = defaultdict(list)
    for entry in entries:
        if entry.file_path:
            path_locations[entry.file_path].append(entry)

    for path, locations in path_locations.items():
        if len(locations) > 1:
            for entry in locations[1:]:  # Skip first occurrence
                errors.append(ValidationError(
                    bib_file=entry.source_file,
                    entry_key=entry.key,
                    error_type="duplicate_path",
                    message=f"Duplicate file path (first in {locations[0].key})",
                    file_path=path
                ))

    return errors


def check_mandatory_fields(entries: list[BibEntry]) -> list[ValidationError]:
    """Check that all mandatory fields are present."""
    errors = []

    for entry in entries:
        entry_type = entry.entry_type.lower()
        if entry_type not in MANDATORY_FIELDS:
            errors.append(ValidationError(
                bib_file=entry.source_file,
                entry_key=entry.key,
                error_type="unknown_type",
                message=f"Unknown entry type: {entry.entry_type}"
            ))
            continue

        required = MANDATORY_FIELDS[entry_type].copy()

        # Special handling for author/editor fields
        if entry_type in ['book', 'inbook']:
            if 'author' in entry.fields or 'editor' in entry.fields:
                required.discard('author')
                required.discard('editor')
            else:
                required.add('author/editor')

        # Special handling for chapter/pages in inbook
        if entry_type == 'inbook':
            if 'chapter' in entry.fields or 'pages' in entry.fields:
                required.discard('chapter')
                required.discard('pages')
            else:
                required.add('chapter/pages')

        # Check missing fields
        missing = required - set(entry.fields.keys())
        if missing:
            errors.append(ValidationError(
                bib_file=entry.source_file,
                entry_key=entry.key,
                error_type="missing_fields",
                message=f"Missing mandatory fields: {', '.join(sorted(missing))}"
            ))

    return errors
