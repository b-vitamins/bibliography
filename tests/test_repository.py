"""Comprehensive tests for the Repository class matching the actual API."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bibmgr.models import BibEntry
from bibmgr.repository import ChangeSet, Repository


@pytest.fixture
def temp_bibtex_dir():
    """Create a temporary directory with bibtex structure."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        bibtex_dir = tmp_path / "bibtex"
        bibtex_dir.mkdir()

        # Create by-type directory
        by_type_dir = bibtex_dir / "by-type"
        by_type_dir.mkdir()

        yield tmp_path


@pytest.fixture
def sample_entry():
    """Create a sample BibEntry for testing."""
    return BibEntry(
        key="test2023example",
        entry_type="article",
        fields={
            "title": "Test Article",
            "author": "John Doe",
            "journal": "Test Journal",
            "year": "2023",
        },
        source_file=Path("test.bib"),
    )


@pytest.fixture
def populated_repo(temp_bibtex_dir: Path):
    """Create a repository with some test data."""
    repo = Repository(temp_bibtex_dir)

    # Create some test .bib files with content
    articles_file = temp_bibtex_dir / "bibtex" / "by-type" / "article.bib"
    articles_file.write_text("""
@article{sample2023,
  title = {Sample Article},
  author = {Sample Author},
  journal = {Sample Journal},
  year = {2023}
}

@article{another2023,
  title = {Another Article},
  author = {Another Author},
  journal = {Another Journal},
  year = {2023}
}
""")

    books_file = temp_bibtex_dir / "bibtex" / "by-type" / "book.bib"
    books_file.write_text("""
@book{testbook2023,
  title = {Test Book},
  author = {Book Author},
  publisher = {Test Publisher},
  year = {2023}
}
""")

    return repo


class TestChangeSet:
    """Test ChangeSet class for tracking dry-run changes."""

    def test_changeset_initialization(self) -> None:
        """Test ChangeSet initialization."""
        changeset = ChangeSet()

        assert changeset.added == []
        assert changeset.removed == []
        assert changeset.updated == []
        assert changeset.file_operations == []

    def test_changeset_add_entry(self, sample_entry: BibEntry) -> None:
        """Test adding entry to changeset."""
        changeset = ChangeSet()
        changeset.add_entry(sample_entry)

        assert len(changeset.added) == 1
        assert changeset.added[0] == sample_entry

    def test_changeset_remove_entry(self, sample_entry: BibEntry) -> None:
        """Test removing entry from changeset."""
        changeset = ChangeSet()
        changeset.remove_entry(sample_entry)

        assert len(changeset.removed) == 1
        assert changeset.removed[0] == sample_entry

    def test_changeset_update_entry(self, sample_entry: BibEntry) -> None:
        """Test updating entry in changeset."""
        changeset = ChangeSet()
        updated_entry = sample_entry.copy()
        updated_entry.update_field("title", "Updated Title")

        changeset.update_entry(sample_entry, updated_entry)

        assert len(changeset.updated) == 1
        assert changeset.updated[0] == (sample_entry, updated_entry)

    def test_changeset_file_operations(self) -> None:
        """Test recording file operations."""
        changeset = ChangeSet()
        changeset.add_file_operation("copy", src="/old/path", dst="/new/path")

        assert len(changeset.file_operations) == 1
        assert changeset.file_operations[0]["operation"] == "copy"
        assert changeset.file_operations[0]["src"] == "/old/path"
        assert changeset.file_operations[0]["dst"] == "/new/path"

    def test_changeset_summary_empty(self) -> None:
        """Test changeset summary with no changes."""
        changeset = ChangeSet()
        summary = changeset.summary()

        assert "=== Change Summary ===" in summary
        assert (
            summary == "=== Change Summary ==="
        )  # Only header, no newlines for empty changeset

    def test_changeset_summary_with_changes(self, sample_entry: BibEntry) -> None:
        """Test changeset summary with various changes."""
        changeset = ChangeSet()

        # Add some changes
        changeset.add_entry(sample_entry)
        changeset.remove_entry(sample_entry)

        updated_entry = sample_entry.copy()
        updated_entry.update_field("title", "Updated Title")
        changeset.update_entry(sample_entry, updated_entry)

        changeset.add_file_operation("copy", src="/old", dst="/new")

        summary = changeset.summary()

        assert "Added 1 entries:" in summary
        assert "Removed 1 entries:" in summary
        assert "Updated 1 entries:" in summary
        assert "File operations (1):" in summary
        assert "test2023example" in summary
        assert "Copy: /old → /new" in summary


