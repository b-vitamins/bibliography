"""Command-line interface for bibliography management."""

import sys
from pathlib import Path

import click
from rich.console import Console

from .models import BibEntry, ValidationError
from .operations import add_entry, add_from_file, remove_entry, update_entry
from .operations import move_pdf as move_pdf_operation
from .report import (
    generate_full_report,
    report_duplicate_keys,
    report_missing_fields,
    report_missing_files,
)
from .repository import Repository
from .validators import (
    check_duplicates,
    check_mandatory_fields,
    check_paths,
    load_bibliography,
)


@click.group()
@click.version_option()
def cli() -> None:
    """Bibliography management system."""
    pass


@cli.group()
def check() -> None:
    """Run validation checks on bibliography files."""
    pass


@cli.group()
def report() -> None:
    """Generate detailed validation reports."""
    pass


def find_bib_files(root: Path) -> list[Path]:
    """Find all .bib files in the bibtex directory."""
    bibtex_dir = root / "bibtex"
    if not bibtex_dir.exists():
        return []
    return sorted(bibtex_dir.rglob("*.bib"))


def load_all_entries(root: Path) -> list[BibEntry]:
    """Load all bibliography entries from the project."""
    entries = []
    bib_files = find_bib_files(root)

    for bib_file in bib_files:
        try:
            entries.extend(load_bibliography(bib_file))
        except ValueError as e:
            click.echo(f"ERROR: {e}", err=True)
            sys.exit(2)

    return entries


def print_errors(errors: list[ValidationError], title: str) -> None:
    """Print validation errors in a consistent format."""
    if not errors:
        return

    click.echo(f"\n{title}:")
    for error in errors:
        click.echo(f"  {error}")


@check.command()
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def paths(root: Path) -> None:
    """Verify all file paths exist."""
    entries = load_all_entries(root)
    errors = check_paths(entries)

    click.echo(f"Checking {len(entries)} entries...")

    if errors:
        print_errors(errors, "Missing files")
        click.echo(f"\nValidation FAILED: {len(errors)} missing file(s)")
        sys.exit(1)
    else:
        click.echo("Validation PASSED: All file paths are valid")


@check.command()
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def duplicates(root: Path) -> None:
    """Check for duplicate keys and file paths."""
    entries = load_all_entries(root)
    errors = check_duplicates(entries)

    click.echo(f"Checking {len(entries)} entries...")

    if errors:
        print_errors(errors, "Duplicates found")
        click.echo(f"\nValidation FAILED: {len(errors)} duplicate(s)")
        sys.exit(1)
    else:
        click.echo("Validation PASSED: No duplicates found")


@check.command()
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def fields(root: Path) -> None:
    """Validate mandatory fields are present."""
    entries = load_all_entries(root)
    errors = check_mandatory_fields(entries)

    click.echo(f"Checking {len(entries)} entries...")

    if errors:
        print_errors(errors, "Field validation errors")
        click.echo(f"\nValidation FAILED: {len(errors)} error(s)")
        sys.exit(1)
    else:
        click.echo("Validation PASSED: All mandatory fields present")


@check.command()
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def all(root: Path) -> None:
    """Run all validation checks."""
    entries = load_all_entries(root)
    click.echo(f"Running all checks on {len(entries)} entries...")

    # Run all validators
    all_errors = []

    path_errors = check_paths(entries)
    if path_errors:
        print_errors(path_errors, "Missing files")
        all_errors.extend(path_errors)

    dup_errors = check_duplicates(entries)
    if dup_errors:
        print_errors(dup_errors, "Duplicates")
        all_errors.extend(dup_errors)

    field_errors = check_mandatory_fields(entries)
    if field_errors:
        print_errors(field_errors, "Field errors")
        all_errors.extend(field_errors)

    # Summary
    if all_errors:
        click.echo(f"\nValidation FAILED: {len(all_errors)} total error(s)")
        sys.exit(1)
    else:
        click.echo("\nValidation PASSED: All checks passed")


@report.command("duplicates")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def report_duplicates_cmd(root: Path) -> None:
    """Report duplicate citation keys with full context."""
    entries = load_all_entries(root)
    click.echo(report_duplicate_keys(entries))


@report.command("fields")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def report_fields_cmd(root: Path) -> None:
    """Report missing mandatory fields with entry context."""
    entries = load_all_entries(root)
    click.echo(report_missing_fields(entries))


@report.command("paths")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def report_paths_cmd(root: Path) -> None:
    """Report missing files with entry context."""
    entries = load_all_entries(root)
    click.echo(report_missing_files(entries))


@report.command("all")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def report_all_cmd(root: Path) -> None:
    """Generate comprehensive validation report."""
    entries = load_all_entries(root)
    click.echo(generate_full_report(entries))


