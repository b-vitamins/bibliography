"""Indexing system for bibliography entries.

This module handles building and updating the search index from .bib files,
following Guix's pattern for progress reporting and batch processing.
"""

import time
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

from .db import BibliographyDB
from .models import BibEntry
from .repository import Repository


class IndexBuilder:
    """Builds and maintains search index from bibliography files."""

    def __init__(self, db: BibliographyDB, repository: Repository):
        """Initialize index builder.

        Args:
            db: Database instance
            repository: Repository instance
        """
        self.db = db
        self.repository = repository
        self.console = Console()

    def build_index(
        self, clear_existing: bool = True, show_progress: bool = True
    ) -> None:
        """Build search index from all .bib files.

        Args:
            clear_existing: Whether to clear existing index
            show_progress: Whether to show progress bar
        """
        if clear_existing:
            if show_progress:
                self.console.print("🗑️  Clearing existing index...")
            self.db.clear_all()

        # Load all entries from repository
        entries = self.repository.get_all_entries()

        if not entries:
            self.console.print("⚠️  No entries found to index")
            return

        if show_progress:
            self._build_with_progress(entries)
        else:
            self._build_silent(entries)

        # Optimize database after bulk insert
        if show_progress:
            self.console.print("🔧 Optimizing database...")
        self.db.optimize()

        if show_progress:
            stats = self.db.get_statistics()
            self.console.print(f"✅ Indexed {stats['total_entries']} entries")

    def update_index(self, source_files: list[Path] | None = None) -> None:
        """Update index for specific files or detect changes.

        Args:
            source_files: Specific files to update, or None to detect changes
        """
        if source_files is None:
            # For now, rebuild entire index
            # TODO: Implement change detection based on file modification times
            self.console.print(
                "🔄 Full index update (change detection not yet implemented)"
            )
            self.build_index(clear_existing=True, show_progress=True)
        else:
            # Update specific files
            self.console.print(f"🔄 Updating index for {len(source_files)} files...")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console,
            ) as progress:
                task = progress.add_task("Updating entries", total=len(source_files))

                for file_path in source_files:
                    # Remove existing entries from this file
                    existing = self.db.get_entries_by_file(str(file_path))
                    for _entry in existing:
                        # For SQLite, we use INSERT OR REPLACE, so no need to delete
                        pass

                    # Load and insert new entries
                    try:
                        new_entries = self.repository.load_entries_from_file(file_path)
                        if new_entries:
                            self.db.insert_entries_batch(new_entries)
                        progress.update(
                            task, advance=1, description=f"Updated {file_path.name}"
                        )
                    except Exception as e:
                        self.console.print(f"❌ Error updating {file_path}: {e}")
                        progress.update(task, advance=1)

            self.console.print("✅ Index update completed")

    def get_index_status(self) -> dict[str, int | str | bool | dict[str, int]]:
        """Get current index status and statistics.

        Returns:
            Dictionary with index status information
        """
        stats = self.db.get_statistics()

        # Get repository statistics for comparison
        repo_entries = self.repository.get_all_entries()

        status = {
            "db_entries": stats["total_entries"],
            "repo_entries": len(repo_entries),
            "up_to_date": stats["total_entries"] == len(repo_entries),
            "by_type": stats["by_type"],
            "by_file": stats["by_file"],
            "db_size_mb": stats["db_size_bytes"] / (1024 * 1024),
            "fts_entries": stats["fts_entries"],
        }

        return status

    def _build_with_progress(self, entries: list[BibEntry]) -> None:
        """Build index with progress reporting."""
        start_time = time.time()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        ) as progress:
            # Add main indexing task
            main_task = progress.add_task("Building search index", total=len(entries))

            batch_size = 1000
            batched = 0

            for i in range(0, len(entries), batch_size):
                batch = entries[i : i + batch_size]

                # Insert batch
                self.db.insert_entries_batch(batch, batch_size=len(batch))
                batched += len(batch)

                # Update progress
                progress.update(
                    main_task,
                    advance=len(batch),
                    description=f"Indexed {batched:,} entries",
                )

        elapsed = time.time() - start_time
        rate = len(entries) / elapsed if elapsed > 0 else 0
        self.console.print(
            f"📊 Indexed {len(entries):,} entries in {elapsed:.2f}s "
            f"({rate:.0f} entries/sec)"
        )

    def _build_silent(self, entries: list[BibEntry]) -> None:
        """Build index without progress reporting."""
        self.db.insert_entries_batch(entries)

    def rebuild_fts_index(self) -> None:
        """Rebuild FTS5 index from entries table to fix inconsistencies."""
        self.console.print("🔧 Rebuilding FTS5 index...")
        start_time = time.time()

        self.db.rebuild_fts_from_entries()

        elapsed = time.time() - start_time
        self.console.print(f"✅ FTS5 index rebuilt in {elapsed:.2f}s")

    def check_fts_consistency(self) -> bool:
        """Check if FTS5 index is consistent with main entries table.

        Returns:
            True if consistent, False otherwise
        """
        stats = self.db.get_statistics()
        consistent = stats["total_entries"] == stats["fts_entries"]

        if not consistent:
            self.console.print(
                f"⚠️  FTS index inconsistent: {stats['total_entries']} entries, "
                f"{stats['fts_entries']} in FTS"
            )

        return consistent


def get_default_db_path() -> Path:
    """Get default database path following XDG conventions.

    Returns:
        Path to default database location
    """
    # Use XDG cache directory or fallback
    import os

    cache_dir = os.environ.get("XDG_CACHE_HOME")
    base_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache"

    return base_dir / "bibmgr" / "bibliography.db"


def create_index_builder(
    repository: Repository, db_path: Path | None = None
) -> IndexBuilder:
    """Create index builder with default or custom database path.

    Args:
        repository: Repository instance
        db_path: Custom database path, or None for default

    Returns:
        IndexBuilder instance
    """
    if db_path is None:
        db_path = get_default_db_path()

    db = BibliographyDB(db_path)
    return IndexBuilder(db, repository)