class TestRepositoryInitialization:
    """Test Repository initialization and basic properties."""

    def test_repository_initialization(self, temp_bibtex_dir: Path) -> None:
        """Test repository initialization."""
        repo = Repository(temp_bibtex_dir)

        assert repo.root_path == temp_bibtex_dir
        assert repo.root == temp_bibtex_dir  # Test backward compatibility alias
        assert repo.bibtex_path == temp_bibtex_dir / "bibtex"
        assert not repo.is_dry_run
        assert repo.entries_cache == {}
        assert repo.changeset is None

    def test_repository_initialization_string_path(self, temp_bibtex_dir: Path) -> None:
        """Test repository initialization with string path."""
        repo = Repository(temp_bibtex_dir)

        assert repo.root_path == temp_bibtex_dir
        assert isinstance(repo.root_path, Path)

    def test_dry_run_toggle(self, temp_bibtex_dir: Path) -> None:
        """Test enabling and disabling dry-run mode."""
        repo = Repository(temp_bibtex_dir)

        # Initially disabled
        assert not repo.is_dry_run
        assert repo.changeset is None

        # Enable dry-run
        repo.enable_dry_run()
        assert repo.is_dry_run
        assert repo.changeset is not None
        assert isinstance(repo.changeset, ChangeSet)

        # Disable dry-run
        repo.disable_dry_run()
        assert not repo.is_dry_run
        assert repo.changeset is None


class TestRepositoryFileOperations:
    """Test Repository file loading and parsing operations."""

    def test_load_entries_empty_repository(self, temp_bibtex_dir: Path) -> None:
        """Test loading entries from empty repository."""
        repo = Repository(temp_bibtex_dir)
        entries = repo.load_entries()

        assert entries == []
        assert repo.entries_cache == {}

    def test_load_entries_with_files(self, populated_repo: Repository) -> None:
        """Test loading entries from repository with files."""
        entries = populated_repo.load_entries()

        assert len(entries) == 3  # 2 articles + 1 book
        assert len(populated_repo.entries_cache) == 2  # 2 files

        # Check entries loaded correctly
        keys = [entry.key for entry in entries]
        assert "sample2023" in keys
        assert "another2023" in keys
        assert "testbook2023" in keys

    def test_load_entries_caching(self, populated_repo: Repository) -> None:
        """Test that load_entries uses caching properly."""
        # First load
        entries1 = populated_repo.load_entries()
        cache_after_first = dict(populated_repo.entries_cache)

        # Second load (should use cache)
        entries2 = populated_repo.load_entries()

        assert entries1 == entries2
        assert populated_repo.entries_cache == cache_after_first

    def test_load_entries_force_reload(self, populated_repo: Repository) -> None:
        """Test force reloading entries."""
        # Load once to populate cache
        populated_repo.load_entries()
        assert len(populated_repo.entries_cache) > 0

        # Mock load_file to verify it's called on force reload
        with patch.object(populated_repo, "load_file") as mock_load:
            mock_load.return_value = []
            populated_repo.load_entries(force_reload=True)

            # Should have called load_file for each .bib file
            assert mock_load.call_count >= 1

    def test_get_all_entries_alias(self, populated_repo: Repository) -> None:
        """Test get_all_entries is alias for load_entries."""
        entries1 = populated_repo.load_entries()
        entries2 = populated_repo.get_all_entries()

        assert entries1 == entries2

    def testload_file_nonexistent(self, temp_bibtex_dir: Path):
        """Test loading from non-existent file."""
        repo = Repository(temp_bibtex_dir)
        nonexistent_file = temp_bibtex_dir / "nonexistent.bib"

        entries = repo.load_file(nonexistent_file)
        assert entries == []

    def testload_file_invalid_bibtex(self, temp_bibtex_dir: Path):
        """Test loading file with invalid BibTeX content."""
        repo = Repository(temp_bibtex_dir)
        invalid_file = temp_bibtex_dir / "invalid.bib"
        invalid_file.write_text("This is not valid BibTeX")

        # Should handle gracefully and return empty list
        entries = repo.load_file(invalid_file)
        assert entries == []

    def test_get_entries_by_file(self, populated_repo: Repository) -> None:
        """Test getting entries from specific file."""
        articles_file = populated_repo.bibtex_path / "by-type" / "article.bib"
        entries = populated_repo.get_entries_by_file(articles_file)

        assert len(entries) == 2
        keys = [entry.key for entry in entries]
        assert "sample2023" in keys
        assert "another2023" in keys

        # All entries should have correct source file
        for entry in entries:
            assert entry.source_file == articles_file

    def test_get_entries_by_file_caching(self, populated_repo: Repository) -> None:
        """Test that get_entries_by_file caches results."""
        articles_file = populated_repo.bibtex_path / "by-type" / "article.bib"

        # First call should load and cache
        entries1 = populated_repo.get_entries_by_file(articles_file)
        assert articles_file in populated_repo.entries_cache

        # Second call should use cache
        entries2 = populated_repo.get_entries_by_file(articles_file)
        assert entries1 == entries2

    def test_load_entries_from_file_alias(self, populated_repo: Repository) -> None:
        """Test load_entries_from_file is alias for get_entries_by_file."""
        articles_file = populated_repo.bibtex_path / "by-type" / "article.bib"

        entries1 = populated_repo.get_entries_by_file(articles_file)
        entries2 = populated_repo.load_entries_from_file(articles_file)

        assert entries1 == entries2


