"""Pytest configuration and fixtures."""

import re
import tempfile
from pathlib import Path

import pytest


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    ansi_escape = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for easier comparison."""
    return " ".join(text.split())


@pytest.fixture
def temp_bib_file():
    """Create a temporary .bib file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False) as f:
        f.write("""@article{test2023,
  author = {Test Author},
  title = {Test Article},
  journal = {Test Journal},
  year = {2023}
}
""")
        temp_path = Path(f.name)
    yield temp_path
    temp_path.unlink()


@pytest.fixture
def sample_bibtex_content():
    """Sample BibTeX content for testing."""
    return """
@article{einstein1905,
  author = {Einstein, Albert},
  title = {On the Electrodynamics of Moving Bodies},
  journal = {Annalen der Physik},
  year = {1905}
}

@book{feynman1985,
  author = {Feynman, Richard P.},
  title = {QED: The Strange Theory of Light and Matter},
  publisher = {Princeton University Press},
  year = {1985}
}

@misc{incomplete_entry,
  title = {Incomplete Entry}
}
"""
