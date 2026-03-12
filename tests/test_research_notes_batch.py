from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import research_notes_batch as batch


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_reader_notes_payload(title: str, arxiv_id: str) -> dict[str, object]:
    return {
        "title": title,
        "doi": None,
        "venue": "NeurIPS",
        "year": 2025,
        "paper_type": "empirical methods paper",
        "external_ids": {
            "arxiv": arxiv_id,
            "doi": None,
            "openreview_forum": None,
            "openalex": None,
            "semantic_scholar": None,
        },
        "source_version": arxiv_id,
        "source_coverage": "combined TeX source",
        "source_provenance": {
            "input_type": "arxiv_source_bundle",
            "input_label": f"https://arxiv.org/abs/{arxiv_id}",
            "tex_source_authority": "TeX",
            "companion_pdf_used": False,
        },
        "input_quality": "native text",
        "tex_source_gate": "PASS",
        "readthrough_complete": True,
        "readthrough_chunks": {"completed": 3, "total": 3},
        "coordinates": {
            "purpose": ["analysis"],
            "problem_form": ["node_classification"],
            "learning_signal": ["self_supervision"],
            "mechanism": ["masked_prediction"],
            "evidence_regime": ["benchmark_experiments"],
        },
        "claim_surfaces": {
            "problem": "The paper studies a benchmarked technical problem.",
            "data": "Benchmarks are used for evaluation.",
            "objective": "Improve the target metric.",
            "mechanism": "Method uses a structured predictor.",
            "regime": "NeurIPS 2025 evaluation setting.",
            "evaluation": "Matched baselines and metrics are reported.",
            "deployment": "Useful for downstream practitioners.",
        },
        "problem": "Technical benchmark task with source-grounded evaluation.",
        "main_claim": "The method improves the benchmark metric under matched evaluation.",
        "notation": ["x: input features"],
        "assumptions": ["A1: benchmark conditions hold"],
        "results": ["Accuracy improves by a reported margin."],
        "algorithms": ["Algorithm 1"],
        "datasets": ["DatasetX"],
        "metrics": ["accuracy"],
        "hardware": {"gpu": "RTX 4090"},
        "effects": ["accuracy_gain"],
        "artifacts": {"code": "https://example.com/code"},
        "relation_hints": ["compares_to: baseline"],
        "repro_thresholds": ["3 seeds"],
        "limitations": ["Single benchmark family."],
        "red_flags": ["More ablations would help."],
    }


def build_reader_notes_markdown(title: str, arxiv_id: str, payload: dict[str, object]) -> str:
    embedded_json = json.dumps(payload, indent=2)
    return f"""# Reader Notes: {title}

## Source coverage
- TeX source gate: PASS
- Source version used: arXiv:{arxiv_id}
- Source coverage: combined TeX source
- Source provenance: arXiv source bundle
- External IDs: arXiv: {arxiv_id}
- Input quality: native text
- Figure availability: source assets
- Readthrough coverage: 3/3 chunks
- Confidence: high

## 0) Header
- Citation: {title}

## 1) One-sentence claim (verifiable)
[P] Anchor: combined-source.tex:10-12; The paper reports an improvement on the benchmark metric.

## 2) Problem & setup (canonicalized)
- Anchor: combined-source.tex:13-18; The task is benchmarked under a controlled evaluation setup.

## 3) Notation & constants table
| symbol | meaning | type/units | default/typical value | source anchor | normalization note |
| --- | --- | --- | --- | --- | --- |
| `x` | input | scalar | 1 | combined-source.tex:20-21 | canonicalized |

## 4) Method/Model (algorithmic core)
1. Anchor: combined-source.tex:22-24; The method applies a structured predictor.

## 5) Theory/Derivation summary
[P] Anchor: combined-source.tex:30-35; The paper states a formal argument for the method.

## 6) Assumptions & conditions ledger
- Anchor: combined-source.tex:36-38; Benchmark assumptions are explicitly stated.

## 7) Experiments: reproduction checklist
- Anchor: combined-source.tex:39-41; The experiment setup specifies seeds, hardware, and metrics.

## 8) Results with matched deltas
[P] Anchor: combined-source.tex:42-45; The primary benchmark improves under matched evaluation.

## 9) Figures -> findings map
- Anchor: combined-source.tex:46-47; Figure 1 shows the main trend.

## 10) Comparison to prior work
[P] Anchor: combined-source.tex:48-49; Relation: compares_to; The method outperforms the nearest baseline.

## 11) External validity & limits
[P] Anchor: combined-source.tex:50-51; External validity is limited to the reported regime.

## 12) Threats to validity
[P] Anchor: combined-source.tex:52-53; Threats include benchmark sensitivity.

## 13) Vital verbatim sentences
- `[claim]` Anchor: combined-source.tex:54-55; "The method improves the benchmark metric."

## 14) Reproduction/verification plan
1. Anchor: combined-source.tex:56-57; Reproduce the benchmark with the stated seeds.

## 15) Artifacts
- Anchor: combined-source.tex:58-59; Code and hardware are identified.

## 16) Red flags & green flags
[P] Anchor: combined-source.tex:60-61; Green flag: the paper reports matched baselines.

## 17) Who should care & why it matters
[I] Basis: combined-source.tex:62-63; Builders care because the method improves a practical metric.

## 18) Open questions
[I] Basis: combined-source.tex:64-65; Open question: does the method generalize beyond DatasetX?

## 19) Machine-readable block (JSON)
```json
{embedded_json}
```
"""