class TestRepositoryEntryOperations:
    """Test Repository CRUD operations for entries."""

    def test_get_entry_found(self, populated_repo: Repository) -> None:
        """Test getting an existing entry."""
        entry = populated_repo.get_entry("sample2023")

        assert entry is not None
        assert entry.key == "sample2023"
        assert entry.entry_type == "article"
        assert entry.fields["title"] == "Sample Article"

    def test_get_entry_not_found(self, populated_repo: Repository) -> None:
        """Test getting a non-existent entry."""
        entry = populated_repo.get_entry("nonexistent2023")
        assert entry is None

    def test_add_entry_success(
        self, temp_bibtex_dir: Path, sample_entry: BibEntry
    ) -> None:
        """Test successfully adding a new entry."""
        repo = Repository(temp_bibtex_dir)

        # Add entry
        repo.add_entry(sample_entry)

        # Verify it was added
        retrieved = repo.get_entry("test2023example")
        assert retrieved is not None
        assert retrieved.key == sample_entry.key
        assert retrieved.fields == sample_entry.fields

        # Verify target file was created and updated
        target_file = repo.find_target_file("article")
        assert target_file.exists()

    def test_add_entry_with_target_file(
        self, temp_bibtex_dir: Path, sample_entry: BibEntry
    ) -> None:
        """Test adding entry to specific target file."""
        repo = Repository(temp_bibtex_dir)
        target_file = temp_bibtex_dir / "bibtex" / "custom.bib"

        repo.add_entry(sample_entry, target_file)

        # Verify entry was added to correct file
        entries = repo.get_entries_by_file(target_file)
        assert len(entries) == 1
        assert entries[0].key == sample_entry.key

    def test_add_entry_duplicate_key(self, populated_repo: Repository) -> None:
        """Test adding entry with duplicate key raises error."""
        # Ensure entries are loaded first
        entries = populated_repo.load_entries()
        assert len(entries) > 0

        # Try to add entry with same key as existing one
        duplicate_entry = BibEntry(
            key="sample2023",  # Duplicate key
            entry_type="book",
            fields={"title": "Duplicate", "author": "Author", "year": "2023"},
            source_file=Path("test.bib"),
        )

        with pytest.raises(ValueError, match="already exists"):
            populated_repo.add_entry(duplicate_entry)

    def test_remove_entry_success(self, populated_repo: Repository) -> None:
        """Test successfully removing an entry."""
        # Verify entry exists first
        entry = populated_repo.get_entry("sample2023")
        assert entry is not None

        # Remove entry
        removed = populated_repo.remove_entry("sample2023")

        assert removed is not None
        assert removed.key == "sample2023"

        # Verify entry is gone
        assert populated_repo.get_entry("sample2023") is None

    def test_remove_entry_not_found(self, populated_repo: Repository) -> None:
        """Test removing non-existent entry."""
        removed = populated_repo.remove_entry("nonexistent2023")
        assert removed is None

    def test_update_entry_success(self, populated_repo: Repository) -> None:
        """Test successfully updating an entry."""
        updates: dict[str, str | None] = {
            "title": "Updated Title",
            "note": "Added note",
        }

        updated = populated_repo.update_entry("sample2023", updates)

        assert updated is not None
        assert updated.fields["title"] == "Updated Title"
        assert updated.fields["note"] == "Added note"
        assert updated.fields["author"] == "Sample Author"  # Unchanged field

        # Verify change persisted
        retrieved = populated_repo.get_entry("sample2023")
        assert retrieved is not None
        assert retrieved.fields["title"] == "Updated Title"

    def test_update_entry_remove_fields(self, populated_repo: Repository) -> None:
        """Test updating entry by removing fields."""
        updates = {
            "journal": None,  # Remove journal field
            "title": "New Title",  # Update title
        }

        updated = populated_repo.update_entry("sample2023", updates)

        assert updated is not None
        assert "journal" not in updated.fields
        assert updated.fields["title"] == "New Title"

    def test_update_entry_not_found(self, populated_repo: Repository) -> None:
        """Test updating non-existent entry."""
        updates: dict[str, str | None] = {"title": "New Title"}
        updated = populated_repo.update_entry("nonexistent2023", updates)

        assert updated is None

    def test_move_entry_success(self, populated_repo: Repository) -> None:
        """Test successfully moving entry to different file."""
        target_file = populated_repo.bibtex_path / "by-type" / "moved.bib"

        moved = populated_repo.move_entry("sample2023", target_file)

        assert moved is not None
        assert moved.source_file == target_file

        # Verify entry is in new file
        entries_in_target = populated_repo.get_entries_by_file(target_file)
        assert any(e.key == "sample2023" for e in entries_in_target)

        # Verify entry is not in original file
        original_file = populated_repo.bibtex_path / "by-type" / "article.bib"
        entries_in_original = populated_repo.get_entries_by_file(original_file)
        assert not any(e.key == "sample2023" for e in entries_in_original)

    def test_move_entry_same_file(self, populated_repo: Repository) -> None:
        """Test moving entry to same file (no-op)."""
        original_file = populated_repo.bibtex_path / "by-type" / "article.bib"

        moved = populated_repo.move_entry("sample2023", original_file)

        assert moved is not None
        assert moved.source_file == original_file

    def test_move_entry_not_found(self, populated_repo: Repository) -> None:
        """Test moving non-existent entry."""
        target_file = populated_repo.bibtex_path / "target.bib"
        moved = populated_repo.move_entry("nonexistent2023", target_file)

        assert moved is None


