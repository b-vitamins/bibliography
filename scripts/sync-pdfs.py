#!/usr/bin/env python3
"""
Synchronize PDFs for BibTeX entries.

This script:
1. Downloads PDFs from 'pdf' field URLs
2. Places them in /home/b/documents/{entry_type}/
3. Names files as {bibkey}.pdf
4. Adds/updates 'file' field with local path
5. Fixes misnamed files and removes dead links
"""

import argparse
import os
import sys
import shutil
import requests
import tempfile
import re
from pathlib import Path
from typing import Optional, Tuple, Any
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
# from bibtexparser.customization import convert_to_unicode

# Base directory for all PDFs
BASE_DIR = Path("/home/b/documents")

# Mapping of BibTeX entry types to subdirectories
TYPE_TO_DIR = {
    "article": "article",
    "inproceedings": "inproceedings",
    "phdthesis": "phdthesis",
    "mastersthesis": "mastersthesis",
    "book": "book",
    "incollection": "incollection",
    "inbook": "inbook",
    "proceedings": "proceedings",
    "techreport": "techreport",
    "unpublished": "unpublished",
    "misc": "misc",
    "online": "online",
    "manual": "manual",
    "booklet": "booklet",
    "conference": "conference",
    "phdproposal": "phdproposal",
    "masterthesis": "mastersthesis",  # Alternative spelling
}