def build_fact_ledger_text() -> str:
    lines = ["# Fact Ledger", ""]
    for index in range(1, 13):
        lines.append(f"- Anchor: `combined-source.tex:{index}`; Atomic fact {index}.")
    lines.append("")
    return "\n".join(lines)


def build_readthrough_log() -> dict[str, object]:
    chunks = []
    for index in range(1, 4):
        chunks.append(
            {
                "id": f"C{index:03d}",
                "start_line": (index - 1) * 10 + 1,
                "end_line": index * 10,
                "section": f"section-{index}",
                "must_read": True,
                "read": True,
                "summary": f"Chunk C{index:03d} covers the main technical content for section {index}.",
                "timestamp_utc": "2026-03-12T00:00:00+00:00",
            }
        )
    return {
        "completed": True,
        "chunks_completed": 3,
        "chunks_total": 3,
        "chunks": chunks,
    }


def write_valid_workspace_bundle(workspace: Path, title: str, arxiv_id: str) -> dict[str, object]:
    payload = build_reader_notes_payload(title, arxiv_id)
    (workspace / "notes").mkdir(parents=True, exist_ok=True)
    (workspace / "manifests").mkdir(parents=True, exist_ok=True)
    (workspace / "notes" / "reader-notes.md").write_text(
        build_reader_notes_markdown(title, arxiv_id, payload),
        encoding="utf-8",
    )
    write_json(workspace / "notes" / "reader-notes.json", payload)
    (workspace / "notes" / "fact-ledger.md").write_text(build_fact_ledger_text(), encoding="utf-8")
    write_json(workspace / "manifests" / "validation-report.json", {"passed": True, "errors": [], "warnings": []})
    write_json(workspace / "manifests" / "readthrough-log.json", build_readthrough_log())
    return payload


def write_valid_published_notes_bundle(notes_dir: Path, title: str, arxiv_id: str) -> dict[str, object]:
    payload = build_reader_notes_payload(title, arxiv_id)
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "reader-notes.md").write_text(build_reader_notes_markdown(title, arxiv_id, payload), encoding="utf-8")
    write_json(notes_dir / "reader-notes.json", payload)
    (notes_dir / "fact-ledger.md").write_text(build_fact_ledger_text(), encoding="utf-8")
    write_json(notes_dir / "validation-report.json", {"passed": True, "errors": [], "warnings": []})
    return payload


