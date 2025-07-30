"""Remove operation for bibliography entries."""

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ..models import BibEntry
from ..repository import Repository

console = Console()


def display_entry(entry: BibEntry) -> None:
    """Display entry details in a formatted way."""
    table = Table(title=f"Entry: {entry.key}", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("Type", entry.entry_type)
    table.add_row("Key", entry.key)
    table.add_row("Source", str(entry.source_file))

    # Sort fields for display
    for field, value in sorted(entry.fields.items()):
        # Truncate long values
        display_value = value if len(value) <= 60 else value[:57] + "..."
        table.add_row(field, display_value)

    console.print(table)


def remove_entry(
    repo: Repository,
    key: str,
    remove_pdf: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> BibEntry | None:
    """Remove an entry from the repository."""
    if dry_run:
        repo.enable_dry_run()

    try:
        # Find the entry
        entry = repo.get_entry(key)
        if not entry:
            console.print(f"[red]Error: Entry '{key}' not found[/red]")
            return None

        # Display entry details
        console.print("\n[bold]Entry to remove:[/bold]")
        display_entry(entry)

        # Check for PDF file
        pdf_path = entry.file_path
        if pdf_path and pdf_path.exists():
            console.print(f"\n[yellow]PDF file: {pdf_path}[/yellow]")
            if remove_pdf:
                console.print("[red]This file will be DELETED[/red]")
            else:
                console.print("[green]This file will be kept[/green]")

        # Confirm removal
        if not force and not Confirm.ask("\nRemove this entry?", default=False):
            console.print("[yellow]Cancelled[/yellow]")
            return None

        # Remove from repository
        removed = repo.remove_entry(key)

        # Remove PDF if requested
        if remove_pdf and pdf_path and pdf_path.exists() and not dry_run:
            try:
                pdf_path.unlink()
                console.print(f"[green]✓ Deleted PDF: {pdf_path}[/green]")
            except Exception as e:
                console.print(f"[red]Error deleting PDF: {e}[/red]")

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes made[/yellow]")
            console.print(repo.changeset.summary() if repo.changeset else "")
            if remove_pdf and pdf_path and pdf_path.exists():
                console.print(f"Would delete: {pdf_path}")
        else:
            console.print(f"\n[green]✓ Entry '{key}' removed successfully[/green]")

        return removed

    finally:
        repo.disable_dry_run()


def remove_orphaned_entries(
    repo: Repository,
    dry_run: bool = False,
) -> list[BibEntry]:
    """Remove all entries with missing PDF files."""
    if dry_run:
        repo.enable_dry_run()

    try:
        # Find entries with missing files
        entries = repo.load_entries()
        orphaned = []

        for entry in entries:
            pdf_path = entry.file_path
            if pdf_path and not pdf_path.exists():
                orphaned.append(entry)

        if not orphaned:
            console.print("[green]No orphaned entries found[/green]")
            return []

        # Display orphaned entries
        console.print(f"\n[bold]Found {len(orphaned)} orphaned entries:[/bold]")

        table = Table(show_header=True)
        table.add_column("Key", style="cyan")
        table.add_column("Type")
        table.add_column("Missing File", style="red")

        for entry in orphaned:
            table.add_row(
                entry.key,
                entry.entry_type,
                str(entry.file_path) if entry.file_path else "N/A",
            )

        console.print(table)

        # Confirm removal
        if not Confirm.ask("\nRemove all orphaned entries?", default=False):
            console.print("[yellow]Cancelled[/yellow]")
            return []

        # Remove entries
        removed = []
        for entry in orphaned:
            if repo.remove_entry(entry.key):
                removed.append(entry)
                console.print(f"[green]Removed: {entry.key}[/green]")

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes made[/yellow]")
            console.print(repo.changeset.summary() if repo.changeset else "")
        else:
            console.print(f"\n[green]✓ Removed {len(removed)} orphaned entries[/green]")

        return removed

    finally:
        repo.disable_dry_run()


def remove_by_type(
    repo: Repository,
    entry_type: str,
    dry_run: bool = False,
) -> list[BibEntry]:
    """Remove all entries of a specific type."""
    if dry_run:
        repo.enable_dry_run()

    try:
        # Find entries of this type
        entries = repo.get_entries_by_type(entry_type)

        if not entries:
            console.print(f"[yellow]No entries of type '{entry_type}' found[/yellow]")
            return []

        # Display entries
        console.print(f"\n[bold]Found {len(entries)} {entry_type} entries:[/bold]")

        table = Table(show_header=True)
        table.add_column("Key", style="cyan")
        table.add_column("Title")
        table.add_column("Author/Editor")

        for entry in entries[:10]:  # Show first 10
            title = entry.fields.get("title", "")[:40]
            author = entry.fields.get("author", entry.fields.get("editor", ""))[:30]
            table.add_row(entry.key, title, author)

        if len(entries) > 10:
            table.add_row("...", f"... and {len(entries) - 10} more", "...")

        console.print(table)

        # Confirm removal
        console.print(
            f"\n[red]WARNING: This will remove ALL {entry_type} entries![/red]"
        )
        if not Confirm.ask("Are you sure?", default=False):
            console.print("[yellow]Cancelled[/yellow]")
            return []

        # Double confirm for safety
        confirm_text = f"remove all {len(entries)} {entry_type} entries"
        typed = Prompt.ask(f"Type '{confirm_text}' to confirm")
        if typed != confirm_text:
            console.print(
                "[yellow]Cancelled - confirmation text did not match[/yellow]"
            )
            return []

        # Remove entries
        removed = []
        for entry in entries:
            if repo.remove_entry(entry.key):
                removed.append(entry)
                console.print(f"[green]Removed: {entry.key}[/green]")

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes made[/yellow]")
            console.print(repo.changeset.summary() if repo.changeset else "")
        else:
            console.print(
                f"\n[green]✓ Removed {len(removed)} {entry_type} entries[/green]"
            )

        return removed

    finally:
        repo.disable_dry_run()
