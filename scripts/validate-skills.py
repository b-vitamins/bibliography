#!/usr/bin/env python3
"""Validate repository skills under .agents/skills."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("missing YAML frontmatter block")

    data: dict[str, str] = {}
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def validate_skill_dir(path: Path) -> list[str]:
    errors: list[str] = []
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        return [f"{path}: missing SKILL.md"]

    try:
        fm = parse_frontmatter(skill_md)
    except Exception as ex:
        return [f"{path}: {ex}"]

    name = fm.get("name", "")
    desc = fm.get("description", "")

    if not name:
        errors.append(f"{path}: frontmatter missing name")
    if not desc:
        errors.append(f"{path}: frontmatter missing description")

    if name and not NAME_RE.match(name):
        errors.append(f"{path}: invalid skill name `{name}`")

    if name and name != path.name:
        errors.append(f"{path}: name `{name}` does not match directory `{path.name}`")

    openai_yaml = path / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        errors.append(f"{path}: missing recommended agents/openai.yaml")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate .agents skills")
    parser.add_argument("--root", default=".agents/skills", help="skills root")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"skills root not found: {root}", file=sys.stderr)
        return 2

    all_errors: list[str] = []
    skill_dirs = sorted([p for p in root.iterdir() if p.is_dir()])

    for d in skill_dirs:
        all_errors.extend(validate_skill_dir(d))

    if all_errors:
        print("skill validation: FAILED")
        for e in all_errors:
            print(f"- {e}")
        return 1

    print(f"skill validation: OK ({len(skill_dirs)} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