def parse_file_field(field_value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Parse a file field to extract path and type."""
    if not field_value:
        return None, None

    # Format: :/path/to/file.ext:type
    match = re.match(r"^:(.+):(\w+)$", field_value)
    if match:
        return match.group(1), match.group(2)
    return None, None


def format_file_field(path: str, file_type: str = "pdf") -> str:
    """Format a file path for the file field."""
    return f":{path}:{file_type}"


def get_target_path(entry: dict[str, Any]) -> Path:
    """Get the target path for a PDF based on entry type and key."""
    entry_type = entry.get("ENTRYTYPE", "misc").lower()
    subdir = TYPE_TO_DIR.get(entry_type, "misc")
    target_dir = BASE_DIR / subdir

    # Create directory if it doesn't exist
    target_dir.mkdir(parents=True, exist_ok=True)

    # Use bibkey as filename
    bibkey = entry.get("ID", "unknown")
    return target_dir / f"{bibkey}.pdf"


def verify_pdf(file_path: Path | str) -> Tuple[bool, str]:
    """Verify that a file is a valid PDF with content."""
    try:
        with open(file_path, "rb") as f:
            # Check PDF header
            header = f.read(5)
            if header != b"%PDF-":
                return False, "Not a PDF file (invalid header)"

            # Check file size (at least 1KB)
            f.seek(0, 2)  # Seek to end
            size = f.tell()
            if size < 1024:
                return False, f"File too small ({size} bytes)"

            # Check for EOF marker
            f.seek(-1024, 2)  # Last 1KB
            tail = f.read()
            if b"%%EOF" not in tail:
                return False, "Missing PDF EOF marker"

            return True, "Valid PDF"
    except Exception as e:
        return False, f"Verification error: {e}"


def download_pdf(
    url: str, target_path: Path, timeout: int = 30, max_retries: int = 3
) -> bool:
    """Download a PDF from URL to target path with retries and verification."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"  Retry attempt {attempt + 1}/{max_retries}")
                # Exponential backoff
                import time

                time.sleep(2**attempt)

            print(f"  Downloading from: {url}")

            # Make request with streaming
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                stream=True,
                allow_redirects=True,
                verify=True,
            )
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            content_length = response.headers.get("content-length")

            if content_length:
                size_mb = int(content_length) / (1024 * 1024)
                if size_mb > 100:
                    print(f"  WARNING: Large file ({size_mb:.1f} MB)")
                    if size_mb > 500:
                        print(f"  ERROR: File too large ({size_mb:.1f} MB), skipping")
                        return False

            # Warn about suspicious content types
            if "html" in content_type:
                print("  WARNING: Content-Type is HTML, likely a landing page")
                return False
            elif "pdf" not in content_type and not url.lower().endswith(".pdf"):
                print(f"  WARNING: Content-Type is {content_type}, may not be PDF")

            # Download to temp file with progress indication
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                downloaded = 0
                chunk_size = 8192

                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:  # Filter out keep-alive chunks
                        tmp.write(chunk)
                        downloaded += len(chunk)

                        # Progress indicator every 10MB
                        if downloaded % (10 * 1024 * 1024) == 0:
                            print(
                                f"    Downloaded {downloaded / (1024 * 1024):.1f} MB..."
                            )

                temp_path = tmp.name
                final_size = downloaded

            # Verify the downloaded file
            is_valid, message = verify_pdf(temp_path)

            if not is_valid:
                print(f"  ERROR: Invalid PDF - {message}")
                os.unlink(temp_path)

                # Check if we got an HTML error page
                with open(temp_path, "rb") as f:
                    content_start = f.read(1000)
                    if b"<!DOCTYPE" in content_start or b"<html" in content_start:
                        print(
                            "  ERROR: Downloaded HTML instead of PDF (likely paywall/login page)"
                        )
                        return False

                continue  # Retry

            # Move to target location
            shutil.move(temp_path, target_path)
            print(f"  Success: Saved {final_size / 1024:.1f} KB to {target_path}")
            return True

        except requests.exceptions.Timeout:
            print(f"  ERROR: Download timeout (attempt {attempt + 1}/{max_retries})")
        except requests.exceptions.ConnectionError as e:
            print(
                f"  ERROR: Connection failed - {e} (attempt {attempt + 1}/{max_retries})"
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print("  ERROR: File not found (404)")
                return False  # Don't retry 404s
            elif e.response.status_code == 403:
                print("  ERROR: Access forbidden (403) - may need authentication")
                return False  # Don't retry 403s
            else:
                print(
                    f"  ERROR: HTTP {e.response.status_code} (attempt {attempt + 1}/{max_retries})"
                )
        except Exception as e:
            print(f"  ERROR: {e} (attempt {attempt + 1}/{max_retries})")
            # Clean up temp file if it exists
            temp_path_var = locals().get("temp_path")
            if temp_path_var is not None and os.path.exists(temp_path_var):
                os.unlink(temp_path_var)

    print(f"  Failed after {max_retries} attempts")
    return False


def fix_existing_file(
    entry: dict[str, Any], current_path: str, file_type: str
) -> Optional[str]:
    """Fix an existing file entry (rename if needed, verify it exists)."""
    current_path_obj = Path(current_path)
    target_path = get_target_path(entry)

    if not current_path_obj.exists():
        print(f"  Dead link removed: {current_path_obj}")
        return None

    if current_path_obj != target_path:
        # File exists but wrong name/location
        print(f"  Moving {current_path_obj} -> {target_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(current_path_obj), str(target_path))
        return str(target_path)

    # File is in correct location
    return str(current_path_obj)


def process_entry(
    entry: dict[str, Any], download: bool = True, fix_existing: bool = True
) -> bool:
    """Process a single BibTeX entry."""
    bibkey = entry.get("ID", "unknown")
    entry_type = entry.get("ENTRYTYPE", "misc")
    print(f"\nProcessing {bibkey} ({entry_type}):")

    modified = False

    # Check for existing file field
    if "file" in entry and fix_existing:
        current_path, file_type = parse_file_field(entry["file"])
        if current_path:
            new_path = fix_existing_file(entry, current_path, file_type or "pdf")
            if new_path:
                entry["file"] = format_file_field(new_path, file_type or "pdf")
                modified = True
            else:
                # Dead link, remove field
                del entry["file"]
                modified = True

    # Check for pdf field to download
    if "pdf" in entry and download and "file" not in entry:
        pdf_url = entry["pdf"].strip()
        if pdf_url:
            target_path = get_target_path(entry)

            # Skip if file already exists
            if target_path.exists():
                print(f"  File already exists: {target_path}")
                entry["file"] = format_file_field(str(target_path), "pdf")
                modified = True
            else:
                # Download the PDF
                if download_pdf(pdf_url, target_path):
                    entry["file"] = format_file_field(str(target_path), "pdf")
                    modified = True
                else:
                    print(f"  Failed to download PDF for {bibkey}")

    return modified


def process_file(
    bib_file: str,
    download: bool = True,
    fix_existing: bool = True,
    dry_run: bool = False,
) -> None:
    """Process a BibTeX file."""
    print(f"Processing {bib_file}...")

    # Parse the BibTeX file
    with open(bib_file, "r", encoding="utf-8") as f:
        parser = BibTexParser(common_strings=True)
        # Remove problematic Unicode customization that causes errors
        bib_db = bibtexparser.load(f, parser=parser)

    # Process each entry
    modified_count = 0
    downloaded_count = 0
    fixed_count = 0

    for entry in bib_db.entries:
        if dry_run:
            # Just report what would be done
            bibkey = entry.get("ID", "unknown")
            if "pdf" in entry and "file" not in entry:
                print(f"Would download PDF for {bibkey}")
                downloaded_count += 1
            if "file" in entry:
                current_path, _ = parse_file_field(entry["file"])
                if current_path:
                    target_path = get_target_path(entry)
                    if Path(current_path) != target_path:
                        print(f"Would fix file path for {bibkey}")
                        fixed_count += 1
        else:
            old_file = entry.get("file")
            modified = process_entry(entry, download, fix_existing)

            if modified:
                modified_count += 1
                if old_file and old_file != entry.get("file"):
                    fixed_count += 1
                elif "file" in entry and not old_file:
                    downloaded_count += 1

    if dry_run:
        print("\nDry run summary:")
        print(f"  Would download: {downloaded_count} PDFs")
        print(f"  Would fix: {fixed_count} file paths")
    else:
        # Write back to file if ANY entries were modified
        if modified_count > 0:
            # Create backup
            backup_file = f"{bib_file}.backup"
            shutil.copy(bib_file, backup_file)
            print(f"\nBacked up to {backup_file}")

            # Write modified entries
            writer = BibTexWriter()
            writer.indent = "  "
            writer.order_entries_by = None  # type: ignore[assignment]
            writer.align_values = False

            with open(bib_file, "w", encoding="utf-8") as f:
                f.write(writer.write(bib_db))

            print("\nSummary:")
            print(f"  Modified: {modified_count} entries")
            print(f"  Downloaded: {downloaded_count} PDFs")
            print(f"  Fixed: {fixed_count} file paths")
            print(f"  Successful updates written to {bib_file}")
        else:
            print("\nNo changes needed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize PDFs for BibTeX entries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all PDFs and fix existing file paths
  %(prog)s file.bib
  
  # Only fix existing file paths (no downloads)
  %(prog)s --no-download file.bib
  
  # Only download new PDFs (don't fix existing)
  %(prog)s --no-fix file.bib
  
  # Dry run to see what would be done
  %(prog)s --dry-run file.bib
  
  # Process all files in a directory
  %(prog)s curated/*.bib
        """,
    )

    parser.add_argument("files", nargs="+", help="BibTeX files to process")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Skip downloading PDFs from pdf field",
    )
    parser.add_argument(
        "--no-fix", action="store_true", help="Skip fixing existing file paths"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    # Process each file
    for bib_file in args.files:
        if not os.path.exists(bib_file):
            print(f"ERROR: File not found: {bib_file}", file=sys.stderr)
            continue

        process_file(
            bib_file,
            download=not args.no_download,
            fix_existing=not args.no_fix,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
