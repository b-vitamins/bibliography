#!/usr/bin/env python3
"""BibTeX key normalization and validation engine for bibops."""

from __future__ import annotations

import dataclasses
import glob
import json
import re
import shutil
from pathlib import Path
from typing import Any

from core.bibkey import (
    entry_signature,
    generate_bib_key,
    key_expected_year,
    suggest_bib_keys,
    synthesize_bib_key,
    validate_bib_key,
)
from core.bibtex_io import parse_bib_file, transactional_write_bib_file


@dataclasses.dataclass
class KeyNormalizeOptions:
    targets: list[str]
    write: bool = False
    canonicalize_all: bool = False
    max_entries: int = 0
    global_scope: str = "targets"  # one of: none, targets, config
    global_paths: list[Path] = dataclasses.field(default_factory=list)
    fail_on_issues: bool = False
    detail_limit: int = 200
    backup: bool = True
    rollback_dir: Path | None = Path("ops/key-normalize-rollbacks")


@dataclasses.dataclass
class KeyIssue:
    file_path: str
    entry_key: str
    issue_type: str
    severity: str
    message: str
    suggestions: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class KeyChange:
    file_path: str
    old_key: str
    new_key: str
    new_entry_type: str
    reason: str


@dataclasses.dataclass
class KeyNormalizeResult:
    summary: dict[str, int | str]
    issue_counts: dict[str, int]
    changes: list[KeyChange]
    issues: list[KeyIssue]


def _expand_targets(targets: list[str]) -> tuple[list[Path], list[str]]:
    paths: list[Path] = []
    unresolved: list[str] = []
    for target in targets:
        matched = glob.glob(target, recursive=True)
        if not matched:
            path = Path(target)
            if path.exists():
                matched = [target]

        if not matched:
            unresolved.append(target)
            continue

        for item in matched:
            path = Path(item)
            if path.exists() and path.is_file() and path.suffix.lower() == ".bib":
                paths.append(path.resolve())

    return sorted(set(paths)), unresolved


_ENTRY_START_RE = re.compile(r"(?im)^\\s*@\\w+\\s*\\{\\s*([^,\\s]+)\\s*,")


def _extract_bib_value(body: str, field: str) -> str:
    match = re.search(rf"(?im)^\\s*{re.escape(field)}\\s*=\\s*", body)
    if not match:
        return ""
    idx = match.end()
    while idx < len(body) and body[idx].isspace():
        idx += 1
    if idx >= len(body):
        return ""

    lead = body[idx]
    if lead == "{":
        depth = 0
        out: list[str] = []
        i = idx
        while i < len(body):
            ch = body[i]
            if ch == "{":
                depth += 1
                if depth > 1:
                    out.append(ch)
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return "".join(out).strip()
                if depth > 0:
                    out.append(ch)
            else:
                if depth > 0:
                    out.append(ch)
            i += 1
        return "".join(out).strip()

    if lead == '"':
        i = idx + 1
        out: list[str] = []
        escaped = False
        while i < len(body):
            ch = body[i]
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                return "".join(out).strip()
            else:
                out.append(ch)
            i += 1
        return "".join(out).strip()

    i = idx
    out = []
    while i < len(body):
        ch = body[i]
        if ch in {",", "\\n", "\\r"}:
            break
        out.append(ch)
        i += 1
    return "".join(out).strip()


def _collect_global_signatures(paths: list[Path]) -> tuple[dict[str, set[str]], int]:
    signatures: dict[str, set[str]] = {}
    parse_errors = 0

    for path in sorted(set(paths)):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            parse_errors += 1
            continue

        starts = list(_ENTRY_START_RE.finditer(text))
        for idx, found in enumerate(starts):
            key = found.group(1).strip()
            if not key:
                continue

            start = found.end()
            end = starts[idx + 1].start() if idx + 1 < len(starts) else len(text)
            body = text[start:end]

            sig = entry_signature(
                year=_extract_bib_value(body, "year"),
                title=_extract_bib_value(body, "title"),
                author=_extract_bib_value(body, "author"),
            )
            signatures.setdefault(key, set()).add(sig)

    return signatures, parse_errors


