#!/usr/bin/env python3
"""
Batch enrichment script that processes multiple entries and tracks each result.

This script:
1. Reads a batch JSON file with entries to enrich
2. For each entry, calls enrich-single-entry.py
3. Collects results and provides summary
4. All tracking is handled automatically by the single-entry script

Usage: batch-enrich-with-tracking.py <batch_json_file>

The batch JSON file should have the format:
{
  "source_file": "path/to/file.bib",
  "entries": ["key1", "key2", ...]
}
"""

import json
import subprocess
import sys
from pathlib import Path


def process_batch(batch_file: str) -> dict[str, int]:
    """Process a batch of entries for enrichment."""
    try:
        with open(batch_file, "r", encoding="utf-8") as f:
            batch_data = json.load(f)
    except Exception as e:
        print(f"Error reading batch file: {e}", file=sys.stderr)
        sys.exit(1)
    
    source_file = batch_data.get("source_file")
    entries = batch_data.get("entries", [])
    
    if not source_file:
        print("Error: No source_file specified in batch", file=sys.stderr)
        sys.exit(1)
    
    if not entries:
        print("Warning: No entries to process")
        return {"success": 0, "failed": 0, "partial": 0}
    
    print(f"Processing {len(entries)} entries from {source_file}")
    print("-" * 60)
    
    results = {"success": 0, "failed": 0, "partial": 0}
    
    for i, entry_key in enumerate(entries, 1):
        print(f"\n[{i}/{len(entries)}] Processing {entry_key}")
        
        # Call the single-entry enrichment script
        cmd = [
            sys.executable,
            "scripts/enrich-single-entry.py",
            source_file,
            entry_key
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Check the exit code
            if result.returncode == 0:
                results["success"] += 1
                print(f"✓ {entry_key}: Enriched successfully")
            elif result.returncode == 2:
                results["partial"] += 1
                print(f"⚠ {entry_key}: Processed but no enrichment indicators")
            else:
                results["failed"] += 1
                print(f"✗ {entry_key}: Failed to enrich")
                if result.stderr:
                    print(f"  Error: {result.stderr.strip()}")
            
            # Print any output
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if not line.startswith("ENRICHMENT_REQUIRED:"):
                        print(f"  {line}")
            
        except Exception as e:
            results["failed"] += 1
            print(f"✗ {entry_key}: Error running enrichment: {e}")
    
    return results


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: batch-enrich-with-tracking.py <batch_json_file>", file=sys.stderr)
        print("\nProcesses a batch of entries and automatically tracks results.", file=sys.stderr)
        sys.exit(1)
    
    batch_file = sys.argv[1]
    
    if not Path(batch_file).exists():
        print(f"Error: Batch file '{batch_file}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Process the batch
    results = process_batch(batch_file)
    
    # Print summary
    print("\n" + "=" * 60)
    print("BATCH ENRICHMENT SUMMARY")
    print("=" * 60)
    print(f"✓ Successful: {results['success']}")
    print(f"⚠ Partial:    {results['partial']}")
    print(f"✗ Failed:     {results['failed']}")
    print(f"─ Total:      {sum(results.values())}")
    print("=" * 60)
    
    # All tracking is already done by enrich-single-entry.py
    print("\nAll results have been tracked in the database.")
    
    # Exit with appropriate code
    if results["failed"] > 0:
        sys.exit(1)
    elif results["partial"] > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()