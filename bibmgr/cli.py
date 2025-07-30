"""Command-line interface for bibliography management."""

import sys
from pathlib import Path

import click

from .models import BibEntry, ValidationError
from .operations import add_entry, add_from_file, remove_entry, update_entry
from .operations import move_pdf as move_pdf_operation
from .query import QueryBuilder
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


@cli.command("show")
@click.argument("key")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Project root directory",
)
def show_cmd(key: str, root: Path) -> None:
    """Show details of a bibliography entry."""
    repo = Repository(root)
    entry = repo.get_entry(key)

    if not entry:
        click.echo(f"Error: Entry '{key}' not found", err=True)
        sys.exit(1)

    # Display entry
    click.echo(f"\n{entry.to_bibtex()}\n")

    # Check if PDF exists
    if entry.file_path:
        if entry.file_path.exists():
            click.echo(f"PDF: {entry.file_path} ✓")
        else:
            click.echo(f"PDF: {entry.file_path} ✗ (missing)")


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

    # Build query
    qb = QueryBuilder(entries)
    query = qb.all()

    if type:
        query = query.where_type(type)
    if author:
        query = query.where("author", author, exact=False)
    if year:
        query = query.where("year", str(year))
    if search:
        query = query.where_any(search)
    if limit:
        query = query.limit(limit)

    # Sort by key
    query = query.order_by_key()

    # Execute query
    results = query.execute()

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
            title = entry.fields.get("title", "No title")[:60]
            author = entry.fields.get(
                "author", entry.fields.get("editor", "No author")
            )[:30]
            year = entry.fields.get("year", "????")
            click.echo(f"{entry.key:30} {year}  {author:30}  {title}")


if __name__ == "__main__":
    cli()
