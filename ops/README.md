# Operations Config

`ops/` is for versioned operational policy: scopes, profiles, source policies,
retry/pacing settings, and documented exceptions.

Runtime state does not belong here by default. Reports, unresolved queues,
checkpoints, caches, progress logs, and rollback artifacts default to
`tmp/bibops/`, which is ignored by Git. Set `BIBOPS_RUNTIME_DIR` to redirect
those transient files for a long run.

Commit files in this directory only when they change reusable behavior.