def _replace_related_keys(value: str, rename_map: dict[str, str]) -> tuple[str, bool]:
    if not value:
        return value, False

    parts = []
    changed = False
    for token in value.replace(";", ",").split(","):
        raw = token.strip()
        if not raw:
            parts.append(raw)
            continue
        repl = rename_map.get(raw)
        if repl and repl != raw:
            parts.append(repl)
            changed = True
        else:
            parts.append(raw)

    if not changed:
        return value, False

    return ", ".join([p for p in parts if p]), True


def _update_reference_fields(entries: list[dict[str, Any]], rename_map: dict[str, str]) -> int:
    if not rename_map:
        return 0

    updated = 0
    direct_fields = ("crossref", "xdata")
    list_fields = ("ids", "related", "relatedentry", "xref")

    for entry in entries:
        for field in direct_fields:
            raw = str(entry.get(field, "")).strip()
            if not raw:
                continue
            replacement = rename_map.get(raw)
            if replacement and replacement != raw:
                entry[field] = replacement
                updated += 1

        for field in list_fields:
            raw = str(entry.get(field, "")).strip()
            if not raw:
                continue
            normalized, changed = _replace_related_keys(raw, rename_map)
            if changed:
                entry[field] = normalized
                updated += 1

    return updated


def _resolve_rename_map(
    file_changes: list[KeyChange],
    final_keys: set[str],
) -> tuple[dict[str, str], int]:
    candidates: dict[str, list[tuple[str, str]]] = {}
    ambiguous = 0
    for change in file_changes:
        old_key = change.old_key
        if not old_key:
            continue
        if old_key in final_keys:
            continue
        candidates.setdefault(old_key, []).append((change.new_key, change.new_entry_type))

    resolved: dict[str, str] = {}
    preferred_types = {"proceedings", "book", "collection", "mvcollection", "reference"}

    for old_key, items in candidates.items():
        unique_new = sorted({new for new, _ in items})
        if len(unique_new) == 1:
            resolved[old_key] = unique_new[0]
            continue

        preferred = sorted({new for new, typ in items if typ in preferred_types})
        if len(preferred) == 1:
            resolved[old_key] = preferred[0]
            ambiguous += 1
            continue

        resolved[old_key] = items[0][0]
        ambiguous += 1

    return resolved, ambiguous


