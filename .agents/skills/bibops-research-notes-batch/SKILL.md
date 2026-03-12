---
name: bibops-research-notes-batch
description: Generate validated research-paper-notes artifacts for many papers selected from bibliography files or oral cohorts, publishing durable notes under /home/b/documents/<entrytype>/<key>/notes/. Use when asked for batch research notes such as all 2025 NeurIPS orals.
---

Use this when the user wants research notes for a cohort of papers rather than a single paper.

This skill composes the global `research-paper-notes` worker skill. It uses bibliography files as selectors, plans one isolated job per paper with an arXiv ID, skips entries without arXiv by default, runs workers in parallel, publishes durable note artifacts into `/home/b/documents/<entrytype>/<key>/notes/`, and then serializes the post-run document relayout so canonical `file` fields can be updated safely.

## Execute

1. Resolve the cohort to one or more `.bib` files.
   - For venue-year oral requests, use `collections/orals/<venue>/<year>.bib` as the selector.
   - Treat `collections/orals/` as read-only derived selectors, never as canonical files to mutate.
2. Build the batch plan:
   - `python3 scripts/research_notes_batch.py plan collections/orals/neurips/2025.bib --json`
   - The planner writes `batch-plan.json`, `summary.json`, `jobs.csv`, `skipped.csv`, and a `workspaces/` directory under a fresh run root in `/home/b/trash/research-notes-batch-runs/` unless `--run-root` is supplied.
3. Review the summary:
   - Dispatch only rows in `jobs.csv`.
   - Missing arXiv should remain `skip_missing_arxiv` unless the user explicitly asks for manual recovery.
4. Fan out one worker per row with bounded concurrency.
   - Prefer `spawn_agents_on_csv` for medium or large batches.
   - The worker must explicitly use `research-paper-notes`.
5. Each worker should:
   - Generate notes for `{arxiv_url}` in a fresh workspace rooted at `{workspace_dir}`.
   - Validate the workspace successfully.
   - Publish the durable outputs with:
     - `python3 scripts/research_notes_batch.py publish --workspace "{workspace_dir}" --notes-dir "{notes_dir}" --json`
   - Treat the publish step as authoritative: if publish returns anything other than `status = "published"`, report failure and do not synthesize a success status.
6. After the worker fanout completes, run the serial finalize stage:
   - `python3 scripts/research_notes_batch.py finalize --results-csv <results.csv> --json`
   - This stage moves an existing flat cached PDF into `/home/b/documents/<entrytype>/<key>/<key>.pdf` when available, falls back to the worker-fetched arXiv PDF when needed, and updates the canonical bibliography entry `file` field.
   - If the selector came from `collections/orals/`, resolve the canonical write target in `conferences/<venue>/<year>.bib`. Never mutate the oral selector file itself.
7. Summarize the batch results from the exported worker CSV, the finalize report, and the planner outputs.

## Worker instruction template

Use this template with `spawn_agents_on_csv`:

```text
Use the global research-paper-notes skill for arXiv paper {arxiv_id} ({title}). Work only in the isolated workspace {workspace_dir}. Generate a fresh strict TeX-first notes workspace, complete the readthrough, write the final artifacts, and ensure validation passes. Then publish the durable artifacts into {notes_dir} with `python3 scripts/research_notes_batch.py publish --workspace "{workspace_dir}" --notes-dir "{notes_dir}" --json`. Do not modify any `.bib` files directly from the worker. Return a JSON result with `status: "published"` only when the publish command itself returns `status: "published"`; otherwise return a failure status and include the publish error. Also return key, arxiv_id, workspace_dir, notes_dir, published_artifacts, and any error.
```

## Constraints

- Do not treat missing arXiv IDs as a browsing task by default; record a skip.
- Keep temporary workspaces outside the repo.
- Publish only final note artifacts to `/home/b/documents/<entrytype>/<key>/notes/`, not the full staging workspace.
- The publish step performs a semantic audit and must reject placeholder notes, empty machine-readable fields, generic readthrough summaries, and untouched fact-ledger templates.
- Treat `collections/orals/` as selector-only input. Any `file` field update belongs in the canonical conference file, never in the oral subset file.
