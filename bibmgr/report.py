"""Generate detailed validation reports with context."""

from collections import defaultdict
from pathlib import Path

from .models import BibEntry, ValidationError
from .validators import check_duplicates, check_mandatory_fields, check_paths


def format_entry_context(entry: BibEntry) -> str:
    """Format a BibTeX entry with relevant fields for context."""
    lines = [f"@{entry.entry_type}{{{entry.key},"]

    # Show key fields first
    key_fields = [
        "author",
        "title",
        "year",
        "journal",
        "booktitle",
        "school",
        "institution",
    ]
    for field in key_fields:
        if field in entry.fields:
            lines.append(f"  {field} = {{{entry.fields[field]}}},")

    # Show file path if present
    if entry.file_path:
        lines.append(f"  file = {{:{entry.file_path}:pdf}},")

    # Show other fields
    for field, value in entry.fields.items():
        if field not in key_fields and field != "file":
            lines.append(f"  {field} = {{{value}}},")

    lines.append("}")
    return "\n".join(lines)


def report_duplicate_keys(entries: list[BibEntry]) -> str:
    """Generate detailed report of duplicate keys."""
    errors = check_duplicates(entries)
    if not errors:
        return "No duplicate keys found."

    # Group by duplicate key
    duplicates_by_key: dict[str, list[BibEntry]] = defaultdict(list)
    for entry in entries:
        # Find all entries that have been flagged as duplicates
        if any(
            e.entry_key == entry.key and e.error_type == "duplicate_key" for e in errors
        ):
            duplicates_by_key[entry.key].append(entry)

    report_lines = [f"Found {len(errors)} duplicate key(s):\n"]

    for key, dup_entries in duplicates_by_key.items():
        report_lines.append(f"\n{'=' * 60}")
        report_lines.append(f"Duplicate key: {key} (found in {len(dup_entries)} files)")
        report_lines.append("=" * 60)

        for i, entry in enumerate(dup_entries, 1):
            report_lines.append(f"\n--- Entry {i} from {entry.source_file} ---")
            report_lines.append(format_entry_context(entry))

    return "\n".join(report_lines)


def report_missing_fields(entries: list[BibEntry]) -> str:
    """Generate detailed report of missing mandatory fields."""
    errors = check_mandatory_fields(entries)
    if not errors:
        return "No missing mandatory fields found."

    # Group by error type
    errors_by_file: dict[Path, list[ValidationError]] = defaultdict(list)
    for error in errors:
        errors_by_file[error.bib_file].append(error)

    report_lines = [f"Found {len(errors)} missing field issue(s):\n"]

    for bib_file, file_errors in errors_by_file.items():
        report_lines.append(f"\n{'=' * 60}")
        report_lines.append(f"File: {bib_file}")
        report_lines.append("=" * 60)

        # Get all entries from this file for context
        file_entries = [e for e in entries if e.source_file == bib_file]

        for error in file_errors:
            # Find the entry
            entry = next((e for e in file_entries if e.key == error.entry_key), None)
            if entry:
                report_lines.append(f"\n--- {error.entry_key}: {error.message} ---")
                report_lines.append(format_entry_context(entry))

                # Suggest fixes based on entry type
                if (
                    entry.entry_type.lower() == "techreport"
                    and "author" in error.message
                    and "institution" in entry.fields
                ):
                    report_lines.append(
                        f"\nSuggestion: Consider using institution as author: "
                        f"{entry.fields['institution']}"
                    )

    return "\n".join(report_lines)


def report_missing_files(entries: list[BibEntry]) -> str:
    """Generate detailed report of missing files."""
    errors = check_paths(entries)
    if not errors:
        return "All file paths are valid."

    report_lines = [f"Found {len(errors)} missing file(s):\n"]

    for error in errors:
        entry = next((e for e in entries if e.key == error.entry_key), None)
        if entry:
            report_lines.append(f"\n--- {error.entry_key} ---")
            report_lines.append(f"Missing file: {error.file_path}")
            report_lines.append(f"Entry type: @{entry.entry_type}")
            if "title" in entry.fields:
                report_lines.append(f"Title: {entry.fields['title']}")
            if "author" in entry.fields:
                report_lines.append(f"Author: {entry.fields['author']}")

    return "\n".join(report_lines)


def generate_full_report(entries: list[BibEntry]) -> str:
    """Generate a comprehensive validation report."""
    sections = []

    # Header
    sections.append("BIBLIOGRAPHY VALIDATION REPORT")
    sections.append("=" * 60)
    sections.append(f"Total entries: {len(entries)}")

    # Check each validation type
    path_errors = check_paths(entries)
    dup_errors = check_duplicates(entries)
    field_errors = check_mandatory_fields(entries)

    total_errors = len(path_errors) + len(dup_errors) + len(field_errors)
    sections.append(f"Total issues: {total_errors}")
    sections.append("")

    # Missing files section
    sections.append("\n1. MISSING FILES")
    sections.append("-" * 60)
    sections.append(report_missing_files(entries))

    # Duplicate keys section
    sections.append("\n\n2. DUPLICATE KEYS")
    sections.append("-" * 60)
    sections.append(report_duplicate_keys(entries))

    # Missing fields section
    sections.append("\n\n3. MISSING MANDATORY FIELDS")
    sections.append("-" * 60)
    sections.append(report_missing_fields(entries))

    return "\n".join(sections)
