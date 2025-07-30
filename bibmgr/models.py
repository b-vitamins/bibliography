"""Data models for bibliography entries."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationError:
    """Represents a validation error in a bibliography entry."""

    bib_file: Path
    entry_key: str
    error_type: str
    message: str
    file_path: Path | None = None

    def __str__(self) -> str:
        """Format error for display."""
        location = f"{self.bib_file.name}[{self.entry_key}]"
        if self.file_path:
            return f"{location}: {self.error_type} - {self.message} ({self.file_path})"
        return f"{location}: {self.error_type} - {self.message}"


@dataclass(frozen=True)
class BibEntry:
    """Represents a bibliography entry."""

    key: str
    entry_type: str
    fields: dict[str, str]
    source_file: Path

    @property
    def file_path(self) -> Path | None:
        """Extract file path from entry if present."""
        if "file" not in self.fields:
            return None

        file_field = self.fields["file"].strip("{}")

        # Handle different BibTeX file formats
        if file_field.startswith(":") and file_field.endswith(":pdf"):
            path_str = file_field[1:-4]
        elif file_field.endswith(":pdf"):
            path_str = file_field[:-4]
        else:
            path_str = file_field

        return Path(path_str) if path_str else None