class TestRepositoryQueryOperations:
    """Test Repository query and filtering operations."""

    def test_get_entries_by_type(self, populated_repo: Repository) -> None:
        """Test getting entries by type."""
        articles = populated_repo.get_entries_by_type("article")
        books = populated_repo.get_entries_by_type("book")
        misc = populated_repo.get_entries_by_type("misc")

        assert len(articles) == 2
        assert len(books) == 1
        assert len(misc) == 0

        # Verify all returned entries have correct type
        for article in articles:
            assert article.entry_type == "article"

        for book in books:
            assert book.entry_type == "book"

    def test_find_target_file(self, temp_bibtex_dir: Path) -> None:
        """Test finding target file for entry type."""
        repo = Repository(temp_bibtex_dir)

        article_file = repo.find_target_file("article")
        book_file = repo.find_target_file("book")

        assert article_file == repo.bibtex_path / "by-type" / "article.bib"
        assert book_file == repo.bibtex_path / "by-type" / "book.bib"

    def test_get_stats(self, populated_repo: Repository) -> None:
        """Test getting repository statistics."""
        stats = populated_repo.get_stats()

        assert stats["total_entries"] == 3
        assert stats["total_files"] == 2
        assert stats["article"] == 2
        assert stats["book"] == 1


class TestRepositoryDryRunMode:
    """Test Repository dry-run functionality."""

    def test_dry_run_add_entry(
        self, temp_bibtex_dir: Path, sample_entry: BibEntry
    ) -> None:
        """Test adding entry in dry-run mode."""
        repo = Repository(temp_bibtex_dir)
        repo.enable_dry_run()

        repo.add_entry(sample_entry)

        # Entry should not actually exist
        assert repo.get_entry("test2023example") is None

        # But should be tracked in changeset
        assert repo.changeset is not None
        assert len(repo.changeset.added) == 1
        assert repo.changeset.added[0].key == "test2023example"

    def test_dry_run_remove_entry(self, populated_repo: Repository) -> None:
        """Test removing entry in dry-run mode."""
        populated_repo.enable_dry_run()

        removed = populated_repo.remove_entry("sample2023")

        # Entry should still exist
        assert populated_repo.get_entry("sample2023") is not None

        # But removal should be tracked
        assert removed is not None
        assert populated_repo.changeset is not None
        assert len(populated_repo.changeset.removed) == 1

    def test_dry_run_update_entry(self, populated_repo: Repository) -> None:
        """Test updating entry in dry-run mode."""
        populated_repo.enable_dry_run()

        updates: dict[str, str | None] = {"title": "Dry Run Title"}
        updated = populated_repo.update_entry("sample2023", updates)

        # Original entry should be unchanged
        original = populated_repo.get_entry("sample2023")
        assert original is not None
        assert original.fields["title"] == "Sample Article"

        # Update should be tracked
        assert updated is not None
        assert populated_repo.changeset is not None
        assert len(populated_repo.changeset.updated) == 1

    def test_dry_run_changeset_summary(
        self, temp_bibtex_dir: Path, sample_entry: BibEntry
    ) -> None:
        """Test changeset summary in dry-run mode."""
        repo = Repository(temp_bibtex_dir)
        repo.enable_dry_run()

        # Perform some operations
        repo.add_entry(sample_entry)

        assert repo.changeset is not None
        summary = repo.changeset.summary()
        assert "Added 1 entries:" in summary
        assert "test2023example" in summary


