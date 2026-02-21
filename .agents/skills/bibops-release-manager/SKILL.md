---
name: bibops-release-manager
description: Execute the release workflow with hooks, linting, tracking export, and milestone commit checks. Use when preparing release-quality bibliography updates or finalizing a collection change set.
---

Run the release checklist and produce commit-ready status.

## Execute

1. Run `scripts/run_release.sh`.
2. Confirm release profile completed successfully.
3. Review `git status --short` and ensure only intended files are staged/committed.
4. Group commits by milestone: infrastructure, policy/workflow, data curation.

## Constraints

- Do not bypass hooks.
- Do not include unrelated modified files in release commits.
- Keep commit messages compliant with repository policy.
