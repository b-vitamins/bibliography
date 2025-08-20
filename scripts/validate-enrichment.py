#!/usr/bin/env python3
"""
Validate enriched BibTeX entries for quality and completeness.

Usage:
    validate-enrichment.py file.bib              # Validate all entries in file
    validate-enrichment.py file.bib entry_key    # Validate specific entry

Validation checks:
- Mandatory fields based on entry type
- OpenAlex ID format (W followed by numbers)
- PDF link accessibility (HEAD request)
- Abstract presence and length
- Common formatting issues
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode  # type: ignore[import-untyped]


# Mandatory fields by entry type
MANDATORY_FIELDS = {
    "article": ["author", "title", "journal", "year"],
    "inproceedings": ["author", "title", "booktitle", "year"],
    "book": ["author", "title", "publisher", "year"],
    "phdthesis": ["author", "title", "school", "year"],
    "mastersthesis": ["author", "title", "school", "year"],
    "techreport": ["author", "title", "institution", "year"],
    "misc": ["title", "year"],
    "unpublished": ["author", "title", "note"],
    "incollection": ["author", "title", "booktitle", "publisher", "year"],
    "inbook": ["author", "title", "pages", "publisher", "year"],
}

# Fields that should be present in enriched entries
ENRICHMENT_FIELDS = ["openalex", "pdf", "abstract"]


class ValidationResult:
    """Store validation results for an entry."""

    def __init__(self, entry_key: str, entry_type: str):
        self.entry_key = entry_key
        self.entry_type = entry_type
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.warnings: list[str] = []
        self.openalex_id: str | None = None

    @property
    def status(self) -> str:
        """Get overall validation status."""
        if self.failed:
            return "failed"
        elif self.warnings:
            return "warning"
        return "passed"

    def report(self) -> str:
        """Generate validation report."""
        lines = [f"\n{'=' * 60}", f"Entry: {self.entry_key} ({self.entry_type})"]

        if self.passed:
            lines.append("\n✓ Passed checks:")
            for check in self.passed:
                lines.append(f"  - {check}")

        if self.warnings:
            lines.append("\n⚠ Warnings:")
            for warning in self.warnings:
                lines.append(f"  - {warning}")

        if self.failed:
            lines.append("\n✗ Failed checks:")
            for failure in self.failed:
                lines.append(f"  - {failure}")

        lines.append(f"\nOverall Status: {self.status.upper()}")
        return "\n".join(lines)


def check_mandatory_fields(entry: dict[str, Any], result: ValidationResult) -> None:
    """Check if all mandatory fields are present."""
    entry_type = entry.get("ENTRYTYPE", "").lower()
    mandatory = MANDATORY_FIELDS.get(entry_type, [])

    for field in mandatory:
        if field in entry and entry[field].strip():
            result.passed.append(f"Mandatory field '{field}' present")
        else:
            result.failed.append(f"Missing mandatory field '{field}'")


def check_openalex_id(entry: dict[str, Any], result: ValidationResult) -> None:
    """Validate OpenAlex ID format."""
    openalex_id = entry.get("openalex", "").strip()

    if not openalex_id:
        result.failed.append("Missing OpenAlex ID")
        return

    if re.match(r"^W\d+$", openalex_id):
        result.passed.append(f"Valid OpenAlex ID format: {openalex_id}")
        result.openalex_id = openalex_id
    else:
        result.failed.append(
            f"Invalid OpenAlex ID format: {openalex_id} (expected W followed by numbers)"
        )


def check_pdf_link(entry: dict[str, Any], result: ValidationResult) -> None:
    """Check PDF link validity and accessibility."""
    pdf_url = entry.get("pdf", "").strip()

    if not pdf_url:
        result.warnings.append("No PDF link provided")
        return

    # Validate URL format
    try:
        parsed = urlparse(pdf_url)
        if not parsed.scheme or not parsed.netloc:
            result.failed.append(f"Invalid PDF URL format: {pdf_url}")
            return
    except Exception:
        result.failed.append(f"Malformed PDF URL: {pdf_url}")
        return

    # Check accessibility with HEAD request
    try:
        req = Request(pdf_url, method="HEAD")
        req.add_header("User-Agent", "BibTeX-Validator/1.0")

        with urlopen(req, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "").lower()

            if response.status == 200:
                if "pdf" in content_type or pdf_url.endswith(".pdf"):
                    result.passed.append(f"PDF link accessible: {pdf_url}")
                else:
                    result.warnings.append(
                        f"PDF link accessible but unexpected content type: {content_type}"
                    )
            else:
                result.warnings.append(f"PDF link returned status {response.status}")

    except HTTPError as e:
        if e.code == 403:
            result.warnings.append(f"PDF link requires authentication (403): {pdf_url}")
        elif e.code == 404:
            result.failed.append(f"PDF link not found (404): {pdf_url}")
        else:
            result.warnings.append(f"PDF link HTTP error {e.code}: {pdf_url}")
    except URLError as e:
        result.warnings.append(f"Cannot verify PDF link (network error): {str(e)}")
    except Exception as e:
        result.warnings.append(f"Cannot verify PDF link: {str(e)}")


def check_abstract(entry: dict[str, Any], result: ValidationResult) -> None:
    """Check abstract presence and quality."""
    abstract = entry.get("abstract", "").strip()

    if not abstract:
        # Some entry types don't require abstracts
        if entry.get("ENTRYTYPE", "").lower() in ["book", "misc"]:
            result.warnings.append("No abstract (optional for this entry type)")
        else:
            result.failed.append("Missing abstract")
        return

    # Check length
    word_count = len(abstract.split())
    if word_count < 50:
        result.warnings.append(f"Abstract seems too short ({word_count} words)")
    elif word_count > 1000:
        result.warnings.append(f"Abstract seems too long ({word_count} words)")
    else:
        result.passed.append(f"Abstract present ({word_count} words)")

    # Check for common issues
    if abstract.startswith('"') and abstract.endswith('"'):
        result.warnings.append("Abstract has surrounding quotes")

    if "..." in abstract or abstract.endswith("..."):
        result.warnings.append("Abstract appears truncated")


def check_formatting(entry: dict[str, Any], result: ValidationResult) -> None:
    """Check common formatting issues."""
    # Title capitalization
    title = entry.get("title", "")
    if title:
        # Check for all caps
        if title.isupper():
            result.warnings.append("Title is in all caps")
        # Check for proper brace protection
        elif not re.search(r"\{[^}]+\}", title) and any(
            word[0].isupper()
            for word in title.split()[1:]
            if word
            not in [
                "a",
                "an",
                "the",
                "of",
                "in",
                "on",
                "at",
                "to",
                "for",
                "and",
                "or",
                "but",
            ]
        ):
            result.warnings.append(
                "Title may need brace protection for capitalized words"
            )

    # Author format
    authors = entry.get("author", "")
    if authors:
        # Check for "and" separator
        if ";" in authors:
            result.warnings.append("Authors should be separated by 'and' not semicolon")

        # Check for first name abbreviations
        author_parts = authors.replace(" and ", "|").split("|")
        abbreviated = [
            a.strip() for a in author_parts if re.search(r"\b[A-Z]\.", a.strip())
        ]
        if abbreviated and len(abbreviated) == len(author_parts):
            result.warnings.append("All authors use abbreviated first names")

    # Page ranges
    pages = entry.get("pages", "")
    if pages:
        if "--" not in pages and "-" in pages and not pages.replace("-", "").isdigit():
            result.warnings.append("Page range should use -- not single dash")
        elif not re.match(r"^\d+(-+\d+)?$", pages.replace(" ", "")):
            result.warnings.append(f"Unusual page format: {pages}")

    # Year format
    year = entry.get("year", "")
    if year:
        if not re.match(r"^\d{4}$", year):
            result.warnings.append(f"Year should be 4 digits: {year}")

    # URL format
    url = entry.get("url", "")
    if url:
        if not url.startswith(("http://", "https://")):
            result.warnings.append(f"URL should start with http:// or https://: {url}")


def validate_entry(entry: dict[str, Any]) -> ValidationResult:
    """Validate a single BibTeX entry."""
    entry_key = entry.get("ID", "unknown")
    entry_type = entry.get("ENTRYTYPE", "unknown").lower()

    result = ValidationResult(entry_key, entry_type)

    # Run all validation checks
    check_mandatory_fields(entry, result)
    check_openalex_id(entry, result)
    check_pdf_link(entry, result)
    check_abstract(entry, result)
    check_formatting(entry, result)

    return result


def update_tracking_database(
    file_path: str, results: list[ValidationResult], db_path: str = "bibliography.db"
) -> None:
    """Update tracking database with validation results using atomic transaction."""
    # Skip if database doesn't exist
    if not Path(db_path).exists():
        print("\n⚠ No tracking database found, skipping database update")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Start transaction explicitly
        conn.execute("BEGIN TRANSACTION")

        # Check if validation columns exist, add if not
        cursor.execute("PRAGMA table_info(enrichment_log)")
        columns = [col[1] for col in cursor.fetchall()]

        if "validation_status" not in columns:
            print("\n📊 Adding validation columns to tracking database...")
            cursor.execute("""
                ALTER TABLE enrichment_log 
                ADD COLUMN validation_status TEXT 
                CHECK(validation_status IN ('passed', 'warning', 'failed'))
            """)
            cursor.execute("""
                ALTER TABLE enrichment_log 
                ADD COLUMN validation_timestamp DATETIME
            """)
            cursor.execute("""
                ALTER TABLE enrichment_log 
                ADD COLUMN validation_details TEXT
            """)

        # Update validation status for each result
        updates_made = 0
        for result in results:
            details = {
                "passed": len(result.passed),
                "warnings": len(result.warnings),
                "failed": len(result.failed),
                "checks": result.passed + result.warnings + result.failed,
            }

            cursor.execute(
                """
                UPDATE enrichment_log
                SET validation_status = ?,
                    validation_timestamp = CURRENT_TIMESTAMP,
                    validation_details = ?
                WHERE file_path = ? 
                  AND entry_key = ?
                  AND timestamp = (
                      SELECT MAX(timestamp)
                      FROM enrichment_log e2
                      WHERE e2.file_path = enrichment_log.file_path
                        AND e2.entry_key = enrichment_log.entry_key
                  )
            """,
                (result.status, str(details), file_path, result.entry_key),
            )

            if cursor.rowcount > 0:
                updates_made += 1

        # Commit only if all updates succeeded
        conn.commit()
        print(
            f"\n✓ Updated validation status for {updates_made} entries in tracking database"
        )

    except Exception as e:
        # Rollback transaction on any error
        conn.rollback()
        print(f"\n✗ Error updating database: {e}", file=sys.stderr)
        print("✗ Transaction rolled back - database unchanged", file=sys.stderr)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate enriched BibTeX entries for quality and completeness"
    )
    parser.add_argument("file", help="BibTeX file to validate")
    parser.add_argument("entry_key", nargs="?", help="Specific entry key to validate")
    parser.add_argument(
        "--no-pdf-check", action="store_true", help="Skip PDF accessibility checks"
    )
    parser.add_argument(
        "--no-db-update", action="store_true", help="Skip updating tracking database"
    )
    parser.add_argument(
        "--summary", action="store_true", help="Show only summary statistics"
    )

    args = parser.parse_args()

    # Check file exists
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File {file_path} does not exist", file=sys.stderr)
        sys.exit(1)

    # Parse BibTeX file
    try:
        parser_obj = BibTexParser(common_strings=True)
        parser_obj.customization = convert_to_unicode  # type: ignore[attr-defined]
        parser_obj.ignore_nonstandard_types = False  # type: ignore[attr-defined]

        with open(file_path, "r", encoding="utf-8") as f:
            bib_db = bibtexparser.load(f, parser=parser_obj)  # type: ignore[no-untyped-call]
    except Exception as e:
        print(f"Error parsing BibTeX file: {e}", file=sys.stderr)
        sys.exit(1)

    # Filter entries if specific key requested
    if args.entry_key:
        entries = [e for e in bib_db.entries if e.get("ID") == args.entry_key]  # type: ignore[arg-type]
        if not entries:
            print(
                f"Error: Entry '{args.entry_key}' not found in {file_path}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        entries = bib_db.entries  # type: ignore[assignment]

    # Validate entries
    results: list[ValidationResult] = []

    print(f"\n🔍 Validating {len(entries)} entries from {file_path}")
    if args.no_pdf_check:
        print("   (Skipping PDF accessibility checks)")

    for entry in entries:
        # Skip PDF check if requested
        original_pdf = None
        if args.no_pdf_check:
            original_pdf = entry.get("pdf")
            if original_pdf:
                entry["pdf"] = ""  # Temporarily remove to skip check

        result = validate_entry(entry)
        results.append(result)

        # Restore PDF field
        if args.no_pdf_check and original_pdf:
            entry["pdf"] = original_pdf

        # Show individual results unless summary mode
        if not args.summary:
            print(result.report())

    # Summary statistics
    passed = sum(1 for r in results if r.status == "passed")
    warnings = sum(1 for r in results if r.status == "warning")
    failed = sum(1 for r in results if r.status == "failed")

    print(f"\n{'=' * 60}")
    print(f"VALIDATION SUMMARY for {file_path.name}")
    print(f"{'=' * 60}")
    print(f"Total entries validated: {len(results)}")
    print(f"✓ Passed: {passed} ({passed / len(results) * 100:.1f}%)")
    print(f"⚠ Warnings: {warnings} ({warnings / len(results) * 100:.1f}%)")
    print(f"✗ Failed: {failed} ({failed / len(results) * 100:.1f}%)")

    # Update tracking database
    if not args.no_db_update:
        update_tracking_database(str(file_path), results)

    # Exit with error if any failures
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
