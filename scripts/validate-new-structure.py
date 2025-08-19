#!/usr/bin/env python3
"""
Comprehensive validation of the new bibliography structure.
Checks all scripts, database consistency, and file organization.
"""

import subprocess
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple


def check_directory_structure() -> Tuple[bool, List[str]]:
    """Verify the new directory structure exists."""
    required_dirs = [
        "books",
        "conferences",
        "courses",
        "curated",
        "journals",
        "presentations",
        "references",
        "theses",
    ]
    missing = []
    for dir_name in required_dirs:
        if not Path(dir_name).exists():
            missing.append(dir_name)

    return len(missing) == 0, missing


def check_database_paths() -> Tuple[bool, Dict[str, int]]:
    """Check database has no old paths."""
    if not Path("bibliography.db").exists():
        return True, {}

    conn = sqlite3.connect("bibliography.db")
    c = conn.cursor()

    issues = {}

    # Check for old paths
    for table in ["bib_entries", "enrichment_log"]:
        c.execute(f"SELECT COUNT(*) FROM {table} WHERE file_path LIKE 'by-%'")
        count = c.fetchone()[0]
        if count > 0:
            issues[f"{table}_old_paths"] = count

    conn.close()
    return len(issues) == 0, issues


def test_script_functionality() -> Tuple[bool, Dict[str, str]]:
    """Test key scripts work with new structure."""
    tests = {}

    # Test count-entries
    try:
        result = subprocess.run(
            ["python3", "scripts/count-entries.py", "curated/llm.bib"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        tests["count-entries"] = (
            "OK" if result.returncode == 0 else f"Failed: {result.stderr}"
        )
    except Exception as e:
        tests["count-entries"] = f"Error: {e}"

    # Test bijection-tracker check
    try:
        result = subprocess.run(
            [
                "guix",
                "shell",
                "-m",
                "manifest.scm",
                "--",
                "python3",
                "scripts/bijection-tracker.py",
                "--check",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        tests["bijection-tracker"] = (
            "OK" if result.returncode == 0 else f"Failed: {result.stderr[:100]}"
        )
    except Exception as e:
        tests["bijection-tracker"] = f"Error: {e}"

    # Test enrichment-status
    try:
        result = subprocess.run(
            ["python3", "scripts/enrichment-status.py"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        tests["enrichment-status"] = (
            "OK" if result.returncode == 0 else f"Failed: {result.stderr}"
        )
    except Exception as e:
        tests["enrichment-status"] = f"Error: {e}"

    all_ok = all(v == "OK" for v in tests.values())
    return all_ok, tests


def count_total_entries() -> Dict[str, int]:
    """Count total entries in each directory."""
    counts = {}

    for dir_path in Path(".").iterdir():
        if dir_path.is_dir() and dir_path.name in [
            "books",
            "conferences",
            "courses",
            "curated",
            "journals",
            "presentations",
            "references",
            "theses",
        ]:
            total = 0
            for bib_file in dir_path.rglob("*.bib"):
                if ".backup" not in str(bib_file):
                    try:
                        with open(bib_file) as f:
                            content = f.read()
                            # Count @ entries but skip @comment, @string, @preamble
                            import re

                            entries = re.findall(
                                r"^@(?!comment|string|preamble)\w+{",
                                content,
                                re.MULTILINE | re.IGNORECASE,
                            )
                            total += len(entries)
                    except Exception:
                        pass
            counts[dir_path.name] = total

    return counts


def main():
    print("=" * 70)
    print("BIBLIOGRAPHY STRUCTURE VALIDATION")
    print("=" * 70)
    print()

    # 1. Check directory structure
    print("1. Directory Structure:")
    dirs_ok, missing = check_directory_structure()
    if dirs_ok:
        print("   ✓ All required directories present")
    else:
        print(f"   ✗ Missing directories: {missing}")
    print()

    # 2. Check database paths
    print("2. Database Path Migration:")
    db_ok, db_issues = check_database_paths()
    if db_ok:
        print("   ✓ All database paths updated")
    else:
        print("   ✗ Database issues:")
        for issue, count in db_issues.items():
            print(f"     - {issue}: {count}")
    print()

    # 3. Test script functionality
    print("3. Script Functionality:")
    scripts_ok, script_results = test_script_functionality()
    for script, status in script_results.items():
        symbol = "✓" if status == "OK" else "✗"
        print(f"   {symbol} {script}: {status}")
    print()

    # 4. Count entries
    print("4. Entry Counts by Directory:")
    counts = count_total_entries()
    total = sum(counts.values())
    for dir_name, count in sorted(counts.items()):
        print(f"   {dir_name:15} {count:6,} entries")
    print(f"   {'TOTAL':15} {total:6,} entries")
    print()

    # 5. Overall status
    print("5. Overall Status:")
    if dirs_ok and db_ok and scripts_ok:
        print("   ✅ All systems operational with new structure!")
    else:
        print("   ⚠️  Some issues need attention")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