def run_key_normalize(options: KeyNormalizeOptions) -> KeyNormalizeResult:
    files, unresolved = _expand_targets(options.targets)

    summary: dict[str, int | str] = {
        "files_total": len(files),
        "files_modified": 0,
        "entries_total": 0,
        "entries_processed": 0,
        "entries_renamed": 0,
        "issues_total": 0,
        "parse_errors": 0,
        "global_parse_errors": 0,
        "unresolved_targets": len(unresolved),
        "reference_updates": 0,
        "global_scope": options.global_scope,
        "wrote_changes": 1 if options.write else 0,
    }

    issue_counts: dict[str, int] = {}
    changes: list[KeyChange] = []
    issues: list[KeyIssue] = []

    global_signatures: dict[str, set[str]] = {}
    if options.global_scope not in {"none", "targets", "config"}:
        raise ValueError("global_scope must be one of: none, targets, config")

    if options.global_scope == "targets":
        global_signatures, g_errors = _collect_global_signatures(files)
        summary["global_parse_errors"] = g_errors
    elif options.global_scope == "config":
        global_signatures, g_errors = _collect_global_signatures(options.global_paths)
        summary["global_parse_errors"] = g_errors

    for path in files:
        try:
            db = parse_bib_file(path)
        except Exception as ex:
            summary["parse_errors"] = int(summary["parse_errors"]) + 1
            issue = KeyIssue(
                file_path=str(path),
                entry_key="*",
                issue_type="parse_error",
                severity="error",
                message=f"failed to parse BibTeX file: {ex}",
            )
            issues.append(issue)
            issue_counts[issue.issue_type] = issue_counts.get(issue.issue_type, 0) + 1
            continue

        entries = db.entries
        summary["entries_total"] = int(summary["entries_total"]) + len(entries)

        baseline_entries = len(entries)
        baseline_comments = len(db.comments)

        reserved_keys: set[str] = set()
        file_changes: list[KeyChange] = []

        for idx, entry in enumerate(entries, start=1):
            if options.max_entries and idx > options.max_entries:
                break

            summary["entries_processed"] = int(summary["entries_processed"]) + 1

            old_key = str(entry.get("ID", "")).strip()
            expected_year = key_expected_year(entry)
            title = str(entry.get("title", ""))
            author = str(entry.get("author", ""))

            key_issues = validate_bib_key(
                old_key,
                expected_year=None if expected_year == "0000" else expected_year,
            )

            entry_sig = entry_signature(
                year=str(entry.get("year", "")),
                title=title,
                author=author,
            )

            global_conflict = False
            if old_key and global_signatures:
                existing = global_signatures.get(old_key, set())
                if existing and entry_sig not in existing:
                    global_conflict = True
                    key_issues.append("key collides with a different global entry signature")

            has_conflict_with_reserved = bool(old_key and old_key in reserved_keys)
            needs_rename = bool(key_issues) or has_conflict_with_reserved

            canonical_key = synthesize_bib_key(author=author, year=expected_year, title=title)
            if options.canonicalize_all and old_key and old_key != canonical_key:
                needs_rename = True

            if not needs_rename and old_key:
                reserved_keys.add(old_key)
                continue

            first_author = author.split(" and ")[0].strip() if author else "paper"
            new_key = generate_bib_key(
                first_author=first_author,
                year=expected_year,
                title=title,
                existing_keys=reserved_keys,
                global_key_signatures=global_signatures,
                candidate_signature=entry_sig,
            )

            if old_key == new_key:
                continue

            entry["ID"] = new_key
            change = KeyChange(
                file_path=str(path),
                old_key=old_key,
                new_key=new_key,
                new_entry_type=str(entry.get("ENTRYTYPE", "")).strip().lower(),
                reason="normalized key format",
            )
            file_changes.append(change)
            changes.append(change)
            summary["entries_renamed"] = int(summary["entries_renamed"]) + 1

            suggestions = suggest_bib_keys(author=author, year=expected_year, title=title, limit=3)
            issue_message = "normalized key"
            if key_issues:
                issue_message = "; ".join(sorted(set(key_issues)))

            if len(issues) < options.detail_limit:
                issue = KeyIssue(
                    file_path=str(path),
                    entry_key=old_key or "*",
                    issue_type="key_normalized",
                    severity="warning",
                    message=issue_message,
                    suggestions=suggestions,
                )
                issues.append(issue)

            issue_counts["key_normalized"] = issue_counts.get("key_normalized", 0) + 1
            if has_conflict_with_reserved:
                issue_counts["duplicate_key_in_file"] = issue_counts.get("duplicate_key_in_file", 0) + 1
            if global_conflict:
                issue_counts["duplicate_key_global"] = issue_counts.get("duplicate_key_global", 0) + 1

        if file_changes:
            final_keys = {str(entry.get("ID", "")).strip() for entry in entries}
            rename_map, ambiguous_mappings = _resolve_rename_map(file_changes, final_keys)

            refs_updated = _update_reference_fields(entries, rename_map)
            summary["reference_updates"] = int(summary["reference_updates"]) + refs_updated
            if ambiguous_mappings:
                issue_counts["reference_mapping_ambiguous"] = (
                    issue_counts.get("reference_mapping_ambiguous", 0) + ambiguous_mappings
                )

            if options.write:
                if options.backup:
                    backup_path = path.with_suffix(path.suffix + ".backup")
                    shutil.copy2(path, backup_path)
                transactional_write_bib_file(
                    path,
                    db,
                    baseline_entries=baseline_entries,
                    baseline_comments=baseline_comments,
                    rollback_dir=options.rollback_dir,
                )
                summary["files_modified"] = int(summary["files_modified"]) + 1

    summary["issues_total"] = sum(issue_counts.values()) + int(summary["parse_errors"])

    return KeyNormalizeResult(
        summary=summary,
        issue_counts=issue_counts,
        changes=changes,
        issues=issues,
    )


def result_to_json(result: KeyNormalizeResult, *, detail_limit: int = 200) -> str:
    payload = {
        "summary": result.summary,
        "issue_counts": result.issue_counts,
        "changes": [dataclasses.asdict(c) for c in result.changes[: max(0, detail_limit)]],
        "issues": [dataclasses.asdict(i) for i in result.issues[: max(0, detail_limit)]],
    }
    omitted_changes = max(0, len(result.changes) - max(0, detail_limit))
    omitted_issues = max(0, len(result.issues) - max(0, detail_limit))
    if omitted_changes:
        payload["changes_omitted"] = omitted_changes
    if omitted_issues:
        payload["issues_omitted"] = omitted_issues
    return json.dumps(payload, indent=2, sort_keys=True)
