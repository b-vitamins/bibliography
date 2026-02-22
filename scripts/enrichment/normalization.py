from __future__ import annotations

import html
import re
import unicodedata


def strip_latex(value: str) -> str:
    text = value or ""
    # Some upstream dumps escape LaTeX commands as "\textbackslash cmd\lbrace...\rbrace".
    # Rehydrate those forms so command stripping can preserve meaningful content.
    text = text.replace(r"\textbackslash", "\\")
    text = text.replace(r"\lbrace", "{").replace(r"\rbrace", "}")
    text = text.replace("łbrace", "{").replace("Łbrace", "{")
    text = text.replace("ŕbrace", "}").replace("Ŕbrace", "}")
    text = re.sub(r"\\\s+", r"\\", text)
    text = re.sub(r"\\\^\s*\{\s*\}", " ", text)
    text = re.sub(r"\b(?:lbrace|rbrace|brace)\b", " ", text, flags=re.I)
    text = text.replace("\\&", "&")
    # Preserve command arguments: "\texttt{LeadCache}" -> "LeadCache".
    wrapped_cmd = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
    while True:
        updated = wrapped_cmd.sub(r" \1 ", text)
        if updated == text:
            break
        text = updated
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return text.replace("\\", " ")


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_text(value: str) -> str:
    text = html.unescape(value or "")
    text = strip_latex(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return normalize_spaces(text)


def sanitize_bibtex_text(value: str) -> str:
    """Drop unbalanced braces so serialized BibTeX remains parse-stable."""
    text = value or ""
    chars = list(text)
    unmatched_open: list[int] = []
    unmatched_close: list[int] = []
    stack: list[int] = []

    for idx, ch in enumerate(chars):
        if ch not in {"{", "}"}:
            continue
        if ch == "{":
            stack.append(idx)
            continue
        # ch == "}"
        if stack:
            stack.pop()
        else:
            unmatched_close.append(idx)

    unmatched_open = stack
    if not unmatched_open and not unmatched_close:
        return text

    # Escaping as \{ or \} is still interpreted structurally by some BibTeX
    # parsers during round-trip, so remove only unmatched braces.
    to_drop = set(unmatched_open + unmatched_close)
    out: list[str] = []
    for idx, ch in enumerate(chars):
        if idx in to_drop:
            continue
        out.append(ch)
    return "".join(out)


def equivalent_text(left: str, right: str) -> bool:
    return normalize_text(left) == normalize_text(right)


def is_prefix_equivalent(left: str, right: str) -> bool:
    a = normalize_text(left)
    b = normalize_text(right)
    return bool(a and b and (a.startswith(b) or b.startswith(a)))


def word_count(value: str) -> int:
    return len(normalize_spaces(value).split()) if value else 0
