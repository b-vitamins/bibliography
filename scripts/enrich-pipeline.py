#!/usr/bin/env python3
"""Run modular, source-grounded bibliography enrichment workflows."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from enrichment.bibtex_io import resolve_bib_paths
from enrichment.config import DEFAULT_CONFIG_PATH, load_pipeline_config
from enrichment.engine import EnrichmentEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bibliography enrichment pipeline")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Pipeline config TOML path",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Plan enrichment candidates")
    plan.add_argument("targets", nargs="+", help="BibTeX file(s) or glob(s)")
    plan.add_argument("--entry-key", action="append", default=[], help="Limit to specific entry key (repeatable)")
    plan.add_argument("--max-entries", type=int, default=0, help="Cap planned entries per file")
    plan.add_argument("--overwrite", action="store_true", help="Plan overwrite candidates too")
    plan.add_argument("--json", action="store_true", help="Emit JSON")
    plan.add_argument("--out", help="Optional path to write plan JSON")

    run = sub.add_parser("run", help="Execute enrichment")
    run.add_argument("targets", nargs="+", help="BibTeX file(s) or glob(s)")
    run.add_argument("--entry-key", action="append", default=[], help="Limit to specific entry key (repeatable)")
    run.add_argument("--max-entries", type=int, default=0, help="Cap processed entries per file")
    run.add_argument("--overwrite", action="store_true", help="Allow non-protected field overwrite")
    run.add_argument("--write", action="store_true", help="Write approved updates to target file")
    run.add_argument("--json", action="store_true", help="Emit JSON")
    run.add_argument(
        "--fail-on-unresolved",
        action="store_true",
        help="Return non-zero when unresolved/error decisions exist",
    )

    return parser


def cmd_plan(args: argparse.Namespace) -> int:
    cfg = load_pipeline_config(Path(args.config))
    files = resolve_bib_paths(args.targets)
    if not files:
        print("No .bib files matched targets", file=sys.stderr)
        return 1

    engine = EnrichmentEngine(cfg)
    try:
        entry_keys = set(args.entry_key) if args.entry_key else None
        payload: dict[str, object] = {"config": str(cfg.config_path), "files": []}

        for file_path in files:
            items = engine.plan(
                file_path=file_path,
                entry_keys=entry_keys,
                max_entries=args.max_entries,
                overwrite_existing=args.overwrite,
            )
            payload["files"].append(
                {
                    "file_path": str(file_path),
                    "planned_entries": len(items),
                    "items": [dataclasses.asdict(item) for item in items],
                }
            )

        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for file_payload in payload["files"]:
                print(f"{file_payload['file_path']}: {file_payload['planned_entries']} planned entries")
            if args.out:
                print(f"plan written: {args.out}")

        return 0
    finally:
        engine.close()


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_pipeline_config(Path(args.config))
    files = resolve_bib_paths(args.targets)
    if not files:
        print("No .bib files matched targets", file=sys.stderr)
        return 1

    engine = EnrichmentEngine(cfg)
    try:
        entry_keys = set(args.entry_key) if args.entry_key else None
        summaries = []
        unresolved_total = 0
        error_total = 0

        for file_path in files:
            summary, _decisions = engine.run_file(
                file_path=file_path,
                entry_keys=entry_keys,
                max_entries=args.max_entries,
                write=args.write,
                overwrite_existing=args.overwrite,
            )
            summaries.append(dataclasses.asdict(summary))
            unresolved_total += summary.unresolved_entries
            error_total += summary.error_entries

        if args.json:
            print(json.dumps({"files": summaries}, indent=2, sort_keys=True))
        else:
            for summary in summaries:
                print(
                    f"{summary['file_path']}: planned={summary['planned_entries']} "
                    f"proposed={summary['proposed_entries']} "
                    f"updated={summary['updated_entries']} unresolved={summary['unresolved_entries']} "
                    f"errors={summary['error_entries']} written={summary['written']}"
                )
                print(f"  report: {summary['report_path']}")
                if summary["unresolved_path"]:
                    print(f"  unresolved: {summary['unresolved_path']}")

        if args.fail_on_unresolved and (unresolved_total > 0 or error_total > 0):
            return 2
        return 0
    finally:
        engine.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "run":
        return cmd_run(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
