"""Command-line interface for bibliography management."""

import sys
from pathlib import Path

import click

from .models import BibEntry, ValidationError
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


def find_bib_files(root: Path) -> list[Path]:
    """Find all .bib files in the bibtex directory."""
    bibtex_dir = root / 'bibtex'
    if not bibtex_dir.exists():
        return []
    return sorted(bibtex_dir.rglob('*.bib'))


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
@click.option('--root', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project root directory')
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
@click.option('--root', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project root directory')
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
@click.option('--root', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project root directory')
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
@click.option('--root', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project root directory')
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


if __name__ == '__main__':
    cli()
