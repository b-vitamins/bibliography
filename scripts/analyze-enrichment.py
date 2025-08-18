#!/usr/bin/env python3
"""
Analyze a BibTeX file for enrichment status and prepare batch processing.
Extracts entries, identifies unenriched ones, and creates batch manifests.

Usage: analyze-enrichment.py file.bib
"""

import json
import subprocess
import sys
from pathlib import Path


def count_entries(filepath: str | Path) -> int:
    """Count total entries in BibTeX file."""
    try:
        result = subprocess.run(
            ["grep", "-c", "^@", str(filepath)], capture_output=True, text=True
        )
        return int(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return 0


def count_enriched(filepath: str | Path) -> int:
    """Count entries that have been successfully enriched according to the database."""
    import sqlite3

    db_path = "bibliography.db"
    if not Path(db_path).exists():
        return 0  # No database means nothing has been enriched

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(DISTINCT entry_key) 
            FROM latest_enrichment_status 
            WHERE file_path = ? AND latest_status = 'success'
        """,
            (str(filepath),),
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception:
        return 0


def extract_entries(filepath: str | Path) -> tuple[bool, str]:
    """Extract all entries using existing script."""
    try:
        script_path = Path(__file__).parent / "extract-entries.py"
        result = subprocess.run(
            ["python3", str(script_path), str(filepath)], capture_output=True, text=True
        )
        if result.returncode != 0:
            return False, result.stderr
        return True, result.stdout
    except Exception as e:
        return False, str(e)


def find_unenriched_entries(
    base_dir: Path, total_count: int, filepath: str | Path
) -> list[dict[str, str | int]]:
    """Find entries not successfully enriched according to the database."""
    import re
    import sqlite3

    db_path = "bibliography.db"
    enriched_keys: set[str] = set()

    # Get successfully enriched entries from database
    if Path(db_path).exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT entry_key 
                FROM latest_enrichment_status 
                WHERE file_path = ? AND latest_status = 'success'
            """,
                (str(filepath),),
            )
            enriched_keys = {row[0] for row in cursor.fetchall()}
            conn.close()
        except Exception:
            pass  # If database query fails, assume nothing is enriched

    unenriched: list[dict[str, str | int]] = []

    for i in range(1, total_count + 1):
        entry_file = base_dir / f"entry-{i}.bib"
        if entry_file.exists():
            with open(entry_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract entry key from the file
            match = re.match(r"@\w+\{([^,\s]+)", content.strip())
            if match:
                entry_key = match.group(1)
                # Check if this entry is NOT in the enriched set
                if entry_key not in enriched_keys:
                    unenriched.append({"index": i, "file": str(entry_file)})
            else:
                # If we can't extract a key, assume it needs enrichment
                unenriched.append({"index": i, "file": str(entry_file)})

    return unenriched


def create_batches(
    unenriched_entries: list[dict[str, str | int]], batch_size: int = 20
) -> list[list[dict[str, str | int]]]:
    """Create batches of entries for parallel processing."""
    batches: list[list[dict[str, str | int]]] = []
    for i in range(0, len(unenriched_entries), batch_size):
        batch = unenriched_entries[i : i + batch_size]
        batches.append(batch)
    return batches


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: analyze-enrichment.py file.bib", file=sys.stderr)
        sys.exit(1)

    filepath = Path(sys.argv[1])

    if not filepath.exists():
        result = {
            "status": "error",
            "message": f"File '{filepath}' not found",
            "action_required": "check_file",
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    try:
        # Count entries
        total = count_entries(filepath)
        enriched = count_enriched(filepath)
        remaining = total - enriched

        if remaining == 0:
            result = {
                "status": "complete",
                "message": "All entries are already enriched",
                "total_entries": total,
                "enriched_entries": enriched,
                "unenriched_entries": 0,
                "action_required": "none",
            }
            print(json.dumps(result, indent=2))
            return

        # Extract all entries
        success, output = extract_entries(filepath)
        if not success:
            result = {
                "status": "error",
                "message": f"Failed to extract entries: {output}",
                "action_required": "debug",
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        # Find unenriched entries
        base_name = filepath.stem
        tmp_dir = Path("tmp") / base_name
        unenriched = find_unenriched_entries(tmp_dir, total, filepath)

        # Create batches
        batches = create_batches(unenriched)

        # Save batch information
        batch_dir = tmp_dir / "batches"
        batch_dir.mkdir(exist_ok=True)

        batch_files: list[str] = []
        for i, batch in enumerate(batches, 1):
            batch_file = batch_dir / f"batch-{i}.json"
            with open(batch_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"batch_number": i, "entries": batch, "count": len(batch)},
                    f,
                    indent=2,
                )
            batch_files.append(str(batch_file))

        # Success output
        result = {
            "status": "ready",
            "message": (
                f"{remaining} unenriched entries found, "
                f"prepared in {len(batches)} batch(es)"
            ),
            "total_entries": total,
            "enriched_entries": enriched,
            "unenriched_entries": remaining,
            "batch_count": len(batches),
            "batch_files": batch_files,
            "temp_directory": str(tmp_dir),
            "action_required": "enrichment",
            "next_step": "Process batches via Claude enrichment agent",
            "reassembly_command": (
                f"for i in $(seq 1 {total}); do "
                f"[ -f tmp/{base_name}/entry-$i.bib ] && "
                f"cat tmp/{base_name}/entry-$i.bib && echo; "
                f"done > {filepath}.enriched"
            ),
        }
        print(json.dumps(result, indent=2))

    except Exception as e:
        result = {"status": "error", "message": str(e), "action_required": "debug"}
        print(json.dumps(result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
