from __future__ import annotations

import dataclasses
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

VALID_ROLES = {"canonical", "curated", "derived", "archive", "auxiliary"}
DEFAULT_MANIFEST_PATH = Path("meta/bibmeta.toml")
_INLINE_LABEL = "bibmeta"
_LEGACY_NAMESPACES = ("folio", "mundaneum")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BibmetaManifestError(RuntimeError):
    """Manifest load/validation failure."""


@dataclasses.dataclass(frozen=True)
class BibmetaRule:
    index: int
    name: str
    glob: str
    exclude: tuple[str, ...]
    role: str
    subject: str | None
    topics: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class BibmetaManifest:
    version: int
    rules: tuple[BibmetaRule, ...]
    path: Path


@dataclasses.dataclass(frozen=True)
class InlineBibmetaBlock:
    start: int
    end: int
    raw: str
    body: str


@dataclasses.dataclass(frozen=True)
class BibmetaDiagnostic:
    file_path: str
    code: str
    severity: str
    message: str
    details: dict[str, str]


@dataclasses.dataclass(frozen=True)
class ResolvedBibmeta:
    file_path: str
    role: str | None
    subject: str | None
    topics: tuple[str, ...]
    rule_name: str | None
    inline_present: bool


def discover_repo_bib_files(repo_root: Path = Path(".")) -> list[Path]:
    out: list[Path] = []
    for path in repo_root.rglob("*.bib"):
        rel = path.relative_to(repo_root)
        if any(part in {".git", "__pycache__"} for part in rel.parts):
            continue
        if path.name.endswith(".backup") or path.name.endswith(".bak"):
            continue
        out.append(path)
    return sorted(set(out))


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> BibmetaManifest:
    if not path.exists():
        raise BibmetaManifestError(f"manifest not found: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BibmetaManifestError(f"failed to parse TOML manifest {path}: {exc}") from exc

    allowed_top_level = {"version", "rules"}
    extra_top_level = sorted(set(data) - allowed_top_level)
    if extra_top_level:
        raise BibmetaManifestError(
            f"unknown top-level manifest keys in {path}: {', '.join(extra_top_level)}"
        )

    version = data.get("version")
    if version != 1:
        raise BibmetaManifestError(f"unsupported bibmeta manifest version: {version!r}")

    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise BibmetaManifestError("manifest must define a non-empty [[rules]] array")

    rules: list[BibmetaRule] = []
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise BibmetaManifestError(f"rule #{index + 1} must be a table")
        rules.append(_load_rule(raw_rule, index))

    return BibmetaManifest(version=version, rules=tuple(rules), path=path)


def _load_rule(raw_rule: dict[str, Any], index: int) -> BibmetaRule:
    allowed = {"name", "glob", "exclude", "role", "subject", "topics"}
    extra = sorted(set(raw_rule) - allowed)
    if extra:
        raise BibmetaManifestError(
            f"rule #{index + 1} has unknown keys: {', '.join(extra)}"
        )

    glob = raw_rule.get("glob")
    if not isinstance(glob, str) or not glob.strip():
        raise BibmetaManifestError(f"rule #{index + 1} must define non-empty `glob`")

    role = raw_rule.get("role")
    if not isinstance(role, str) or role not in VALID_ROLES:
        raise BibmetaManifestError(
            f"rule #{index + 1} has invalid role {role!r}; expected one of {sorted(VALID_ROLES)}"
        )

    exclude_raw = raw_rule.get("exclude", [])
    if exclude_raw is None:
        exclude_raw = []
    if not isinstance(exclude_raw, list) or any(not isinstance(item, str) for item in exclude_raw):
        raise BibmetaManifestError(f"rule #{index + 1} `exclude` must be a list of strings")

    subject = raw_rule.get("subject")
    if subject is not None and not isinstance(subject, str):
        raise BibmetaManifestError(f"rule #{index + 1} `subject` must be a string")

    topics_raw = raw_rule.get("topics", [])
    if topics_raw is None:
        topics_raw = []
    if not isinstance(topics_raw, list) or any(not isinstance(item, str) for item in topics_raw):
        raise BibmetaManifestError(f"rule #{index + 1} `topics` must be a list of strings")

    rule = BibmetaRule(
        index=index,
        name=str(raw_rule.get("name") or f"rule-{index + 1}"),
        glob=glob,
        exclude=tuple(exclude_raw),
        role=role,
        subject=subject,
        topics=tuple(topics_raw),
    )

    _validate_role_fields(
        role=rule.role,
        subject=rule.subject,
        topics=rule.topics,
        context=f"manifest rule `{rule.name}`",
        strict=True,
    )
    return rule


def validate_repo_bibmeta(
    repo_root: Path = Path("."),
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    paths: list[Path] | None = None,
) -> tuple[BibmetaManifest | None, list[BibmetaDiagnostic], dict[str, ResolvedBibmeta]]:
    diagnostics: list[BibmetaDiagnostic] = []
    try:
        manifest = load_manifest(manifest_path)
    except BibmetaManifestError as exc:
        diagnostics.append(
            BibmetaDiagnostic(
                file_path=str(manifest_path),
                code="manifest_invalid",
                severity="error",
                message=str(exc),
                details={},
            )
        )
        return None, diagnostics, {}

    targets = paths if paths is not None else discover_repo_bib_files(repo_root)
    resolved: dict[str, ResolvedBibmeta] = {}
    for path in targets:
        resolution, issues = validate_bib_file(path, manifest=manifest, repo_root=repo_root)
        resolved[str(path)] = resolution
        diagnostics.extend(issues)
    return manifest, diagnostics, resolved


def validate_bib_file(
    path: Path,
    *,
    manifest: BibmetaManifest,
    repo_root: Path = Path("."),
    text: str | None = None,
) -> tuple[ResolvedBibmeta, list[BibmetaDiagnostic]]:
    file_path = str(path)
    rel_path = _relative_posix(path, repo_root)
    text = path.read_text(encoding="utf-8") if text is None else text
    diagnostics: list[BibmetaDiagnostic] = []

    for namespace in _LEGACY_NAMESPACES:
        pattern = re.compile(rf"@COMMENT\s*\{{\s*{re.escape(namespace)}\s*:", re.IGNORECASE)
        if pattern.search(text):
            diagnostics.append(
                BibmetaDiagnostic(
                    file_path=file_path,
                    code="legacy_namespace",
                    severity="error",
                    message=f"legacy @{namespace} metadata namespace is not allowed",
                    details={"namespace": namespace},
                )
            )

    defaults, rule = _resolve_defaults(rel_path, manifest)
    if rule is None:
        diagnostics.append(
            BibmetaDiagnostic(
                file_path=file_path,
                code="unmatched_file",
                severity="error",
                message="file does not match any bibmeta rule",
                details={"relative_path": rel_path},
            )
        )
        resolution = ResolvedBibmeta(
            file_path=file_path,
            role=None,
            subject=None,
            topics=tuple(),
            rule_name=None,
            inline_present=False,
        )
        return resolution, diagnostics

    inline_blocks = find_inline_bibmeta_blocks(text)
    inline_present = bool(inline_blocks)
    if len(inline_blocks) > 1:
        diagnostics.append(
            BibmetaDiagnostic(
                file_path=file_path,
                code="inline_duplicate",
                severity="error",
                message="at most one @COMMENT{bibmeta: ...} block is allowed per file",
                details={"count": str(len(inline_blocks))},
            )
        )

    merged = dict(defaults)
    inline_payload: dict[str, Any] = {}

    if inline_blocks:
        block = inline_blocks[0]
        if not _is_leading_trivia(text[: block.start]):
            diagnostics.append(
                BibmetaDiagnostic(
                    file_path=file_path,
                    code="inline_not_top_of_file",
                    severity="error",
                    message="inline bibmeta block must appear before the first real BibTeX directive",
                    details={},
                )
            )

        try:
            inline_payload = _parse_inline_body(block.body)
        except BibmetaManifestError as exc:
            diagnostics.append(
                BibmetaDiagnostic(
                    file_path=file_path,
                    code="inline_parse_error",
                    severity="error",
                    message=str(exc),
                    details={},
                )
            )
        else:
            merged = _merge_inline(defaults, inline_payload)
            if _metadata_equal(defaults, merged):
                diagnostics.append(
                    BibmetaDiagnostic(
                        file_path=file_path,
                        code="inline_redundant",
                        severity="error",
                        message="inline bibmeta block redundantly restates path-derived metadata",
                        details={"relative_path": rel_path, "rule": rule.name},
                    )
                )

    diagnostics.extend(
        _validate_resolved_metadata(
            file_path=file_path,
            role=merged.get("role"),
            subject=merged.get("subject"),
            topics=merged.get("topics") or (),
        )
    )

    resolution = ResolvedBibmeta(
        file_path=file_path,
        role=merged.get("role"),
        subject=merged.get("subject"),
        topics=tuple(merged.get("topics") or ()),
        rule_name=rule.name,
        inline_present=inline_present,
    )
    return resolution, diagnostics


def resolve_bibmeta(
    path: Path,
    *,
    manifest: BibmetaManifest,
    repo_root: Path = Path("."),
    text: str | None = None,
) -> ResolvedBibmeta:
    resolution, diagnostics = validate_bib_file(path, manifest=manifest, repo_root=repo_root, text=text)
    errors = [diag for diag in diagnostics if diag.severity == "error"]
    if errors:
        joined = "; ".join(diag.message for diag in errors)
        raise BibmetaManifestError(f"bibmeta validation failed for {path}: {joined}")
    return resolution


def find_inline_bibmeta_blocks(text: str) -> list[InlineBibmetaBlock]:
    blocks: list[InlineBibmetaBlock] = []
    upper = text.upper()
    cursor = 0
    needle = "@COMMENT"
    while True:
        idx = upper.find(needle, cursor)
        if idx == -1:
            break
        brace_idx = idx + len(needle)
        while brace_idx < len(text) and text[brace_idx].isspace():
            brace_idx += 1
        if brace_idx >= len(text) or text[brace_idx] != "{":
            cursor = idx + len(needle)
            continue
        end = _find_matching_brace(text, brace_idx)
        if end is None:
            cursor = brace_idx + 1
            continue
        raw = text[idx : end + 1]
        inner = text[brace_idx + 1 : end]
        stripped = inner.lstrip()
        if stripped.lower().startswith(f"{_INLINE_LABEL}:"):
            body = stripped[len(_INLINE_LABEL) + 1 :]
            blocks.append(InlineBibmetaBlock(start=idx, end=end + 1, raw=raw, body=body))
        cursor = end + 1
    return blocks


def _find_matching_brace(text: str, open_brace_idx: int) -> int | None:
    depth = 0
    in_string = False
    escape = False
    for idx in range(open_brace_idx, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return idx
    return None


def _parse_inline_body(body: str) -> dict[str, Any]:
    try:
        data = tomllib.loads(body)
    except tomllib.TOMLDecodeError as exc:
        raise BibmetaManifestError(f"invalid TOML in inline bibmeta block: {exc}") from exc

    allowed = {"role", "subject", "topics", "topics_append", "replace_topics"}
    extra = sorted(set(data) - allowed)
    if extra:
        raise BibmetaManifestError(
            f"inline bibmeta block has unknown keys: {', '.join(extra)}"
        )

    role = data.get("role")
    if role is not None and (not isinstance(role, str) or role not in VALID_ROLES):
        raise BibmetaManifestError(
            f"inline bibmeta `role` must be one of {sorted(VALID_ROLES)}"
        )

    subject = data.get("subject")
    if subject is not None and not isinstance(subject, str):
        raise BibmetaManifestError("inline bibmeta `subject` must be a string")

    for list_key in ("topics", "topics_append"):
        value = data.get(list_key)
        if value is not None and (
            not isinstance(value, list) or any(not isinstance(item, str) for item in value)
        ):
            raise BibmetaManifestError(f"inline bibmeta `{list_key}` must be a list of strings")

    replace_topics = data.get("replace_topics")
    if replace_topics is not None and not isinstance(replace_topics, bool):
        raise BibmetaManifestError("inline bibmeta `replace_topics` must be a boolean")

    return data


def _merge_inline(defaults: dict[str, Any], inline: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "role": defaults.get("role"),
        "subject": defaults.get("subject"),
        "topics": list(defaults.get("topics") or []),
    }
    if "role" in inline:
        merged["role"] = inline["role"]
    if "subject" in inline:
        merged["subject"] = inline["subject"]

    topics = list(merged["topics"])
    replace_topics = bool(inline.get("replace_topics", False))
    if replace_topics:
        topics = []
    if "topics" in inline:
        if replace_topics:
            topics = list(inline["topics"])
        else:
            topics = _merge_topics(topics, inline["topics"])
    if "topics_append" in inline:
        topics = _merge_topics(topics, inline["topics_append"])
    merged["topics"] = topics
    return merged


def _merge_topics(base: list[str], extra: list[str]) -> list[str]:
    out = list(base)
    seen = set(base)
    for item in extra:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _metadata_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("role") == right.get("role")
        and left.get("subject") == right.get("subject")
        and tuple(left.get("topics") or ()) == tuple(right.get("topics") or ())
    )


def _validate_resolved_metadata(
    *,
    file_path: str,
    role: str | None,
    subject: str | None,
    topics: tuple[str, ...] | list[str],
) -> list[BibmetaDiagnostic]:
    topics_tuple = tuple(topics)
    diagnostics: list[BibmetaDiagnostic] = []
    if role not in VALID_ROLES:
        diagnostics.append(
            BibmetaDiagnostic(
                file_path=file_path,
                code="role_invalid",
                severity="error",
                message=f"resolved role is invalid: {role!r}",
                details={},
            )
        )
        return diagnostics

    try:
        _validate_role_fields(role=role, subject=subject, topics=topics_tuple, context=file_path, strict=True)
    except BibmetaManifestError as exc:
        diagnostics.append(
            BibmetaDiagnostic(
                file_path=file_path,
                code="field_combo_invalid",
                severity="error",
                message=str(exc),
                details={},
            )
        )

    if subject is not None and not _SLUG_RE.match(subject):
        diagnostics.append(
            BibmetaDiagnostic(
                file_path=file_path,
                code="subject_invalid",
                severity="error",
                message=f"subject slug must be lowercase kebab-case: {subject!r}",
                details={"subject": subject},
            )
        )

    bad_topics = [topic for topic in topics_tuple if not _SLUG_RE.match(topic)]
    if bad_topics:
        diagnostics.append(
            BibmetaDiagnostic(
                file_path=file_path,
                code="topics_invalid",
                severity="error",
                message="topic slugs must be lowercase kebab-case",
                details={"topics": ", ".join(bad_topics)},
            )
        )
    return diagnostics


def _validate_role_fields(
    *,
    role: str,
    subject: str | None,
    topics: tuple[str, ...],
    context: str,
    strict: bool,
) -> None:
    if role == "canonical":
        if topics:
            raise BibmetaManifestError(f"{context} cannot define topics for role `canonical`")
        return
    if role == "curated":
        if subject is not None:
            raise BibmetaManifestError(f"{context} cannot define subject for role `curated`")
        if strict and not topics:
            raise BibmetaManifestError(f"{context} must define at least one topic for role `curated`")
        return
    if subject is not None or topics:
        raise BibmetaManifestError(
            f"{context} cannot define subject/topics for role `{role}`"
        )


def _resolve_defaults(rel_path: str, manifest: BibmetaManifest) -> tuple[dict[str, Any], BibmetaRule | None]:
    placeholders = _placeholder_context(rel_path)
    pure = PurePosixPath(rel_path)
    for rule in manifest.rules:
        if not _match_glob(pure, rule.glob):
            continue
        if any(_match_glob(pure, pattern) for pattern in rule.exclude):
            continue
        return (
            {
                "role": rule.role,
                "subject": _apply_template(rule.subject, placeholders) if rule.subject is not None else None,
                "topics": [
                    _apply_template(topic, placeholders)
                    for topic in rule.topics
                ],
            },
            rule,
        )
    return {}, None


def _match_glob(path: PurePosixPath, pattern: str) -> bool:
    if path.match(pattern):
        return True
    if "/**/" in pattern:
        simplified = pattern.replace("/**/", "/")
        if path.match(simplified):
            return True
    if pattern.startswith("**/") and path.match(pattern[3:]):
        return True
    return False


def _placeholder_context(rel_path: str) -> dict[str, str]:
    pure = PurePosixPath(rel_path)
    parent = pure.parent.name if pure.parent != PurePosixPath('.') else ""
    grandparent = pure.parent.parent.name if len(pure.parents) > 1 else ""
    return {
        "stem": pure.stem,
        "parent": parent,
        "grandparent": grandparent,
    }


def _apply_template(value: str, placeholders: dict[str, str]) -> str:
    out = value
    for key, replacement in placeholders.items():
        out = out.replace(f"{{{key}}}", replacement)
    return out


def _relative_posix(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _is_leading_trivia(text: str) -> bool:
    if not text:
        return True
    stripped_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%"):
            continue
        stripped_lines.append(line)
    return not stripped_lines