class ResearchNotesBatchTests(unittest.TestCase):
    def test_extract_arxiv_id_prefers_eprint_archiveprefix(self) -> None:
        entry = {
            "archiveprefix": "arXiv",
            "eprint": "2502.05173v3",
            "arxiv": "https://arxiv.org/abs/0000.00000",
        }
        arxiv_id, source = batch.extract_arxiv_id(entry)
        self.assertEqual(arxiv_id, "2502.05173")
        self.assertEqual(source, "eprint")

    def test_plan_skips_missing_arxiv_and_existing_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            bib_path = tmp / "selector.bib"
            bib_path.write_text(
                """@inproceedings{alpha2025paper,
  title = {Alpha Paper},
  year = {2025},
  arxiv = {https://arxiv.org/abs/2502.05173}
}

@inproceedings{beta2025paper,
  title = {Beta Paper},
  year = {2025}
}

@inproceedings{gamma2025paper,
  title = {Gamma Paper},
  year = {2025},
  arxiv = {https://arxiv.org/abs/2501.00001}
}
""",
                encoding="utf-8",
            )

            documents_root = tmp / "documents"
            published_notes = batch.notes_dir(documents_root, "inproceedings", "gamma2025paper")
            published_notes.mkdir(parents=True)
            for filename in batch.PUBLISHED_ARTIFACTS:
                (published_notes / filename).write_text("ok\n", encoding="utf-8")

            run_root = tmp / "run"
            plan = batch.build_plan([str(bib_path)], run_root, documents_root, force=False)
            outputs = batch.write_plan_outputs(plan, run_root)

            self.assertEqual(plan["ready_count"], 1)
            self.assertEqual(plan["skipped_count"], 2)
            self.assertIn("skip_missing_arxiv", plan["skip_reasons"])
            self.assertIn("skip_existing_notes", plan["skip_reasons"])

            jobs_csv = Path(outputs["jobs_csv"])
            with jobs_csv.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["key"], "alpha2025paper")
            self.assertEqual(rows[0]["notes_dir"], str(batch.notes_dir(documents_root, "inproceedings", "alpha2025paper").resolve()))
            self.assertTrue(rows[0]["workspace_dir"].endswith("/2502.05173"))

    def test_plan_routes_oral_selector_to_canonical_conference_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            oral_root = tmp / "collections" / "orals"
            canonical_root = tmp / "conferences"
            oral_bib = oral_root / "neurips" / "2025.bib"
            canonical_bib = canonical_root / "neurips" / "2025.bib"
            oral_bib.parent.mkdir(parents=True)
            canonical_bib.parent.mkdir(parents=True)
            oral_bib.write_text(
                """@inproceedings{alpha2025paper,
  title = {Alpha Paper},
  year = {2025},
  url = {https://openreview.net/forum?id=test123},
  pdf = {https://openreview.net/pdf?id=test123},
  arxiv = {https://arxiv.org/abs/2502.05173}
}
""",
                encoding="utf-8",
            )
            canonical_bib.write_text(
                """@inproceedings{alpha2025paper,
  title = {Alpha Paper},
  year = {2025}
}
""",
                encoding="utf-8",
            )

            original_orals_root = batch.ORALS_ROOT
            original_canonical_root = batch.CANONICAL_CONFERENCES_ROOT
            try:
                batch.ORALS_ROOT = oral_root.resolve()
                batch.CANONICAL_CONFERENCES_ROOT = canonical_root.resolve()
                plan = batch.build_plan([str(oral_bib)], tmp / "run", tmp / "documents", force=False)
            finally:
                batch.ORALS_ROOT = original_orals_root
                batch.CANONICAL_CONFERENCES_ROOT = original_canonical_root

            self.assertEqual(plan["ready_count"], 1)
            self.assertEqual(plan["ready_jobs"][0]["target_bib_file"], str(canonical_bib.resolve()))

    def test_publish_copies_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            workspace = tmp / "workspace"
            write_valid_workspace_bundle(workspace, title="Alpha Paper", arxiv_id="2502.05173")

            notes_target = tmp / "documents" / "inproceedings" / "alpha2025paper" / "notes"
            report = batch.publish_workspace(workspace, notes_target, fail_if_exists=False)

            self.assertTrue(report["published"])
            self.assertEqual(report["status"], "published")
            for filename in batch.PUBLISHED_ARTIFACTS:
                self.assertTrue((notes_target / filename).exists(), filename)

    def test_publish_rejects_placeholder_note_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            workspace = tmp / "workspace"
            (workspace / "notes").mkdir(parents=True)
            (workspace / "manifests").mkdir(parents=True)
            (workspace / "notes" / "reader-notes.md").write_text(
                "# Reader Notes: Alpha Paper\n\n## 1) One-sentence claim (verifiable)\n[P] Anchor: source/overview; This work’s primary claim is documented but not re-validated in this batch run.\n",
                encoding="utf-8",
            )
            write_json(
                workspace / "notes" / "reader-notes.json",
                {
                    **build_reader_notes_payload("Alpha Paper", "2502.05173"),
                    "title": None,
                    "paper_type": None,
                    "problem": None,
                    "main_claim": None,
                    "notation": [],
                    "assumptions": [],
                    "results": [],
                    "limitations": [],
                    "coordinates": {
                        "purpose": [],
                        "problem_form": [],
                        "learning_signal": [],
                        "mechanism": [],
                        "evidence_regime": [],
                    },
                },
            )
            (workspace / "notes" / "fact-ledger.md").write_text("# Fact Ledger\n\n- Add anchored bullets.\n", encoding="utf-8")
            write_json(workspace / "manifests" / "validation-report.json", {"passed": True, "errors": [], "warnings": []})
            write_json(
                workspace / "manifests" / "readthrough-log.json",
                {
                    "completed": True,
                    "chunks_completed": 1,
                    "chunks_total": 1,
                    "chunks": [
                        {
                            "id": "C001",
                            "start_line": 1,
                            "end_line": 10,
                            "section": "section-1",
                            "must_read": True,
                            "read": True,
                            "summary": "Read and indexed chunk C001",
                            "timestamp_utc": "2026-03-12T00:00:00+00:00",
                        }
                    ],
                },
            )

            notes_target = tmp / "documents" / "inproceedings" / "alpha2025paper" / "notes"
            report = batch.publish_workspace(workspace, notes_target, fail_if_exists=False)

            self.assertFalse(report["published"])
            self.assertEqual(report["status"], "failed")
            self.assertIn("semantic_errors", report)
            self.assertTrue(any("generic summary" in message or "substantive" in message for message in report["semantic_errors"]))

    def test_finalize_moves_flat_pdf_and_updates_canonical_file_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            canonical_bib = tmp / "conferences" / "neurips" / "2025.bib"
            canonical_bib.parent.mkdir(parents=True)
            canonical_bib.write_text(
                """@inproceedings{alpha2025paper,
  author = {Ada Lovelace},
  title = {Alpha Paper},
  booktitle = {NeurIPS},
  year = {2025},
  file = {:/tmp/old-alpha.pdf:pdf},
  url = {https://openreview.net/forum?id=test123},
  pdf = {https://openreview.net/pdf?id=test123},
  archiveprefix = {arXiv},
  eprint = {2502.05173}
}
""",
                encoding="utf-8",
            )

            old_pdf = tmp / "documents" / "inproceedings" / "alpha2025paper.pdf"
            old_pdf.parent.mkdir(parents=True)
            old_pdf.write_bytes(b"%PDF-1.4 flat\n")

            notes_dir = tmp / "documents" / "inproceedings" / "alpha2025paper" / "notes"
            write_valid_published_notes_bundle(notes_dir, title="Alpha Paper", arxiv_id="2502.05173")
            workspace = tmp / "run" / "workspaces" / "2502.05173"
            (workspace / "artifacts" / "arxiv" / "pdf").mkdir(parents=True)
            (workspace / "artifacts" / "arxiv" / "pdf" / "2502.05173.pdf").write_bytes(b"%PDF-1.4 fetched\n")

            results_csv = tmp / "run" / "results.csv"
            results_csv.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = batch.READY_FIELDS + [
                "item_id",
                "row_index",
                "status",
                "attempt_count",
                "last_error",
                "result_json",
                "reported_at",
                "completed_at",
            ]
            preferred_pdf = tmp / "documents" / "inproceedings" / "alpha2025paper" / "alpha2025paper.pdf"
            with results_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "job_id": "alpha2025paper",
                        "key": "alpha2025paper",
                        "entry_type": "inproceedings",
                        "title": "Alpha Paper",
                        "year": "2025",
                        "selector_url": "https://openreview.net/forum?id=test123",
                        "selector_pdf": "https://openreview.net/pdf?id=test123",
                        "arxiv_id": "2502.05173",
                        "arxiv_url": "https://arxiv.org/abs/2502.05173",
                        "workspace_dir": str(workspace),
                        "notes_dir": str(notes_dir),
                        "preferred_pdf_path": str(preferred_pdf),
                        "existing_pdf_path": str(old_pdf),
                        "source_bib_files": str(tmp / "collections" / "orals" / "neurips" / "2025.bib"),
                        "target_bib_file": str(canonical_bib),
                        "item_id": "row-1",
                        "row_index": "0",
                        "status": "completed",
                        "attempt_count": "1",
                        "last_error": "",
                        "result_json": json.dumps(
                            {
                                "status": "success",
                                "published_artifacts": sorted(batch.PUBLISHED_ARTIFACTS),
                                "error": "",
                            }
                        ),
                        "reported_at": "",
                        "completed_at": "",
                    }
                )

            summary = batch.finalize_results(results_csv)

            self.assertEqual(summary["finalized_count"], 1)
            self.assertEqual(summary["error_count"], 0)
            self.assertFalse(old_pdf.exists())
            self.assertTrue(preferred_pdf.exists())
            rendered = canonical_bib.read_text(encoding="utf-8")
            self.assertIn(str(preferred_pdf.resolve()), rendered)

    def test_finalize_reports_missing_canonical_entry_for_oral_selector(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            canonical_bib = tmp / "conferences" / "neurips" / "2025.bib"
            canonical_bib.parent.mkdir(parents=True)
            canonical_bib.write_text(
                """@inproceedings{different2025paper,
  author = {Ada Lovelace},
  title = {Different Paper},
  booktitle = {NeurIPS},
  year = {2025}
}
""",
                encoding="utf-8",
            )

            results_csv = tmp / "run" / "results.csv"
            results_csv.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = batch.READY_FIELDS + [
                "item_id",
                "row_index",
                "status",
                "attempt_count",
                "last_error",
                "result_json",
                "reported_at",
                "completed_at",
            ]
            with results_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                notes_dir = tmp / "documents" / "inproceedings" / "alpha2025paper" / "notes"
                write_valid_published_notes_bundle(notes_dir, title="Alpha Paper", arxiv_id="2502.05173")
                writer.writerow(
                    {
                        "job_id": "alpha2025paper",
                        "key": "alpha2025paper",
                        "entry_type": "inproceedings",
                        "title": "Alpha Paper",
                        "year": "2025",
                        "selector_url": "https://openreview.net/forum?id=test123",
                        "selector_pdf": "https://openreview.net/pdf?id=test123",
                        "arxiv_id": "2502.05173",
                        "arxiv_url": "https://arxiv.org/abs/2502.05173",
                        "workspace_dir": str(tmp / "run" / "workspaces" / "2502.05173"),
                        "notes_dir": str(notes_dir),
                        "preferred_pdf_path": str(tmp / "documents" / "inproceedings" / "alpha2025paper" / "alpha2025paper.pdf"),
                        "existing_pdf_path": str(tmp / "documents" / "inproceedings" / "alpha2025paper.pdf"),
                        "source_bib_files": str(tmp / "collections" / "orals" / "neurips" / "2025.bib"),
                        "target_bib_file": str(canonical_bib),
                        "item_id": "row-1",
                        "row_index": "0",
                        "status": "completed",
                        "attempt_count": "1",
                        "last_error": "",
                        "result_json": json.dumps(
                            {
                                "status": "success",
                                "published_artifacts": sorted(batch.PUBLISHED_ARTIFACTS),
                                "error": "",
                            }
                        ),
                        "reported_at": "",
                        "completed_at": "",
                    }
                )

            original_orals_root = batch.ORALS_ROOT
            original_canonical_root = batch.CANONICAL_CONFERENCES_ROOT
            try:
                batch.ORALS_ROOT = (tmp / "collections" / "orals").resolve()
                batch.CANONICAL_CONFERENCES_ROOT = (tmp / "conferences").resolve()
                summary = batch.finalize_results(results_csv)
            finally:
                batch.ORALS_ROOT = original_orals_root
                batch.CANONICAL_CONFERENCES_ROOT = original_canonical_root

            self.assertEqual(summary["error_count"], 1)
            self.assertEqual(summary["rows"][0]["status"], "canonical_entry_missing")

    def test_finalize_rejects_semantically_hollow_published_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            canonical_bib = tmp / "conferences" / "neurips" / "2025.bib"
            canonical_bib.parent.mkdir(parents=True)
            canonical_bib.write_text(
                """@inproceedings{alpha2025paper,
  author = {Ada Lovelace},
  title = {Alpha Paper},
  booktitle = {NeurIPS},
  year = {2025}
}
""",
                encoding="utf-8",
            )

            notes_dir = tmp / "documents" / "inproceedings" / "alpha2025paper" / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "reader-notes.md").write_text(
                "# Reader Notes: Alpha Paper\n\n## 1) One-sentence claim (verifiable)\n[P] Anchor: source/overview; This work’s primary claim is documented but not re-validated in this batch run.\n",
                encoding="utf-8",
            )
            write_json(
                notes_dir / "reader-notes.json",
                {
                    **build_reader_notes_payload("Alpha Paper", "2502.05173"),
                    "paper_type": None,
                    "problem": None,
                    "main_claim": None,
                    "notation": [],
                    "assumptions": [],
                    "results": [],
                    "limitations": [],
                    "coordinates": {
                        "purpose": [],
                        "problem_form": [],
                        "learning_signal": [],
                        "mechanism": [],
                        "evidence_regime": [],
                    },
                },
            )
            (notes_dir / "fact-ledger.md").write_text("# Fact Ledger\n\n- Add anchored bullets.\n", encoding="utf-8")
            write_json(notes_dir / "validation-report.json", {"passed": True, "errors": [], "warnings": []})

            results_csv = tmp / "run" / "results.csv"
            results_csv.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = batch.READY_FIELDS + [
                "item_id",
                "row_index",
                "status",
                "attempt_count",
                "last_error",
                "result_json",
                "reported_at",
                "completed_at",
            ]
            with results_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "job_id": "alpha2025paper",
                        "key": "alpha2025paper",
                        "entry_type": "inproceedings",
                        "title": "Alpha Paper",
                        "year": "2025",
                        "selector_url": "https://openreview.net/forum?id=test123",
                        "selector_pdf": "https://openreview.net/pdf?id=test123",
                        "arxiv_id": "2502.05173",
                        "arxiv_url": "https://arxiv.org/abs/2502.05173",
                        "workspace_dir": str(tmp / "run" / "workspaces" / "2502.05173"),
                        "notes_dir": str(notes_dir),
                        "preferred_pdf_path": str(tmp / "documents" / "inproceedings" / "alpha2025paper" / "alpha2025paper.pdf"),
                        "existing_pdf_path": "",
                        "source_bib_files": str(tmp / "selector.bib"),
                        "target_bib_file": str(canonical_bib),
                        "item_id": "row-1",
                        "row_index": "0",
                        "status": "completed",
                        "attempt_count": "1",
                        "last_error": "",
                        "result_json": json.dumps({"status": "published", "published_artifacts": sorted(batch.PUBLISHED_ARTIFACTS), "error": ""}),
                        "reported_at": "",
                        "completed_at": "",
                    }
                )

            summary = batch.finalize_results(results_csv)

            self.assertEqual(summary["error_count"], 1)
            self.assertEqual(summary["rows"][0]["status"], "notes_audit_failed")


if __name__ == "__main__":
    unittest.main()
