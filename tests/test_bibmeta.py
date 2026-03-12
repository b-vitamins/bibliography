from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core.bibmeta import load_manifest, validate_bib_file  # noqa: E402


class BibmetaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmpdir.name)
        manifest_src = Path(__file__).resolve().parents[1] / "meta" / "bibmeta.toml"
        manifest_dst = self.repo_root / "meta" / "bibmeta.toml"
        manifest_dst.parent.mkdir(parents=True, exist_ok=True)
        manifest_dst.write_text(manifest_src.read_text(encoding="utf-8"), encoding="utf-8")
        self.manifest = load_manifest(manifest_dst)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _write(self, rel_path: str, content: str) -> Path:
        path = self.repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        return path

    def test_path_derived_curated_collection(self) -> None:
        path = self._write(
            "collections/normalizing-flows.bib",
            """
            @article{example2024flow,
              author = {Example, Ada},
              title = {Example},
              journal = {Example Journal},
              year = {2024}
            }
            """,
        )
        resolution, diagnostics = validate_bib_file(path, manifest=self.manifest, repo_root=self.repo_root)
        self.assertFalse(diagnostics)
        self.assertEqual(resolution.role, "curated")
        self.assertEqual(list(resolution.topics), ["normalizing-flows"])

    def test_oral_subset_is_derived(self) -> None:
        path = self._write(
            "collections/orals/iclr/2026.bib",
            """
            @inproceedings{example2026oral,
              author = {Example, Ada},
              title = {Example Oral},
              booktitle = {ICLR},
              year = {2026}
            }
            """,
        )
        resolution, diagnostics = validate_bib_file(path, manifest=self.manifest, repo_root=self.repo_root)
        self.assertFalse(diagnostics)
        self.assertEqual(resolution.role, "derived")
        self.assertEqual(list(resolution.topics), [])

    def test_redundant_inline_bibmeta_is_rejected(self) -> None:
        path = self._write(
            "books/math-analysis.bib",
            """
            @COMMENT{bibmeta:
            subject = "math-analysis"
            }

            @book{rudin1976principles,
              author = {Rudin, Walter},
              title = {Principles of Mathematical Analysis},
              publisher = {McGraw-Hill},
              year = {1976}
            }
            """,
        )
        _resolution, diagnostics = validate_bib_file(path, manifest=self.manifest, repo_root=self.repo_root)
        codes = {diag.code for diag in diagnostics}
        self.assertIn("inline_redundant", codes)

    def test_inline_bibmeta_must_be_top_of_file(self) -> None:
        path = self._write(
            "collections/gan.bib",
            """
            @article{goodfellow2014gan,
              author = {Goodfellow, Ian},
              title = {Generative Adversarial Nets},
              journal = {Example},
              year = {2014}
            }

            @COMMENT{bibmeta:
            topics_append = ["generative-models"]
            }
            """,
        )
        _resolution, diagnostics = validate_bib_file(path, manifest=self.manifest, repo_root=self.repo_root)
        codes = {diag.code for diag in diagnostics}
        self.assertIn("inline_not_top_of_file", codes)


if __name__ == "__main__":
    unittest.main()
