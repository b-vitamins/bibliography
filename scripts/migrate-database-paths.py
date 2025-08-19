#!/usr/bin/env python3
"""
Migrate database file paths from old structure to new structure.
Maps by-domain/* to curated/* and handles other reorganizations.
"""

import sqlite3
from pathlib import Path

# Path mappings from old to new structure
PATH_MAPPINGS = {
    # Most by-domain files moved to curated/
    "by-domain/autoencoder.bib": "curated/autoencoder.bib",
    "by-domain/continual.bib": "curated/continual.bib",
    "by-domain/diffusion.bib": "curated/diffusion.bib",
    "by-domain/ebm.bib": "curated/ebm.bib",
    "by-domain/flows.bib": "curated/flows.bib",
    "by-domain/gan.bib": "curated/gan.bib",
    "by-domain/generalization.bib": "curated/generalization.bib",
    "by-domain/geometric.bib": "curated/geometric.bib",
    "by-domain/gnn.bib": "curated/gnn.bib",
    "by-domain/hopfield.bib": "curated/hopfield.bib",
    "by-domain/incontext.bib": "curated/incontext.bib",
    "by-domain/information-theory.bib": "curated/information-theory.bib",
    "by-domain/information.bib": "curated/information.bib",
    "by-domain/llm.bib": "curated/llm.bib",
    "by-domain/ml-theory.bib": "curated/ml-theory.bib",
    "by-domain/moe.bib": "curated/moe.bib",
    "by-domain/neurosymbolic.bib": "curated/neurosymbolic.bib",
    "by-domain/oscillation.bib": "curated/oscillation.bib",
    "by-domain/quantumml.bib": "curated/quantumml.bib",
    "by-domain/rl.bib": "curated/rl.bib",
    "by-domain/sciml.bib": "curated/sciml.bib",
    "by-domain/spnn.bib": "curated/spnn.bib",
    "by-domain/ssm.bib": "curated/ssm.bib",
    "by-domain/training.bib": "curated/training.bib",
    "by-domain/transformers.bib": "curated/transformers.bib",
    "by-domain/worldmodel.bib": "curated/worldmodel.bib",
    # Special moves
    "by-domain/physics-computational.bib": "courses/physics-computational.bib",
    "by-domain/infophyscomp.bib": "references/infophyscomp.bib",
    "by-domain/award.bib": "curated/award.bib",  # or wherever it went
    # by-format moves
    "by-format/courses/course-notes.bib": "courses/course-notes.bib",
    "by-format/courses/coursework-exams.bib": "courses/coursework-exams.bib",
    "by-format/courses/coursework-homework.bib": "courses/coursework-homework.bib",
    "by-format/courses/coursework-solutions.bib": "courses/coursework-solutions.bib",
    "by-format/courses/problem-sets.bib": "courses/problem-sets.bib",
    "by-format/courses/physics-computational.bib": "courses/physics-computational.bib",
    "by-format/presentations.bib": "presentations/presentations.bib",
    "by-format/references/dlfc.bib": "references/dlfc.bib",
    "by-format/references/infophyscomp.bib": "references/infophyscomp.bib",
    "by-format/references/reference-guides.bib": "references/reference-guides.bib",
    "by-format/references/references.bib": "references/references.bib",
    "by-format/references/technical-standards.bib": "references/technical-standards.bib",
    "by-format/references/tutorials.bib": "references/tutorials.bib",
    "by-format/references/udl.bib": "references/udl.bib",
    "by-format/references/whitepapers.bib": "references/whitepapers.bib",
    "by-format/references/award.bib": "curated/award.bib",
    "by-format/theses/dissertations.bib": "theses/dissertations.bib",
    "by-format/theses/theses.bib": "theses/theses.bib",
}


def migrate_database(db_path="bibliography.db"):
    """Update all file paths in the database."""
    if not Path(db_path).exists():
        print(f"Database {db_path} not found")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get list of tables with file_path column
    tables_to_update = []
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    for table_name in [row[0] for row in c.fetchall()]:
        c.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in c.fetchall()]
        if "file_path" in columns:
            tables_to_update.append(table_name)

    print(f"Found {len(tables_to_update)} tables to update: {tables_to_update}")

    total_updates = 0

    for table in tables_to_update:
        print(f"\nUpdating {table}...")
        table_updates = 0

        for old_path, new_path in PATH_MAPPINGS.items():
            c.execute(
                f"UPDATE {table} SET file_path = ? WHERE file_path = ?",
                (new_path, old_path),
            )
            count = c.rowcount
            if count > 0:
                print(f"  {old_path} -> {new_path}: {count} rows")
                table_updates += count

        total_updates += table_updates
        print(f"  Total updates in {table}: {table_updates}")

    # Check for any remaining old paths
    print("\nChecking for unmapped paths...")
    for table in tables_to_update:
        c.execute(f"SELECT DISTINCT file_path FROM {table} WHERE file_path LIKE 'by-%'")
        remaining = c.fetchall()
        if remaining:
            print(f"\nWARNING: Unmapped paths in {table}:")
            for path in remaining:
                print(f"  - {path[0]}")

    conn.commit()
    conn.close()

    print(f"\nTotal database updates: {total_updates}")


if __name__ == "__main__":
    migrate_database()
