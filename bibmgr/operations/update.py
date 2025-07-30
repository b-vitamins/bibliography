"""Update operation for bibliography entries."""

from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ..models import BibEntry
from ..repository import Repository

console = Console()


def display_changes(old_entry: BibEntry, new_entry: BibEntry) -> None:
    """Display changes between old and new entry."""
    table = Table(title=f"Changes to {old_entry.key}", show_header=True)
    table.add_column("Field", style="cyan")
    table.add_column("Old Value", style="red")
    table.add_column("New Value", style="green")

    # Check all fields
    all_fields = set(old_entry.fields.keys()) | set(new_entry.fields.keys())

    for field in sorted(all_fields):
        old_val = old_entry.fields.get(field, "")
        new_val = new_entry.fields.get(field, "")

        if old_val != new_val:
            # Truncate long values
            old_display = old_val if len(old_val) <= 30 else old_val[:27] + "..."
            new_display = new_val if len(new_val) <= 30 else new_val[:27] + "..."

            if not old_val:
                old_display = "[not set]"
            if not new_val:
                new_display = "[removed]"

            table.add_row(field, old_display, new_display)

    if table.row_count > 0:
        console.print(table)
    else:
        console.print("[yellow]No changes[/yellow]")


def update_entry(
    repo: Repository,
    key: str,
    updates: dict[str, str | None] | None = None,
    interactive: bool = True,
    dry_run: bool = False,
) -> BibEntry | None:
    """Update an entry in the repository."""
    if dry_run:
        repo.enable_dry_run()

    try:
        # Find the entry
        entry = repo.get_entry(key)
        if not entry:
            console.print(f"[red]Error: Entry '{key}' not found[/red]")
            return None

        # If no updates provided and not interactive, nothing to do
        if not updates and not interactive:
            console.print("[yellow]No updates specified[/yellow]")
            return entry

        # Collect updates
        if not updates:
            updates = {}

        if interactive:
            console.print(f"\n[bold]Updating entry: {key}[/bold]")
            console.print(f"Type: {entry.entry_type}")
            console.print(
                "\n[yellow]Current fields (Enter=keep, 'DELETE'=remove):[/yellow]"
            )

            # Show current fields
            for field, value in sorted(entry.fields.items()):
                # Special handling for long values
                if len(value) > 60:
                    console.print(f"\n{field}:")
                    console.print(f"  [dim]{value[:80]}...[/dim]")
                    new_value = Prompt.ask("New value", default="[keep]")
                else:
                    new_value = Prompt.ask(f"{field}", default=value)

                if new_value == "[keep]":
                    continue  # Keep current value
                elif new_value.upper() == "DELETE":
                    updates[field] = None  # Mark for deletion
                elif new_value != value:
                    updates[field] = new_value

            # Add new fields
            while Confirm.ask("\nAdd a new field?", default=False):
                field_name = Prompt.ask("Field name")
                if field_name and field_name not in entry.fields:
                    field_value = Prompt.ask(f"{field_name} value")
                    if field_value:
                        updates[field_name] = field_value

        # Check if there are any updates
        if not updates:
            console.print("[yellow]No changes made[/yellow]")
            return entry

        # Show preview of changes
        new_entry = entry.copy()
        for field, value in updates.items():
            if value is None:
                new_entry.remove_field(field)
            else:
                new_entry.update_field(field, value)

        console.print("\n[bold]Preview of changes:[/bold]")
        display_changes(entry, new_entry)

        # Validate mandatory fields
        missing = new_entry.validate_mandatory_fields()
        if missing:
            console.print(
                f"\n[red]Warning: Missing mandatory fields: {', '.join(missing)}[/red]"
            )
            if not Confirm.ask("Continue anyway?", default=False):
                console.print("[yellow]Cancelled[/yellow]")
                return None

        # Confirm update
        if interactive and not Confirm.ask("\nApply these changes?", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return None

        # Apply updates
        updated = repo.update_entry(key, updates)

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes made[/yellow]")
            console.print(repo.changeset.summary() if repo.changeset else "")
        else:
            console.print(f"\n[green]✓ Entry '{key}' updated successfully[/green]")

        return updated

    finally:
        repo.disable_dry_run()


def update_field_batch(
    repo: Repository,
    field: str,
    old_value: str,
    new_value: str,
    entry_type: str | None = None,
    dry_run: bool = False,
) -> list[BibEntry]:
    """Update a field value across multiple entries."""
    if dry_run:
        repo.enable_dry_run()

    try:
        # Find matching entries
        entries = repo.load_entries()
        matches = []

        for entry in entries:
            # Filter by type if specified
            if entry_type and entry.entry_type != entry_type:
                continue

            # Check if field matches
            if entry.fields.get(field, "") == old_value:
                matches.append(entry)

        if not matches:
            console.print(
                f"[yellow]No entries found with {field}='{old_value}'[/yellow]"
            )
            return []

        # Display matches
        console.print(f"\n[bold]Found {len(matches)} matching entries:[/bold]")

        table = Table(show_header=True)
        table.add_column("Key", style="cyan")
        table.add_column("Type")
        table.add_column("Title")

        for entry in matches[:10]:  # Show first 10
            title = entry.fields.get("title", "")[:40]
            table.add_row(entry.key, entry.entry_type, title)

        if len(matches) > 10:
            table.add_row("...", "...", f"... and {len(matches) - 10} more")

        console.print(table)

        # Show change
        console.print("\n[bold]Change:[/bold]")
        console.print(f"  {field}: [red]{old_value}[/red] → [green]{new_value}[/green]")

        # Confirm update
        if not Confirm.ask("\nApply to all matching entries?", default=False):
            console.print("[yellow]Cancelled[/yellow]")
            return []

        # Update entries
        updated = []
        for entry in matches:
            result = repo.update_entry(entry.key, {field: new_value})
            if result:
                updated.append(result)
                console.print(f"[green]Updated: {entry.key}[/green]")

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes made[/yellow]")
            console.print(repo.changeset.summary() if repo.changeset else "")
        else:
            console.print(f"\n[green]✓ Updated {len(updated)} entries[/green]")

        return updated

    finally:
        repo.disable_dry_run()


def move_pdf(
    repo: Repository,
    key: str,
    new_path: Path,
    dry_run: bool = False,
) -> BibEntry | None:
    """Move PDF file and update entry path."""
    if dry_run:
        repo.enable_dry_run()

    try:
        # Find the entry
        entry = repo.get_entry(key)
        if not entry:
            console.print(f"[red]Error: Entry '{key}' not found[/red]")
            return None

        # Check current PDF
        old_path = entry.file_path
        if not old_path:
            console.print(f"[red]Error: Entry '{key}' has no file path[/red]")
            return None

        # Validate paths
        if not old_path.exists():
            console.print(f"[red]Error: Current file not found: {old_path}[/red]")
            if not Confirm.ask("Update path anyway?", default=False):
                return None

        new_path = new_path.expanduser().resolve()
        if new_path.exists():
            console.print(f"[red]Error: Target already exists: {new_path}[/red]")
            return None

        # Show operation
        console.print("\n[bold]Move operation:[/bold]")
        console.print(f"  From: {old_path}")
        console.print(f"  To:   {new_path}")

        # Confirm
        if not Confirm.ask("\nProceed with move?", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return None

        # Move file (if not dry run and file exists)
        if not dry_run and old_path.exists():
            try:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                old_path.rename(new_path)
                console.print("[green]✓ Moved file successfully[/green]")
            except Exception as e:
                console.print(f"[red]Error moving file: {e}[/red]")
                return None

        # Update entry
        updates: dict[str, str | None] = {"file": f":{new_path}:pdf"}
        updated = repo.update_entry(key, updates)

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes made[/yellow]")
            console.print(repo.changeset.summary() if repo.changeset else "")
            if old_path.exists():
                console.print(f"Would move: {old_path} → {new_path}")
        else:
            console.print(f"\n[green]✓ Entry '{key}' updated with new path[/green]")

        return updated

    finally:
        repo.disable_dry_run()
