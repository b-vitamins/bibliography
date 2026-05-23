from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bibops_fulltext_sync import (  # noqa: E402
    DEFAULT_TEI_COORDINATES,
    FulltextSyncOptions,
    FulltextWorkItem,
    classify_page_tier,
    effective_tier_plan,
    extraction_config_sha256,
    grobid_parameters,
    metadata_is_current,
    process_item,
    prepare_item,
    run_fulltext_sync,
    scan_work,
    tei_features,
)
from bibops_pdf_sync import expand_targets, get_target_path  # noqa: E402
from core.bibtex_io import resolve_bib_paths  # noqa: E402


def write_minimal_pdf(path: Path) -> None:
    body = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n" + (b"0" * 1200) + b"\n%%EOF\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


class FulltextSyncTests(unittest.TestCase):
    def test_pdf_target_path_uses_per_entry_workspace(self) -> None:
        entry = {"ID": "smith2026test", "ENTRYTYPE": "inproceedings"}
        self.assertEqual(
            get_target_path(entry, Path("/docs")),
            Path("/docs/inproceedings/smith2026test/smith2026test.pdf"),
        )

    def test_target_expansion_preserves_priority_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.bib"
            second = root / "second.bib"
            first.write_text("", encoding="utf-8")
            second.write_text("", encoding="utf-8")

            self.assertEqual(resolve_bib_paths([str(second), str(first)]), [second.resolve(), first.resolve()])
            expanded, unresolved = expand_targets([str(second), str(first)])
            self.assertEqual(unresolved, [])
            self.assertEqual(expanded, [second.resolve(), first.resolve()])

    def test_page_tiers_classify_long_documents(self) -> None:
        options = FulltextSyncOptions(targets=[])
        self.assertEqual(classify_page_tier(None, options), "unknown")
        self.assertEqual(classify_page_tier(50, options), "article")
        self.assertEqual(classify_page_tier(51, options), "medium")
        self.assertEqual(classify_page_tier(151, options), "long")
        self.assertEqual(classify_page_tier(501, options), "huge")

    def test_auto_tier_workers_scale_with_cpu_threads(self) -> None:
        plan = effective_tier_plan(FulltextSyncOptions(targets=[]), cpu_threads=12)
        self.assertEqual(plan["article"].workers, 6)
        self.assertEqual(plan["medium"].workers, 3)
        self.assertEqual(plan["unknown"].workers, 3)
        self.assertEqual(plan["long"].workers, 1)
        self.assertEqual(plan["huge"].workers, 1)

        explicit = effective_tier_plan(
            FulltextSyncOptions(targets=[], workers=9, medium_workers=4, long_workers=2, huge_workers=1),
            cpu_threads=12,
        )
        self.assertEqual(explicit["article"].workers, 9)
        self.assertEqual(explicit["medium"].workers, 4)
        self.assertEqual(explicit["long"].workers, 2)
        self.assertEqual(explicit["huge"].workers, 1)

    def test_grobid_parameters_default_to_bulk_information_profile(self) -> None:
        params = grobid_parameters()
        self.assertIn(("consolidateHeader", "1"), params)
        self.assertIn(("includeRawCitations", "1"), params)
        self.assertIn(("segmentSentences", "1"), params)
        self.assertIn(("teiCoordinates", "figure"), params)
        self.assertIn(("teiCoordinates", "formula"), params)
        self.assertIn(("teiCoordinates", "ref"), params)
        self.assertIn(("teiCoordinates", "biblStruct"), params)
        self.assertNotIn(("consolidateCitations", "1"), params)
        self.assertNotIn(("consolidateFunders", "1"), params)
        self.assertNotIn(("includeRawAffiliations", "1"), params)
        self.assertNotIn(("includeRawCopyrights", "1"), params)
        self.assertEqual(DEFAULT_TEI_COORDINATES, ("figure", "formula", "ref", "biblStruct"))

        lean = grobid_parameters(
            FulltextSyncOptions(
                targets=[],
                include_raw_citations=False,
                segment_sentences=False,
                tei_coordinates=False,
            )
        )
        self.assertEqual(lean, [("consolidateHeader", "1")])

        richer = grobid_parameters(
            FulltextSyncOptions(
                targets=[],
                consolidate_citations=True,
                consolidate_funders=True,
                include_raw_affiliations=True,
                include_raw_copyrights=True,
            )
        )
        self.assertIn(("consolidateCitations", "1"), richer)
        self.assertIn(("consolidateFunders", "1"), richer)
        self.assertIn(("includeRawAffiliations", "1"), richer)
        self.assertIn(("includeRawCopyrights", "1"), richer)

    def test_scan_requires_canonical_nested_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "documents"
            bib = root / "sample.bib"
            pdf = docs / "inproceedings" / "smith2026test" / "smith2026test.pdf"
            write_minimal_pdf(pdf)
            bib.write_text(
                """@inproceedings{smith2026test,
  author = {Jane Smith},
  title = {A Test Paper},
  booktitle = {ICLR},
  year = {2026},
  file = {:%s:pdf}
}
"""
                % pdf,
                encoding="utf-8",
            )

            work, preflight, summary = scan_work(FulltextSyncOptions(targets=[str(bib)], base_dir=docs))

            self.assertEqual(len(preflight), 0)
            self.assertEqual(len(work), 1)
            self.assertEqual(summary["work_items"], 1)

    def test_prepare_skips_current_provenance_without_pdfinfo_or_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "smith2026test.pdf"
            tei = root / "smith2026test.tei.xml"
            meta = root / "smith2026test.grobid.json"
            write_minimal_pdf(pdf)
            tei.write_text("<TEI/>", encoding="utf-8")
            stat = pdf.stat()
            config_sha = extraction_config_sha256(grobid_parameters())
            meta.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "pdf": {
                            "sha256": "cached-sha",
                            "bytes": stat.st_size,
                            "mtime_ns": stat.st_mtime_ns,
                            "pages": 12,
                        },
                        "grobid": {
                            "version": "0.9.0",
                            "revision": "0.9.0",
                            "extraction_config_sha256": config_sha,
                        },
                    }
                ),
                encoding="utf-8",
            )
            item = FulltextWorkItem(
                bib_file=root / "sample.bib",
                entry_key="smith2026test",
                entry_type="inproceedings",
                title="A Test Paper",
                author="Jane Smith",
                pdf_path=pdf,
                document_dir=root,
                tei_path=tei,
                provenance_path=meta,
            )

            with mock.patch("bibops_fulltext_sync.pdf_page_count", side_effect=AssertionError("no pdfinfo")):
                with mock.patch("bibops_fulltext_sync.file_sha256", side_effect=AssertionError("no hash")):
                    prepared, outcome = prepare_item(
                        item,
                        options=FulltextSyncOptions(targets=[]),
                        grobid_info={"version": "0.9.0", "revision": "0.9.0"},
                        config_sha=config_sha,
                        parameters=grobid_parameters(),
                    )

            self.assertIsNone(prepared)
            self.assertIsNotNone(outcome)
            self.assertEqual(outcome.status, "skipped_current")
            self.assertEqual(outcome.page_count, 12)
            self.assertEqual(outcome.page_tier, "article")

    def test_process_item_does_not_force_text_plain_accept_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "smith2026test.pdf"
            write_minimal_pdf(pdf)
            item = FulltextWorkItem(
                bib_file=root / "sample.bib",
                entry_key="smith2026test",
                entry_type="inproceedings",
                title="A Test Paper",
                author="Jane Smith",
                pdf_path=pdf,
                document_dir=root,
                tei_path=root / "smith2026test.tei.xml",
                provenance_path=root / "smith2026test.grobid.json",
                page_count=1,
                page_tier="article",
            )

            response = mock.Mock()
            response.status_code = 200
            response.text = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader><fileDesc><titleStmt><title>A Test Paper</title></titleStmt></fileDesc></teiHeader>
  <text><body><p>Body.</p></body></text>
