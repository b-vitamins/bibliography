"""Command-line interface for bibliography management."""

import sys
from pathlib import Path

import click

from .fixers import (
    apply_fixes,
    fix_duplicate_keys,
    fix_missing_fields,
)
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


@cli.group()
def fix() -> None:
    """Fix validation errors in bibliography files."""
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


@fix.command('duplicates')
@click.option('--root', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project root directory')
@click.option('--dry-run/--no-dry-run', default=True,
              help='Show what would be fixed without making changes')
def fix_duplicates_cmd(root: Path, dry_run: bool) -> None:
    """Fix duplicate citation keys."""
    entries = load_all_entries(root)
    fixes = fix_duplicate_keys(entries)

    if not fixes:
        click.echo("No duplicate keys found to fix")
        return

    click.echo(f"Found {len(fixes)} duplicate key(s) to fix")

    # Apply fixes
    counts = apply_fixes(fixes, dry_run=dry_run)

    total_fixed = sum(counts.values())
    if dry_run:
        click.echo(f"\nDry run complete. Would fix {total_fixed} issue(s)")
    else:
        click.echo(f"\nFixed {total_fixed} issue(s)")


@fix.command('fields')
@click.option('--root', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project root directory')
@click.option('--dry-run/--no-dry-run', default=True,
              help='Show what would be fixed without making changes')
def fix_fields_cmd(root: Path, dry_run: bool) -> None:
    """Fix missing mandatory fields."""
    entries = load_all_entries(root)
    fixes = fix_missing_fields(entries)

    if not fixes:
        click.echo("No missing fields found to fix")
        return

    click.echo(f"Found {len(fixes)} missing field(s) to fix")

    # Apply fixes
    counts = apply_fixes(fixes, dry_run=dry_run)

    total_fixed = sum(counts.values())
    if dry_run:
        click.echo(f"\nDry run complete. Would fix {total_fixed} issue(s)")
    else:
        click.echo(f"\nFixed {total_fixed} issue(s)")


@fix.command('all')
@click.option('--root', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project root directory')
@click.option('--dry-run/--no-dry-run', default=True,
              help='Show what would be fixed without making changes')
def fix_all_cmd(root: Path, dry_run: bool) -> None:
    """Fix all validation errors."""
    entries = load_all_entries(root)

    all_fixes = []

    # Collect all fixes
    dup_fixes = fix_duplicate_keys(entries)
    if dup_fixes:
        click.echo(f"Found {len(dup_fixes)} duplicate key(s) to fix")
        all_fixes.extend(dup_fixes)

    field_fixes = fix_missing_fields(entries)
    if field_fixes:
        click.echo(f"Found {len(field_fixes)} missing field(s) to fix")
        all_fixes.extend(field_fixes)

    if not all_fixes:
        click.echo("No issues found to fix")
        return

    # Apply all fixes
    counts = apply_fixes(all_fixes, dry_run=dry_run)

    total_fixed = sum(counts.values())
    if dry_run:
        click.echo(f"\nDry run complete. Would fix {total_fixed} issue(s)")
    else:
        click.echo(f"\nFixed {total_fixed} issue(s)")


if __name__ == '__main__':
    cli()