# CRUD Operations


@cli.command("add")
@click.option("--type", "-t", help="Entry type (e.g., article, book)")
@click.option("--key", "-k", help="Citation key")
@click.option(
    "--from-file",
    "-f",
    type=click.Path(exists=True, path_type=Path),
    help="Import from .bib file",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def add_cmd(
    type: str | None, key: str | None, from_file: Path | None, dry_run: bool, root: Path
) -> None:
    """Add a new bibliography entry."""
    repo = Repository(root)

    if from_file:
        # Import from file
        entries = add_from_file(repo, from_file, dry_run=dry_run)
        sys.exit(0 if entries else 1)
    else:
        # Interactive add
        entry = add_entry(repo, entry_type=type, key=key, dry_run=dry_run)
        sys.exit(0 if entry else 1)


@cli.command("remove")
@click.argument("key")
@click.option("--remove-pdf", is_flag=True, help="Also delete the PDF file")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def remove_cmd(
    key: str, remove_pdf: bool, force: bool, dry_run: bool, root: Path
) -> None:
    """Remove a bibliography entry."""
    repo = Repository(root)
    entry = remove_entry(repo, key, remove_pdf=remove_pdf, force=force, dry_run=dry_run)
    sys.exit(0 if entry else 1)


@cli.command("update")
@click.argument("key")
@click.option(
    "--set", "-s", multiple=True, help="Set field value (format: field=value)"
)
@click.option("--remove-field", "-r", multiple=True, help="Remove a field")
@click.option(
    "--move-pdf", type=click.Path(path_type=Path), help="Move PDF to new location"
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def update_cmd(
    key: str,
    set: tuple[str, ...],
    remove_field: tuple[str, ...],
    move_pdf: Path | None,
    dry_run: bool,
    root: Path,
) -> None:
    """Update a bibliography entry."""
    repo = Repository(root)

    if move_pdf:
        # Handle PDF move
        entry = move_pdf_operation(repo, key, move_pdf, dry_run=dry_run)
        sys.exit(0 if entry else 1)

    # Parse field updates
    updates = {}
    for field_update in set:
        if "=" not in field_update:
            click.echo(
                f"Error: Invalid format '{field_update}', use field=value", err=True
            )
            sys.exit(1)
        field, value = field_update.split("=", 1)
        updates[field] = value

    # Add field removals
    for field in remove_field:
        updates[field] = None

    # Interactive mode if no updates specified
    interactive = not updates and not move_pdf

    entry = update_entry(
        repo, key, updates=updates, interactive=interactive, dry_run=dry_run
    )
    sys.exit(0 if entry else 1)


@cli.command("list")
@click.option("--type", "-t", help="Filter by entry type")
@click.option("--author", "-a", help="Filter by author")
@click.option("--year", "-y", help="Filter by year")
@click.option("--search", "-s", help="Search all fields")
@click.option("--limit", "-n", type=int, help="Limit number of results")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["short", "full", "keys"]),
    default="short",
    help="Output format",
)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def list_cmd(
    type: str | None,
    author: str | None,
    year: str | None,
    search: str | None,
    limit: int | None,
    format: str,
    root: Path,
) -> None:
    """List bibliography entries."""
    repo = Repository(root)
    entries = repo.load_entries()

    # Filter entries
    results = entries.copy()

    if type:
        results = [e for e in results if e.entry_type == type]
    if author:
        results = [
            e
            for e in results
            if author.lower() in (e.fields.get("author") or "").lower()
        ]
    if year:
        results = [e for e in results if e.fields.get("year") == str(year)]
    if search:
        results = [e for e in results if search.lower() in str(e).lower()]

    # Sort by key
    results.sort(key=lambda e: e.key)

    # Apply limit
    if limit:
        results = results[:limit]

    if not results:
        click.echo("No entries found")
        return

    # Display results
    if format == "keys":
        for entry in results:
            click.echo(entry.key)
    elif format == "full":
        for i, entry in enumerate(results):
            if i > 0:
                click.echo("\n" + "-" * 40 + "\n")
            click.echo(entry.to_bibtex())
    else:  # short format
        click.echo(f"Found {len(results)} entries:\n")
        for entry in results:
            title = (entry.fields.get("title") or "No title")[:60]
            author = (
                entry.fields.get("author") or entry.fields.get("editor") or "No author"
            )[:30]
            year = entry.fields.get("year", "????")
            click.echo(f"{entry.key:30} {year}  {author:30}  {title}")


