# Operations Config

`ops/` is for versioned operational policy: scopes, profiles, source policies,
retry/pacing settings, and documented exceptions.

Runtime state does not belong here by default. Reports, unresolved queues,
checkpoints, caches, progress logs, and rollback artifacts default to
`tmp/bibops/`, which is ignored by Git. Set `BIBOPS_RUNTIME_DIR` to redirect
those transient files for a long run.

Commit files in this directory only when they change reusable behavior.

The full-text bootstrap profiles, `profiles/fulltext-active.toml` and
`profiles/fulltext-conferences.toml`, first use `pdf-sync --no-download` to
migrate valid cached PDFs into per-entry document workspaces under
`/home/b/documents/<entrytype>/<bibkey>/`, then run GROBID full-text extraction.
They write raw TEI as `<bibkey>.tei.xml` and compact provenance as
`<bibkey>.grobid.json`; derived search/chunk/embedding artifacts should be
generated outside BibTeX from that TEI layer.

The full-text profiles read explicit target queues from
`fulltext-active-targets.txt` and `fulltext-conference-targets.txt`. The
conference queue starts with ICLR, NeurIPS, and ICML interleaved by per-venue
recency, then processes AISTATS, COLT, and UAI by the same recency rule. Active
non-conference files follow after conferences, with long-form books last.

`fulltext-sync` uses `pdfinfo` lazily, in bounded dispatch batches, to classify
PDFs into page-count tiers before submitting each batch to GROBID. Current
TEI/provenance pairs are skipped from cached PDF identity without rerunning
`pdfinfo`. The default worker count is CPU-derived (`--workers 0`): article PDFs
run wider, unknown/medium PDFs run narrower, and long/huge PDFs are serialized
with longer read timeouts so books and long reports do not starve the article
corpus.

The GROBID request follows `grobid-client-python`'s transport pattern, not its
lean default extraction profile: bounded batches, threaded HTTP requests,
multipart file metadata, and retry/backoff for 503 server busy responses. The
default extraction profile remains high-information-density:
header consolidation, raw citations, sentence segmentation, and TEI coordinates
for `figure`, `formula`, `ref`, and `biblStruct` are enabled. Citation
consolidation, funder consolidation, raw affiliations, and raw copyright text
are disabled by default because they are high-cost and low-value for the bulk
conference corpus.
