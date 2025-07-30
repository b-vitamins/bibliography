"""Add operation for bibliography entries."""

import re
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from ..models import BibEntry
from ..repository import Repository
from ..validators import MANDATORY_FIELDS

console = Console()


def generate_key(author: str, year: str, title: str) -> str:
    """Generate a citation key from metadata."""
    # Extract last name from author
    author_parts = author.split(",")[0].strip() if "," in author else author.split()[-1]
    author_key = re.sub(r"[^a-zA-Z]", "", author_parts).lower()

    # Extract first meaningful word from title
    title_words = re.findall(r"\b[a-zA-Z]{4,}\b", title.lower())
    title_key = title_words[0] if title_words else "unknown"

    return f"{author_key}{year}{title_key}"


def validate_pdf_path(path_str: str) -> Path | None:
    """Validate and return PDF path."""
    if not path_str:
        return None

    path = Path(path_str).expanduser().resolve()

    if not path.exists():
        console.print(f"[red]Warning: File does not exist: {path}[/red]")
        if not Confirm.ask("Continue anyway?"):
            return None

    if path.suffix.lower() != ".pdf":
        console.print(f"[yellow]Warning: File is not a PDF: {path}[/yellow]")
        if not Confirm.ask("Continue anyway?"):
            return None

    return path


def prompt_for_entry(
    entry_type: str,
    suggested_key: str | None = None,
) -> BibEntry | None:
    """Interactively prompt for entry fields."""
    console.print(f"\n[bold blue]Creating new {entry_type} entry[/bold blue]")

    # Get mandatory fields for this type
    mandatory = MANDATORY_FIELDS.get(entry_type, [])
    fields = {}

    # Prompt for mandatory fields first
    console.print("\n[yellow]Mandatory fields:[/yellow]")
    for field in mandatory:
        if "/" in field:  # Handle author/editor
            alternatives = field.split("/")
            console.print(f"Need one of: {', '.join(alternatives)}")
            for alt in alternatives:
                value = Prompt.ask(f"{alt}", default="")
                if value:
                    fields[alt] = value
                    break
            else:
                console.print(f"[red]Error: One of {field} is required[/red]")
                return None
        else:
            value = Prompt.ask(f"{field}")
            if not value:
                console.print(f"[red]Error: {field} is required[/red]")
                return None
            fields[field] = value

    # Generate or prompt for key
    if suggested_key:
        key = Prompt.ask("Citation key", default=suggested_key)
    else:
        # Try to generate key from mandatory fields
        author = fields.get("author", fields.get("editor", ""))
        year = fields.get("year", "")
        title = fields.get("title", "")

        if author and year and title:
            suggested = generate_key(author, year, title)
            key = Prompt.ask("Citation key", default=suggested)
        else:
            key = Prompt.ask("Citation key")

    # Prompt for optional common fields
    console.print("\n[yellow]Optional fields (press Enter to skip):[/yellow]")

    # Common optional fields by type
    optional_fields = {
        "article": ["volume", "number", "pages", "month", "doi", "url"],
        "book": ["volume", "series", "address", "edition", "month", "isbn", "url"],
        "inproceedings": [
            "editor",
            "pages",
            "organization",
            "address",
            "month",
            "doi",
            "url",
        ],
        "phdthesis": ["type", "address", "month", "url"],
        "techreport": ["type", "number", "address", "month", "url"],
    }

    for field in optional_fields.get(entry_type, ["url", "doi", "note"]):
        value = Prompt.ask(f"{field}", default="")
        if value:
            fields[field] = value

    # Prompt for PDF file
    console.print("\n[yellow]PDF file location:[/yellow]")
    pdf_path = Prompt.ask("PDF path (absolute)", default="")
    if pdf_path:
        path = validate_pdf_path(pdf_path)
        if path:
            fields["file"] = f":{path}:pdf"

    # Additional fields
    while Confirm.ask("\nAdd another field?", default=False):
        field_name = Prompt.ask("Field name")
        field_value = Prompt.ask(f"{field_name} value")
        if field_name and field_value:
            fields[field_name] = field_value

    # Create entry
    entry = BibEntry(
        key=key,
        entry_type=entry_type,
        fields=fields,
        source_file=Path(""),  # Will be set by repository
    )

    # Show preview
    console.print("\n[bold green]Entry preview:[/bold green]")
    console.print(entry.to_bibtex())

    if not Confirm.ask("\nSave this entry?", default=True):
        return None

    return entry