</TEI>"""
            response.raise_for_status.return_value = None
            session = mock.Mock()
            session.post.return_value = response

            with mock.patch("bibops_fulltext_sync.grobid_http_session", return_value=session):
                outcome = process_item(
                    item,
                    options=FulltextSyncOptions(targets=[]),
                    grobid_info={"version": "0.9.0", "revision": "0.9.0"},
                    parameters=grobid_parameters(),
                    config_sha=extraction_config_sha256(grobid_parameters()),
                )

            self.assertEqual(outcome.status, "extracted")
            self.assertNotIn("headers", session.post.call_args.kwargs)

    def test_dry_run_does_not_require_grobid_version_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "documents"
            bib = root / "sample.bib"
            pdf = docs / "inproceedings" / "smith2026test" / "smith2026test.pdf"
            write_minimal_pdf(pdf)
            bib.write_text(
                """@inproceedings{smith2026test,
  author = {Jane Smith},
  title = {A Test Paper},
  booktitle = {ICLR},
  year = {2026},
  file = {:%s:pdf}
}
"""
                % pdf,
                encoding="utf-8",
            )

            with mock.patch("bibops_fulltext_sync.grobid_version", side_effect=AssertionError("no GROBID probe")):
                result = run_fulltext_sync(
                    FulltextSyncOptions(
                        targets=[str(bib)],
                        base_dir=docs,
                        dry_run=True,
                    )
                )

            self.assertEqual(result.summary["work_items"], 1)
            self.assertEqual(result.summary["planned"], 1)
            self.assertEqual(result.failures, [])

    def test_fulltext_module_is_package_importable(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-c", "import scripts.bibops_fulltext_sync"],
            cwd=REPO,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_metadata_current_checks_pdf_hash_grobid_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tei = root / "key.tei.xml"
            meta = root / "key.grobid.json"
            tei.write_text("<TEI/>", encoding="utf-8")
            config_sha = extraction_config_sha256(grobid_parameters())
            meta.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "pdf": {"sha256": "abc"},
                        "grobid": {
                            "version": "0.9.0",
                            "revision": "0.9.0",
                            "extraction_config_sha256": config_sha,
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(
                metadata_is_current(
                    meta,
                    tei,
                    pdf_sha="abc",
                    grobid_info={"version": "0.9.0", "revision": "0.9.0"},
                    config_sha=config_sha,
                )
            )
            self.assertFalse(
                metadata_is_current(
                    meta,
                    tei,
                    pdf_sha="changed",
                    grobid_info={"version": "0.9.0", "revision": "0.9.0"},
                    config_sha=config_sha,
                )
            )

    def test_metadata_current_accepts_superset_extraction_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tei = root / "key.tei.xml"
            meta = root / "key.grobid.json"
            tei.write_text("<TEI/>", encoding="utf-8")
            requested = grobid_parameters()
            richer = grobid_parameters(
                FulltextSyncOptions(
                    targets=[],
                    consolidate_citations=True,
                    consolidate_funders=True,
                    include_raw_affiliations=True,
                    include_raw_copyrights=True,
                    tei_coordinate_elements=("title", "figure", "formula", "ref", "biblStruct"),
                )
            )
            meta.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "pdf": {"sha256": "abc"},
                        "grobid": {
                            "version": "0.9.0",
                            "revision": "0.9.0",
                            "extraction_config_sha256": "older-richer-config",
                            "parameters": richer,
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(
                metadata_is_current(
                    meta,
                    tei,
                    pdf_sha="abc",
                    grobid_info={"version": "0.9.0", "revision": "0.9.0"},
                    config_sha=extraction_config_sha256(requested),
                    parameters=requested,
                )
            )

    def test_tei_features_extracts_quality_signals(self) -> None:
        tei = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt><title>A Test Paper</title></titleStmt>
      <sourceDesc>
        <biblStruct>
          <analytic><author><persName><surname>Smith</surname></persName></author></analytic>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
    <profileDesc><abstract><p>This is the abstract.</p></abstract></profileDesc>
  </teiHeader>
  <text>
    <body><p>Body text.</p></body>
    <back><listBibl><biblStruct/><biblStruct/></listBibl></back>
  </text>
</TEI>"""
        features = tei_features(tei, bib_title="A Test Paper", bib_author="Jane Smith and John Doe")
        self.assertTrue(features["has_title"])
        self.assertTrue(features["has_abstract"])
        self.assertEqual(features["reference_count"], 2)
        self.assertTrue(features["first_author_match"])
        self.assertGreater(features["title_similarity"], 0.95)


if __name__ == "__main__":
    unittest.main()