class TestRepositoryFileManagement:
    """Test Repository file writing and atomic operations."""

    def test_save_entries_new_file(self, temp_bibtex_dir: Path) -> None:
        """Test saving entries to new file."""
        repo = Repository(temp_bibtex_dir)
        entries = [
            BibEntry(
                key="test1",
                entry_type="article",
                fields={"title": "Test 1", "author": "Author 1", "year": "2023"},
                source_file=Path("test.bib"),
            ),
            BibEntry(
                key="test2",
                entry_type="article",
                fields={"title": "Test 2", "author": "Author 2", "year": "2023"},
                source_file=Path("test.bib"),
            ),
        ]

        target_file = temp_bibtex_dir / "bibtex" / "test.bib"
        repo.save_entries(entries, target_file)

        # Verify file was created and contains entries
        assert target_file.exists()
        content = target_file.read_text()
        assert "test1" in content
        assert "test2" in content
        assert "@article" in content

    def test_save_entries_overwrite(self, populated_repo: Repository) -> None:
        """Test overwriting existing file."""
        articles_file = populated_repo.bibtex_path / "by-type" / "article.bib"

        new_entries = [
            BibEntry(
                key="new2023",
                entry_type="article",
                fields={"title": "New Article", "author": "New Author", "year": "2023"},
                source_file=articles_file,
            )
        ]

        populated_repo.save_entries(new_entries, articles_file)

        # Verify old entries are gone and new entry exists
        entries = populated_repo.get_entries_by_file(articles_file)
        assert len(entries) == 1
        assert entries[0].key == "new2023"

    def test_save_entries_dry_run(
        self, temp_bibtex_dir: Path, sample_entry: BibEntry
    ) -> None:
        """Test saving entries in dry-run mode."""
        repo = Repository(temp_bibtex_dir)
        repo.enable_dry_run()

        target_file = temp_bibtex_dir / "bibtex" / "test.bib"
        repo.save_entries([sample_entry], target_file)

        # File should not be created
        assert not target_file.exists()

        # Changes should be tracked
        assert repo.changeset is not None
        assert len(repo.changeset.added) == 1


