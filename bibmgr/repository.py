"""Repository layer for managing BibTeX files with atomic operations."""

import tempfile
from pathlib import Path
from typing import Any

import bibtexparser  # type: ignore[import-untyped]
from bibtexparser.bparser import BibTexParser  # type: ignore[import-untyped]
from bibtexparser.bwriter import BibTexWriter  # type: ignore[import-untyped]

from .models import BibEntry


class ChangeSet:
    """Tracks changes for dry-run mode."""

    def __init__(self) -> None:
        """Initialize empty changeset."""
        self.added: list[BibEntry] = []
        self.removed: list[BibEntry] = []
        self.updated: list[tuple[BibEntry, BibEntry]] = []  # (old, new)
        self.file_operations: list[dict[str, Any]] = []

    def add_entry(self, entry: BibEntry) -> None:
        """Record an entry addition."""
        self.added.append(entry)

    def remove_entry(self, entry: BibEntry) -> None:
        """Record an entry removal."""
        self.removed.append(entry)

    def update_entry(self, old: BibEntry, new: BibEntry) -> None:
        """Record an entry update."""
        self.updated.append((old, new))

    def add_file_operation(self, operation: str, **kwargs: Any) -> None:
        """Record a file operation."""
        self.file_operations.append({"operation": operation, **kwargs})

    def summary(self) -> str:
        """Generate a summary of changes."""
        lines = ["=== Change Summary ==="]

        if self.added:
            lines.append(f"\nAdded {len(self.added)} entries:")
            for entry in self.added:
                lines.append(f"  + {entry.key} ({entry.entry_type})")

        if self.removed:
            lines.append(f"\nRemoved {len(self.removed)} entries:")
            for entry in self.removed:
                lines.append(f"  - {entry.key} ({entry.entry_type})")

        if self.updated:
            lines.append(f"\nUpdated {len(self.updated)} entries:")
            for old, new in self.updated:
                lines.append(f"  ~ {old.key}")
                # Show field changes
                old_fields = set(old.fields.keys())
                new_fields = set(new.fields.keys())

                for field in sorted(new_fields - old_fields):
                    lines.append(f"    + {field}: {new.fields[field]}")

                for field in sorted(old_fields - new_fields):
                    lines.append(f"    - {field}: {old.fields[field]}")

                for field in sorted(old_fields & new_fields):
                    if old.fields[field] != new.fields[field]:
                        lines.append(
                            f"    ~ {field}: {old.fields[field]} → {new.fields[field]}"
                        )

        if self.file_operations:
            lines.append(f"\nFile operations ({len(self.file_operations)}):")
            for op in self.file_operations:
                operation = op["operation"]
                if operation == "copy":
                    lines.append(f"  Copy: {op['src']} → {op['dst']}")
                elif operation == "move":
                    lines.append(f"  Move: {op['src']} → {op['dst']}")
                elif operation == "delete":
                    lines.append(f"  Delete: {op['path']}")

        return "\n".join(lines)