def add_entry(
    repo: Repository,
    entry_type: str | None = None,
    key: str | None = None,
    dry_run: bool = False,
) -> BibEntry | None:
    """Add a new entry to the repository."""
    if dry_run:
        repo.enable_dry_run()

    try:
        # If no entry type specified, prompt for it
        if not entry_type:
            entry_types = list(MANDATORY_FIELDS.keys())
            console.print("\n[bold]Available entry types:[/bold]")
            for i, etype in enumerate(entry_types, 1):
                console.print(f"{i}. {etype}")

            choice = Prompt.ask(
                "Select entry type (number or name)",
                default="article",
            )

            # Handle numeric choice
            if choice.isdigit() and 1 <= int(choice) <= len(entry_types):
                entry_type = entry_types[int(choice) - 1]
            else:
                entry_type = choice.lower()

        # Validate entry type
        if entry_type not in MANDATORY_FIELDS:
            console.print(f"[red]Error: Unknown entry type '{entry_type}'[/red]")
            console.print(f"Valid types: {', '.join(MANDATORY_FIELDS.keys())}")
            return None

        # Check if key already exists
        if key and repo.get_entry(key):
            console.print(f"[red]Error: Entry with key '{key}' already exists[/red]")
            return None

        # Prompt for entry details
        entry = prompt_for_entry(entry_type, suggested_key=key)
        if not entry:
            return None

        # Determine target file
        by_type_dir = repo.bibtex_path / "by-type"
        target_file = by_type_dir / f"{entry_type}.bib"

        # Ensure directory exists
        by_type_dir.mkdir(parents=True, exist_ok=True)

        # Add to repository
        repo.add_entry(entry, target_file)

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes made[/yellow]")
            console.print(repo.changeset.summary() if repo.changeset else "")
        else:
            console.print(f"\n[green]✓ Entry '{entry.key}' added successfully[/green]")

        return entry

    finally:
        repo.disable_dry_run()


def add_from_file(
    repo: Repository,
    bib_file: Path,
    dry_run: bool = False,
) -> list[BibEntry]:
    """Import entries from a BibTeX file."""
    if not bib_file.exists():
        console.print(f"[red]Error: File not found: {bib_file}[/red]")
        return []

    if dry_run:
        repo.enable_dry_run()

    try:
        # Load entries from file
        temp_repo = Repository(repo.root_path)
        entries = temp_repo._load_file(bib_file)  # type: ignore[attr-defined]

        if not entries:
            console.print(f"[yellow]No entries found in {bib_file}[/yellow]")
            return []

        console.print(f"\n[bold]Found {len(entries)} entries in {bib_file}[/bold]")

        # Check for duplicates
        added = []
        skipped = []

        for entry in entries:
            if repo.get_entry(entry.key):
                skipped.append(entry)
                console.print(f"[yellow]Skipping duplicate: {entry.key}[/yellow]")
                continue

            # Determine target file by type
            target_file = repo.bibtex_path / "by-type" / f"{entry.entry_type}.bib"

            # Add to repository
            repo.add_entry(entry, target_file)
            added.append(entry)
            console.print(f"[green]Added: {entry.key} ({entry.entry_type})[/green]")

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes made[/yellow]")
            console.print(repo.changeset.summary() if repo.changeset else "")
        else:
            console.print(f"\n[green]✓ Added {len(added)} entries[/green]")
            if skipped:
                console.print(f"[yellow]Skipped {len(skipped)} duplicates[/yellow]")

        return added

    finally:
        repo.disable_dry_run()