class TestRepositoryErrorHandling:
    """Test Repository error handling and edge cases."""

    def test_add_entry_creates_directories(
        self, temp_bibtex_dir: Path, sample_entry: BibEntry
    ) -> None:
        """Test that add_entry creates necessary directories."""
        repo = Repository(temp_bibtex_dir)

        # Remove by-type directory
        by_type_dir = temp_bibtex_dir / "bibtex" / "by-type"
        if by_type_dir.exists():
            import shutil

            shutil.rmtree(by_type_dir)

        repo.add_entry(sample_entry)

        # Verify directories were created
        assert by_type_dir.exists()
        target_file = by_type_dir / "article.bib"
        assert target_file.exists()

    def test_load_entries_with_parsing_errors(self, temp_bibtex_dir: Path) -> None:
        """Test handling files with parsing errors."""
        repo = Repository(temp_bibtex_dir)

        # Create file with partially valid content
        broken_file = temp_bibtex_dir / "bibtex" / "broken.bib"
        broken_file.write_text("""
@article{valid2023,
  title = {Valid Entry},
  author = {Valid Author},
  year = {2023}
}

@article{broken2023
  title = Valid Entry},  // Missing opening brace
  author = {Broken Author},
  year = {2023}
}
""")

        # Should handle gracefully and return valid entries
        entries = repo.load_entries()

        # Should get at least the valid entry
        valid_keys = [e.key for e in entries if e.key == "valid2023"]
        assert len(valid_keys) == 1

    def test_remove_entry_from_cache_invalidation(
        self, populated_repo: Repository
    ) -> None:
        """Test cache invalidation after removing entry."""
        # Load entries to populate cache
        populated_repo.load_entries()
        assert len(populated_repo.entries_cache) > 0

        # Remove entry
        populated_repo.remove_entry("sample2023")

        # Cache should be updated
        articles_file = populated_repo.bibtex_path / "by-type" / "article.bib"
        cached_entries = populated_repo.entries_cache[articles_file]
        keys = [e.key for e in cached_entries]
        assert "sample2023" not in keys

    def test_repository_with_empty_files(self, temp_bibtex_dir: Path) -> None:
        """Test repository operations with empty .bib files."""
        repo = Repository(temp_bibtex_dir)

        # Create empty .bib file
        empty_file = temp_bibtex_dir / "bibtex" / "empty.bib"
        empty_file.write_text("")

        entries = repo.load_entries()
        assert entries == []

    def test_repository_concurrent_operations(self, populated_repo: Repository) -> None:
        """Test that operations work correctly with cache consistency."""
        # Load entries
        initial_entries = populated_repo.load_entries()
        initial_count = len(initial_entries)

        # Add entry in one "session"
        new_entry = BibEntry(
            key="concurrent2023",
            entry_type="article",
            fields={"title": "Concurrent", "author": "Author", "year": "2023"},
            source_file=Path("test.bib"),
        )
        populated_repo.add_entry(new_entry)

        # Load entries again - should see the new entry
        updated_entries = populated_repo.load_entries()
        assert len(updated_entries) == initial_count + 1

        # Verify new entry is accessible
        assert populated_repo.get_entry("concurrent2023") is not None