@cli.command("search")
@click.argument("patterns", nargs=-1, required=True)
@click.option("--limit", "-n", type=int, default=20, help="Maximum results")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "bibtex", "json", "keys"]),
    default="table",
    help="Output format",
)
@click.option(
    "--sort",
    "-s",
    type=click.Choice(["relevance", "year", "author", "title"]),
    default="relevance",
    help="Sort order",
)
@click.option("--stats", is_flag=True, help="Show search statistics")
@click.option(
    "--database",
    type=click.Path(path_type=Path),
    help="Custom database path",
)
def search_cmd(
    patterns: tuple[str, ...],
    limit: int,
    format: str,
    sort: str,
    stats: bool,
    database: Path | None,
) -> None:
    """Search bibliography using FTS5 full-text search.

    Examples:

        # Natural language search
        bib search quantum computing

        # Field-specific search
        bib search author:feynman

        # Boolean operators
        bib search "quantum AND computing"

        # Wildcards
        bib search quan*

        # Phrase search
        bib search "path integral"
    """
    from .scripts.search import search_command

    search_command(list(patterns), limit, format, sort, stats, database)


@cli.command("locate")
@click.argument("pattern")
@click.option("--glob", is_flag=True, help="Use glob pattern matching")
@click.option("--basename", is_flag=True, help="Search only file basenames")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "paths", "keys"]),
    default="table",
    help="Output format",
)
@click.option(
    "--database",
    type=click.Path(path_type=Path),
    help="Custom database path",
)
def locate_cmd(
    pattern: str,
    glob: bool,
    basename: bool,
    format: str,
    database: Path | None,
) -> None:
    """Locate entries by file path (like 'guix locate').

    Examples:

        # Find entries containing specific file
        bib locate thesis-1942-feynman.pdf

        # Find by directory
        bib locate /home/b/documents/misc/

        # Use glob patterns
        bib locate --glob "*.pdf"

        # Search only basenames
        bib locate --basename quantum.pdf
    """
    from .scripts.locate import locate_command

    locate_command(pattern, glob, basename, format, database)


@cli.command("show")
@click.argument("key")
@click.option(
    "--database",
    type=click.Path(path_type=Path),
    help="Custom database path",
)
def show_cmd(key: str, database: Path | None) -> None:
    """Show specific entry by citation key.

    Examples:

        # Display entry details
        bib show feynman1942principle

        # Show with custom database
        bib show --database /path/to/db.sqlite key123
    """
    from .scripts.search import show_command

    show_command(key, database)


@cli.group()
def index() -> None:
    """Manage search index."""
    pass


@index.command("build")
@click.option("--clear", is_flag=True, help="Clear existing index")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress output")
@click.option(
    "--database",
    type=click.Path(path_type=Path),
    help="Custom database path",
)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def index_build_cmd(
    clear: bool, quiet: bool, database: Path | None, root: Path
) -> None:
    """Build search index from .bib files."""
    from .index import create_index_builder

    repo = Repository(root)
    builder = create_index_builder(repo, database)

    builder.build_index(clear_existing=clear, show_progress=not quiet)


@index.command("update")
@click.option(
    "--files",
    "-f",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Specific files to update",
)
@click.option(
    "--database",
    type=click.Path(path_type=Path),
    help="Custom database path",
)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def index_update_cmd(
    files: tuple[Path, ...], database: Path | None, root: Path
) -> None:
    """Update search index for specific files or detect changes."""
    from .index import create_index_builder

    repo = Repository(root)
    builder = create_index_builder(repo, database)

    if files:
        builder.update_index(list(files))
    else:
        builder.update_index()


@index.command("status")
@click.option(
    "--database",
    type=click.Path(path_type=Path),
    help="Custom database path",
)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def index_status_cmd(database: Path | None, root: Path) -> None:
    """Show index status and statistics."""
    from .index import create_index_builder

    repo = Repository(root)
    builder = create_index_builder(repo, database)

    status = builder.get_index_status()

    console = Console()
    console.print("[bold]Search Index Status[/bold]\n")

    # Index status
    if status["up_to_date"]:
        console.print("✅ Index is up to date")
    else:
        console.print("⚠️  Index needs updating")

    console.print(f"Database entries: {status['db_entries']:,}")
    console.print(f"Repository entries: {status['repo_entries']:,}")
    console.print(f"Database size: {status['db_size_mb']:.1f} MB")
    console.print(f"FTS entries: {status['fts_entries']:,}\n")

    # Entries by type
    by_type = status.get("by_type")
    if by_type and isinstance(by_type, dict):
        console.print("[bold]Entries by type:[/bold]")
        for entry_type, count in sorted(by_type.items()):
            console.print(f"  {entry_type:15} {count:6,}")
        console.print()


@cli.command("stats")
@click.option(
    "--database",
    type=click.Path(path_type=Path),
    help="Custom database path",
)
def stats_cmd(database: Path | None) -> None:
    """Show database statistics."""
    from .scripts.search import stats_command

    stats_command(database)


if __name__ == "__main__":
    cli()
