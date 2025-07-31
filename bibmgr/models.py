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


@dataclass
class BibEntry:
    """Represents a bibliography entry."""

    key: str
    entry_type: str
    fields: dict[str, str | None]
    source_file: Path

    @property
    def file_path(self) -> Path | None:
        """Extract file path from entry if present."""
        if "file" not in self.fields:
            return None

        file_field_value = self.fields["file"]
        if file_field_value is None:
            return None
        file_field = file_field_value.strip("{}")

        # Handle different BibTeX file formats
        if file_field.startswith(":") and file_field.endswith(":pdf"):
            path_str = file_field[1:-4]
        elif file_field.endswith(":pdf"):
            path_str = file_field[:-4]
        else:
            path_str = file_field

        return Path(path_str) if path_str else None

    def update_field(self, field: str, value: str | None) -> None:
        """Update a single field value."""
        self.fields[field] = value

    def remove_field(self, field: str) -> None:
        """Remove a field from the entry."""
        self.fields.pop(field, None)

    def set_file_path(self, path: Path) -> None:
        """Set the file path in BibTeX format."""
        self.fields["file"] = f"{{:{path}:pdf}}"

    def validate_mandatory_fields(self) -> list[str]:
        """Check if entry has all mandatory fields for its type."""
        from .validators import MANDATORY_FIELDS

        required = MANDATORY_FIELDS.get(self.entry_type, [])
        missing = []

        for field in required:
            if "/" in field:  # Handle author/editor case
                alternatives = field.split("/")
                if not any(alt in self.fields for alt in alternatives):
                    missing.append(field)
            elif field not in self.fields:
                missing.append(field)

        return missing

    def to_bibtex(self) -> str:
        """Convert entry to BibTeX format string."""
        lines = [f"@{self.entry_type}{{{self.key},"]

        # Sort fields for consistent output
        sorted_fields = sorted(self.fields.items())

        for field, value in sorted_fields:
            # Ensure values are properly formatted
            if value is not None and (
                not value.startswith("{") or not value.endswith("}")
            ):
                value = f"{{{value}}}"
            lines.append(f"  {field} = {value},")

        # Remove trailing comma from last field
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]

        lines.append("}")
        return "\n".join(lines)

    def copy(self) -> "BibEntry":
        """Create a deep copy of the entry."""
        return BibEntry(
            key=self.key,
            entry_type=self.entry_type,
            fields=self.fields.copy(),
            source_file=self.source_file,
        )