class TestRepositoryIntegration:
    """Integration tests combining multiple repository operations."""

    def test_full_crud_workflow(self, temp_bibtex_dir: Path) -> None:
        """Test complete CRUD workflow."""
        repo = Repository(temp_bibtex_dir)

        # Create
        entry = BibEntry(
            key="workflow2023",
            entry_type="article",
            fields={"title": "Workflow Test", "author": "Test Author", "year": "2023"},
            source_file=Path("test.bib"),
        )
        repo.add_entry(entry)

        # Read
        retrieved = repo.get_entry("workflow2023")
        assert retrieved is not None
        assert retrieved.fields["title"] == "Workflow Test"

        # Update
        updates: dict[str, str | None] = {
            "title": "Updated Workflow",
            "note": "Added note",
        }
        updated = repo.update_entry("workflow2023", updates)
        assert updated is not None
        assert updated.fields["title"] == "Updated Workflow"
        assert updated.fields["note"] == "Added note"

        # Delete
        removed = repo.remove_entry("workflow2023")
        assert removed is not None
        assert repo.get_entry("workflow2023") is None

    def test_bulk_operations(self, temp_bibtex_dir: Path) -> None:
        """Test handling multiple entries efficiently."""
        repo = Repository(temp_bibtex_dir)

        # Add multiple entries
        entries = []
        for i in range(10):
            entry = BibEntry(
                key=f"bulk{i:03d}",
                entry_type="article",
                fields={
                    "title": f"Bulk Entry {i}",
                    "author": f"Author {i}",
                    "year": "2023",
                },
                source_file=Path("test.bib"),
            )
            entries.append(entry)
            repo.add_entry(entry)

        # Verify all entries exist
        all_entries = repo.load_entries()
        assert len(all_entries) == 10

        # Test type filtering
        articles = repo.get_entries_by_type("article")
        assert len(articles) == 10

        # Test stats
        stats = repo.get_stats()
        assert stats["total_entries"] == 10
        assert stats["article"] == 10

    def test_cross_file_operations(self, populated_repo: Repository) -> None:
        """Test operations across multiple files."""
        # Get entry from one file
        entry = populated_repo.get_entry("sample2023")
        assert entry is not None
        assert entry.source_file.name == "article.bib"

        # Move to different file
        target_file = populated_repo.bibtex_path / "moved.bib"
        moved = populated_repo.move_entry("sample2023", target_file)

        assert moved is not None
        assert moved.source_file == target_file

        # Verify it's accessible by key regardless of file
        retrieved = populated_repo.get_entry("sample2023")
        assert retrieved is not None
        assert retrieved.source_file == target_file

    def test_dry_run_comprehensive(self, populated_repo: Repository) -> None:
        """Test comprehensive dry-run operations."""
        # Load entries first to populate cache
        initial_entries = populated_repo.load_entries()
        len(initial_entries)

        # Verify entries exist before dry-run
        assert populated_repo.get_entry("sample2023") is not None
        assert populated_repo.get_entry("another2023") is not None

        populated_repo.enable_dry_run()

        # Perform various operations
        new_entry = BibEntry(
            key="dryrun2023",
            entry_type="book",
            fields={"title": "Dry Run Book", "author": "Author", "year": "2023"},
            source_file=Path("test.bib"),
        )
        populated_repo.add_entry(new_entry)
        populated_repo.update_entry("sample2023", {"title": "Dry Run Update"})
        populated_repo.remove_entry("another2023")

        # Verify original state unchanged (entries should still be accessible)
        assert populated_repo.get_entry("dryrun2023") is None
        original = populated_repo.get_entry("sample2023")
        assert original is not None, "sample2023 should still exist in dry-run mode"
        assert original.fields["title"] == "Sample Article"
        assert populated_repo.get_entry("another2023") is not None

        # Verify changeset tracks everything
        changeset = populated_repo.changeset
        assert changeset is not None
        assert len(changeset.added) == 1
        assert len(changeset.updated) == 1
        assert len(changeset.removed) == 1

        summary = changeset.summary()
        assert "dryrun2023" in summary
        assert "sample2023" in summary
        assert "another2023" in summary
