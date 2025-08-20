#!/usr/bin/env python3
"""
Orchestrate the complete bibliography enrichment workflow end-to-end.

This script automates the entire process:
1. Analyzes a BibTeX file to find unenriched entries
2. Processes entries in batches (handling ENRICHMENT_REQUIRED markers)
3. Reassembles the enriched file
4. Validates the results
5. Replaces the original if validation passes

Usage:
    enrich-bibliography.py file.bib                    # Enrich entire file
    enrich-bibliography.py file.bib --backup           # Create backup before modifying
    enrich-bibliography.py file.bib --validate-only    # Just run validation
    enrich-bibliography.py file.bib --retry-failed     # Include retry of previously failed entries
    enrich-bibliography.py file.bib --dry-run          # Show what would be done
    enrich-bibliography.py file.bib --batch-size 10    # Custom batch size
    enrich-bibliography.py file.bib --max-batches 5    # Limit number of batches
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode


class EnrichmentOrchestrator:
    """Orchestrates the complete enrichment workflow."""

    def __init__(
        self,
        file_path: Path,
        backup: bool = False,
        validate_only: bool = False,
        retry_failed: bool = False,
        dry_run: bool = False,
        batch_size: int = 20,
        max_batches: Optional[int] = None,
        verbose: bool = False,
    ):
        self.file_path = file_path
        self.backup = backup
        self.validate_only = validate_only
        self.retry_failed = retry_failed
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.max_batches = max_batches
        self.verbose = verbose

        # State tracking
        self.original_count = 0
        self.enriched_count = 0
        self.unenriched_count = 0
        self.failed_count = 0
        self.validated_count = 0
        self.backup_path: Optional[Path] = None
        self.temp_dir: Optional[Path] = None
        self.enriched_file: Optional[Path] = None

    def log(self, message: str, level: str = "info") -> None:
        """Log a message with appropriate formatting."""
        prefix = {
            "info": "ℹ️ ",
            "success": "✓ ",
            "warning": "⚠️ ",
            "error": "✗ ",
            "progress": "🔄 ",
            "debug": "🔍 ",
        }.get(level, "")

        if level == "debug" and not self.verbose:
            return

        print(f"{prefix}{message}")

    def run(self) -> bool:
        """Run the complete enrichment workflow."""
        try:
            self.log(f"Starting enrichment workflow for {self.file_path}")

            # Validate only mode
            if self.validate_only:
                return self._run_validation_only()

            # Step 1: Initial checks
            if not self._initial_checks():
                return False

            # Step 2: Create backup if requested
            if self.backup and not self.dry_run:
                self._create_backup()

            # Step 3: Analyze file
            self.log("Analyzing file for enrichment status...", "progress")
            analysis = self._analyze_file()
            if not analysis:
                return False

            # Step 4: Check if enrichment needed
            if analysis["unenriched_entries"] == 0 and not self.retry_failed:
                self.log("All entries are already enriched!", "success")
                return True

            # Step 5: Process batches
            if not self.dry_run:
                self.log(
                    f"Processing {analysis['unenriched_entries']} unenriched entries...",
                    "progress",
                )
                if not self._process_batches(analysis):
                    return False

            # Step 6: Reassemble file
            if not self.dry_run:
                self.log("Reassembling enriched file...", "progress")
                if not self._reassemble_file(analysis):
                    return False

            # Step 7: Validate results
            if not self.dry_run:
                self.log("Validating enriched file...", "progress")
                if not self._validate_results():
                    return False

            # Step 8: Replace original
            if not self.dry_run:
                self.log("Replacing original file with enriched version...", "progress")
                if not self._replace_original():
                    return False

            # Success!
            self._print_summary()
            return True

        except KeyboardInterrupt:
            self.log("Workflow interrupted by user", "error")
            self._cleanup(restore_backup=True)
            return False
        except Exception as e:
            self.log(f"Unexpected error: {e}", "error")
            self._cleanup(restore_backup=True)
            return False

    def _initial_checks(self) -> bool:
        """Perform initial checks before starting."""
        # Check file exists
        if not self.file_path.exists():
            self.log(f"File not found: {self.file_path}", "error")
            return False

        # Check database exists
        if not Path("bibliography.db").exists():
            self.log("Initializing tracking database...", "info")
            try:
                subprocess.run(
                    ["python3", "scripts/init-tracking-db.py"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.log("Database initialized successfully", "success")
            except subprocess.CalledProcessError as e:
                self.log(f"Failed to initialize database: {e.stderr}", "error")
                return False

        # Parse file to get initial count
        try:
            parser = BibTexParser()
            parser.customization = convert_to_unicode  # type: ignore[attr-defined]
            with open(self.file_path, "r", encoding="utf-8") as f:
                bib_db = bibtexparser.load(f, parser=parser)
            self.original_count = len(bib_db.entries)
            self.log(f"Found {self.original_count} entries in {self.file_path}", "info")
        except Exception as e:
            self.log(f"Error parsing BibTeX file: {e}", "error")
            return False

        return True

    def _create_backup(self) -> None:
        """Create a backup of the original file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_path = self.file_path.with_suffix(f".bak.{timestamp}")
        shutil.copy2(self.file_path, self.backup_path)
        self.log(f"Created backup: {self.backup_path}", "success")

    def _analyze_file(self) -> Optional[Dict[str, Any]]:
        """Analyze the file for enrichment status."""
        try:
            result = subprocess.run(
                ["python3", "scripts/analyze-enrichment.py", str(self.file_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            analysis = json.loads(result.stdout)

            self.enriched_count = analysis.get("enriched_entries", 0)
            self.unenriched_count = analysis.get("unenriched_entries", 0)

            self.log(
                f"Analysis complete: {self.enriched_count} enriched, {self.unenriched_count} unenriched",
                "info",
            )

            # Store temp directory
            if "temp_directory" in analysis:
                self.temp_dir = Path(analysis["temp_directory"])

            return analysis

        except subprocess.CalledProcessError as e:
            self.log(f"Analysis failed: {e.stderr}", "error")
            return None
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse analysis output: {e}", "error")
            return None

    def _process_batches(self, analysis: Dict[str, Any]) -> bool:
        """Process enrichment batches."""
        batch_files = analysis.get("batch_files", [])
        if not batch_files:
            self.log("No batches to process", "warning")
            return True

        # Limit batches if requested
        if self.max_batches:
            batch_files = batch_files[: self.max_batches]
            self.log(f"Processing first {self.max_batches} batches only", "info")

        total_batches = len(batch_files)
        self.log(f"Processing {total_batches} batch(es)...", "progress")

        # Process each batch
        for i, batch_file in enumerate(batch_files, 1):
            self.log(
                f"\nProcessing batch {i}/{total_batches}: {Path(batch_file).name}",
                "progress",
            )

            # Print enrichment markers for Claude to handle
            with open(batch_file, "r") as f:
                batch_data = json.load(f)

            entries = batch_data.get("entries", [])
            for entry in entries:
                entry_file = entry.get("file")
                if entry_file:
                    print(f"ENRICHMENT_REQUIRED: {entry_file}")

            # Wait for enrichment to complete
            self.log(f"Waiting for batch {i} enrichment to complete...", "debug")
            time.sleep(2)  # Give Claude time to process

        return True

    def _reassemble_file(self, analysis: Dict[str, Any]) -> bool:
        """Reassemble the enriched file from individual entries."""
        if not self.temp_dir:
            self.log("No temporary directory found", "error")
            return False

        total_entries = analysis.get("total_entries", 0)

        # Create enriched file path
        self.enriched_file = self.file_path.with_suffix(".enriched")

        self.log(f"Reassembling {total_entries} entries...", "debug")

        # Use the sequential loop method for reassembly
        reassembly_cmd = (
            f"for i in $(seq 1 {total_entries}); do "
            f'[ -f "{self.temp_dir}/entry-$i.bib" ] && '
            f'cat "{self.temp_dir}/entry-$i.bib" && echo; '
            f'done > "{self.enriched_file}"'
        )

        try:
            result = subprocess.run(
                ["bash", "-c", reassembly_cmd],
                capture_output=True,
                text=True,
                check=True,
            )

            # Verify reassembled file
            if not self.enriched_file.exists():
                self.log("Reassembled file not created", "error")
                return False

            # Count entries in reassembled file
            result = subprocess.run(
                ["grep", "-c", "^@", str(self.enriched_file)],
                capture_output=True,
                text=True,
            )
            reassembled_count = int(result.stdout.strip())

            if reassembled_count != total_entries:
                self.log(
                    f"Entry count mismatch: expected {total_entries}, got {reassembled_count}",
                    "error",
                )
                return False

            self.log(f"Successfully reassembled {reassembled_count} entries", "success")
            return True

        except subprocess.CalledProcessError as e:
            self.log(f"Reassembly failed: {e.stderr}", "error")
            return False
        except Exception as e:
            self.log(f"Error during reassembly: {e}", "error")
            return False

    def _validate_results(self) -> bool:
        """Validate the enriched file."""
        if not self.enriched_file or not self.enriched_file.exists():
            self.log("No enriched file to validate", "error")
            return False

        try:
            # Run validation
            result = subprocess.run(
                [
                    "python3",
                    "scripts/validate-enrichment.py",
                    str(self.enriched_file),
                    "--no-pdf-check",  # Skip PDF checks for speed
                    "--summary",
                ],
                capture_output=True,
                text=True,
            )

            # Parse validation results
            output = result.stdout
            self.log("Validation results:", "info")
            for line in output.strip().split("\n"):
                if line.strip():
                    print(f"  {line}")

            # Check exit code
            if result.returncode == 0:
                self.log("Validation passed!", "success")
                return True
            else:
                self.log("Validation failed - check results above", "error")
                return False

        except subprocess.CalledProcessError as e:
            self.log(f"Validation error: {e.stderr}", "error")
            return False

    def _replace_original(self) -> bool:
        """Replace the original file with the enriched version."""
        if not self.enriched_file or not self.enriched_file.exists():
            self.log("No enriched file to use for replacement", "error")
            return False

        try:
            # Move enriched file to original location
            shutil.move(str(self.enriched_file), str(self.file_path))
            self.log(
                f"Successfully replaced {self.file_path} with enriched version",
                "success",
            )
            return True

        except Exception as e:
            self.log(f"Failed to replace original file: {e}", "error")
            return False

    def _run_validation_only(self) -> bool:
        """Run validation on the existing file."""
        self.log(f"Running validation on {self.file_path}...", "progress")

        try:
            result = subprocess.run(
                ["python3", "scripts/validate-enrichment.py", str(self.file_path)],
                capture_output=True,
                text=True,
            )

            print(result.stdout)

            if result.returncode == 0:
                self.log("Validation passed!", "success")
                return True
            else:
                self.log("Validation failed", "error")
                return False

        except subprocess.CalledProcessError as e:
            self.log(f"Validation error: {e.stderr}", "error")
            return False

    def _cleanup(self, restore_backup: bool = False) -> None:
        """Clean up temporary files and optionally restore backup."""
        # Restore backup if requested and available
        if restore_backup and self.backup_path and self.backup_path.exists():
            self.log("Restoring backup due to error...", "warning")
            try:
                shutil.copy2(self.backup_path, self.file_path)
                self.log("Backup restored successfully", "success")
            except Exception as e:
                self.log(f"Failed to restore backup: {e}", "error")

        # Clean up temporary directory
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                self.log("Cleaned up temporary files", "debug")
            except Exception as e:
                self.log(f"Failed to clean up temp directory: {e}", "warning")

        # Clean up enriched file if exists
        if self.enriched_file and self.enriched_file.exists():
            try:
                self.enriched_file.unlink()
            except Exception:
                pass

    def _print_summary(self) -> None:
        """Print final summary of the enrichment process."""
        print("\n" + "=" * 60)
        print("ENRICHMENT WORKFLOW COMPLETE")
        print("=" * 60)

        if self.dry_run:
            print("DRY RUN MODE - No actual changes made")
            print(f"Would process {self.unenriched_count} unenriched entries")
        else:
            print(f"Original entries: {self.original_count}")
            print(f"Previously enriched: {self.enriched_count}")
            print(f"Newly enriched: {self.unenriched_count}")
            print(f"Total enriched: {self.enriched_count + self.unenriched_count}")

        if self.backup_path:
            print(f"\nBackup saved to: {self.backup_path}")

        print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrate the complete bibliography enrichment workflow end-to-end"
    )
    parser.add_argument("file", help="BibTeX file to enrich")
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup before modifying (recommended)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Just run validation without enrichment",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Include retry of previously failed entries",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Number of entries per batch (default: 20)",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        help="Maximum number of batches to process (for testing)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed debug output"
    )

    args = parser.parse_args()

    # Create orchestrator
    orchestrator = EnrichmentOrchestrator(
        file_path=Path(args.file),
        backup=args.backup,
        validate_only=args.validate_only,
        retry_failed=args.retry_failed,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        verbose=args.verbose,
    )

    # Run workflow
    success = orchestrator.run()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