class Repository:
    """Manages BibTeX files with support for atomic operations and dry-run mode."""

    def __init__(self, root_path: Path) -> None:
        """Initialize repository with root path."""
        self.root_path = Path(root_path)
        self.bibtex_path = self.root_path / "bibtex"
        self._entries_cache: dict[Path, list[BibEntry]] = {}
        self._changeset: ChangeSet | None = None
        self._dry_run = False

    @property
    def root(self) -> Path:
        """Get root path (alias for root_path for backward compatibility)."""
        return self.root_path

    def enable_dry_run(self) -> None:
        """Enable dry-run mode - changes are tracked but not applied."""
        self._dry_run = True
        self._changeset = ChangeSet()

    def disable_dry_run(self) -> None:
        """Disable dry-run mode."""
        self._dry_run = False
        self._changeset = None

    @property
    def changeset(self) -> ChangeSet | None:
        """Get current changeset (only in dry-run mode)."""
        return self._changeset

    @property
    def is_dry_run(self) -> bool:
        """Check if repository is in dry-run mode."""
        return self._dry_run

    @property
    def entries_cache(self) -> dict[Path, list[BibEntry]]:
        """Get entries cache (for testing)."""
        return self._entries_cache

    def load_entries(self, force_reload: bool = False) -> list[BibEntry]:
        """Load all entries from .bib files."""
        if not force_reload and self._entries_cache:
            # Return flattened cache
            all_entries = []
            for entries in self._entries_cache.values():
                all_entries.extend(entries)
            return all_entries

        self._entries_cache.clear()
        all_entries = []

        for bib_file in self.bibtex_path.rglob("*.bib"):
            entries = self.load_file(bib_file)
            self._entries_cache[bib_file] = entries
            all_entries.extend(entries)

        return all_entries

    def get_all_entries(self) -> list[BibEntry]:
        """Get all entries from repository (alias for load_entries)."""
        return self.load_entries()

    def load_file(self, bib_file: Path) -> list[BibEntry]:
        """Load entries from a single .bib file."""
        if not bib_file.exists():
            return []

        parser = BibTexParser()
        parser.ignore_nonstandard_types = False  # type: ignore[attr-defined]
        parser.homogenize_fields = False  # type: ignore[attr-defined]

        with open(bib_file, encoding="utf-8") as f:
            bib_db = bibtexparser.load(f, parser)

        entries = []
        for entry in bib_db.entries:
            # Extract entry type and key
            entry_type = entry.get("ENTRYTYPE", "misc").lower()
            key = entry.get("ID", "")

            # Remove metadata fields
            fields = {k: v for k, v in entry.items() if k not in ["ENTRYTYPE", "ID"]}

            entries.append(
                BibEntry(
                    key=key,
                    entry_type=entry_type,
                    fields=fields,
                    source_file=bib_file,
                )
            )

        return entries

    def save_entries(self, entries: list[BibEntry], bib_file: Path) -> None:
        """Save entries to a .bib file with atomic write."""
        if self._dry_run:
            # In dry-run mode, just track what would be saved
            existing = self._entries_cache.get(bib_file, [])

            # Track changes
            existing_keys = {e.key for e in existing}
            new_keys = {e.key for e in entries}

            # Added entries
            for entry in entries:
                if entry.key not in existing_keys:
                    self._changeset.add_entry(entry)  # type: ignore[union-attr]

            # Removed entries
            for entry in existing:
                if entry.key not in new_keys:
                    self._changeset.remove_entry(entry)  # type: ignore[union-attr]

            # Updated entries
            for new_entry in entries:
                if new_entry.key in existing_keys:
                    old_entry = next(e for e in existing if e.key == new_entry.key)
                    if old_entry.fields != new_entry.fields:
                        self._changeset.update_entry(old_entry, new_entry)  # type: ignore[union-attr]

            return

        # Prepare entries for bibtexparser
        bib_entries = []
        for entry in entries:
            bib_entry = {"ENTRYTYPE": entry.entry_type, "ID": entry.key}
            # Filter out None values
            filtered_fields = {k: v for k, v in entry.fields.items() if v is not None}
            bib_entry.update(filtered_fields)
            bib_entries.append(bib_entry)

        # Create BibTeX database
        db = bibtexparser.bibdatabase.BibDatabase()
        db.entries = bib_entries

        # Configure writer for clean output
        writer = BibTexWriter()
        writer.indent = "  "
        writer.order_entries_by = None  # type: ignore[assignment]
        writer.align_values = False

        # Write to temporary file first (atomic write)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=bib_file.parent,
            delete=False,
        ) as tmp:
            tmp.write(writer.write(db))
            tmp_path = Path(tmp.name)

        # Atomic replace
        tmp_path.replace(bib_file)

        # Update cache
        self._entries_cache[bib_file] = entries

    def get_entry(self, key: str) -> BibEntry | None:
        """Get an entry by its key."""
        entries = self.load_entries()
        for entry in entries:
            if entry.key == key:
                return entry
        return None

    def add_entry(self, entry: BibEntry, target_file: Path | None = None) -> None:
        """Add a new entry to the repository."""
        if target_file is None:
            # Determine target file based on entry type
            target_file = self.find_target_file(entry.entry_type)

        # Ensure target directory exists
        target_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing entries from target file
        existing = self.get_entries_by_file(target_file)

        # Check for duplicate key across entire repository
        existing_entry = self.get_entry(entry.key)
        if existing_entry:
            msg = (
                f"Entry with key '{entry.key}' already exists in "
                f"{existing_entry.source_file}"
            )
            raise ValueError(msg)

        # Update entry's source file
        entry.source_file = target_file

        # Add new entry
        updated = existing + [entry]

        # Save back
        self.save_entries(updated, target_file)

    def remove_entry(self, key: str) -> BibEntry | None:
        """Remove an entry by its key."""
        # Find the entry
        entry = self.get_entry(key)
        if not entry:
            return None

        # Load entries from source file
        entries = self._entries_cache.get(entry.source_file, [])

        # Remove the entry
        updated = [e for e in entries if e.key != key]

        # Save back
        self.save_entries(updated, entry.source_file)

        return entry

    def update_entry(self, key: str, updates: dict[str, str | None]) -> BibEntry | None:
        """Update an entry's fields."""
        # Find the entry
        entry = self.get_entry(key)
        if not entry:
            return None

        # Create updated entry
        updated_entry = entry.copy()
        for field, value in updates.items():
            if value is None:
                updated_entry.remove_field(field)
            else:
                updated_entry.update_field(field, value)

        # Load entries from source file
        entries = self._entries_cache.get(entry.source_file, [])

        # Replace the entry
        updated_entries = []
        for e in entries:
            if e.key == key:
                updated_entries.append(updated_entry)
            else:
                updated_entries.append(e)

        # Save back
        self.save_entries(updated_entries, entry.source_file)

        return updated_entry

    def move_entry(self, key: str, target_file: Path) -> BibEntry | None:
        """Move an entry to a different .bib file."""
        # Find the entry
        entry = self.get_entry(key)
        if not entry:
            return None

        if entry.source_file == target_file:
            return entry  # Already in target file

        # Remove from source
        source_entries = self._entries_cache.get(entry.source_file, [])
        updated_source = [e for e in source_entries if e.key != key]
        self.save_entries(updated_source, entry.source_file)

        # Add to target
        entry.source_file = target_file
        self.add_entry(entry, target_file)

        return entry

    def get_entries_by_type(self, entry_type: str) -> list[BibEntry]:
        """Get all entries of a specific type."""
        entries = self.load_entries()
        return [e for e in entries if e.entry_type == entry_type]

    def get_entries_by_file(self, bib_file: Path) -> list[BibEntry]:
        """Get all entries from a specific .bib file."""
        if bib_file not in self._entries_cache:
            entries = self.load_file(bib_file)
            self._entries_cache[bib_file] = entries
        return self._entries_cache.get(bib_file, [])

    def load_entries_from_file(self, bib_file: Path) -> list[BibEntry]:
        """Load entries from a specific .bib file.

        This is an alias for get_entries_by_file for backward compatibility.

        Args:
            bib_file: Path to .bib file

        Returns:
            List of entries in that file
        """
        return self.get_entries_by_file(bib_file)

    def find_target_file(self, entry_type: str) -> Path:
        """Find the appropriate target file for an entry type."""
        by_type_dir = self.bibtex_path / "by-type"
        return by_type_dir / f"{entry_type}.bib"

    def get_stats(self) -> dict[str, int]:
        """Get repository statistics."""
        entries = self.load_entries()
        stats = {
            "total_entries": len(entries),
            "total_files": len(self._entries_cache),
        }

        # Count by type
        type_counts: dict[str, int] = {}
        for entry in entries:
            type_counts[entry.entry_type] = type_counts.get(entry.entry_type, 0) + 1

        stats.update(type_counts)
        return stats
