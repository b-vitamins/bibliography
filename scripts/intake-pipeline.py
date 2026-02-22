#!/usr/bin/env python3
"""Run modular, source-grounded bibliography intake workflows."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from intake.config import DEFAULT_CONFIG_PATH, load_intake_config, parse_target_tokens
from intake.engine import IntakeEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bibliography intake pipeline")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Intake pipeline config TOML path",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="Discover source records for venue/year targets")
    discover.add_argument("targets", nargs="+", help="Target tokens in venue:year format")
    discover.add_argument("--json", action="store_true", help="Emit JSON")
    discover.add_argument("--out", help="Optional output JSON path")

    plan = sub.add_parser("plan", help="Plan intake reconciliation without writing")
    plan.add_argument("targets", nargs="+", help="Target tokens in venue:year format")
    plan.add_argument("--max-records", type=int, default=0, help="Cap source records per target")
    plan.add_argument(
        "--fail-on-gap",
        action="store_true",
        help="Return non-zero when missing/extra gaps are detected in plan mode",
    )
    plan.add_argument("--json", action="store_true", help="Emit JSON")
    plan.add_argument("--out", help="Optional output JSON path")

    run = sub.add_parser("run", help="Run intake reconciliation, optionally writing files")
    run.add_argument("targets", nargs="+", help="Target tokens in venue:year format")
    run.add_argument("--max-records", type=int, default=0, help="Cap source records per target")
    run.add_argument("--write", action="store_true", help="Write merged target .bib files")
    run.add_argument(
        "--fail-on-gap",
        action="store_true",
        help="Return non-zero when gaps/issues remain after run",
    )
    run.add_argument("--json", action="store_true", help="Emit JSON")
    run.add_argument("--out", help="Optional output JSON path")

    return parser


def _emit_payload(payload: dict, *, as_json: bool, out_path: str | None) -> None:
    if out_path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_discover(args: argparse.Namespace) -> int:
    cfg = load_intake_config(Path(args.config))
    targets = parse_target_tokens(args.targets)
    engine = IntakeEngine(cfg)
    try:
        payload = {"config": str(cfg.config_path), "targets": []}
        for venue, year in targets:
            snapshot, attempts = engine.discover(venue, year, purpose="discover")
            if snapshot is None:
                payload["targets"].append(
                    {
                        "target": f"{venue}:{year}",
                        "found": False,
                        "attempts": attempts,
                    }
                )
                continue
            payload["targets"].append(
                {
                    "target": snapshot.target.target_id,
                    "found": True,
                    "adapter": snapshot.adapter,
                    "records": len(snapshot.records),
                    "expected_count": snapshot.expected_count,
                    "attempts": attempts,
                    "metadata": snapshot.metadata,
                }
            )

        _emit_payload(payload, as_json=args.json, out_path=args.out)
        if not args.json:
            for row in payload["targets"]:
                if not row["found"]:
                    print(f"{row['target']}: no catalog records")
                else:
                    print(
                        f"{row['target']}: adapter={row['adapter']} records={row['records']} "
                        f"expected={row['expected_count']}"
                    )
            if args.out:
                print(f"discover report written: {args.out}")

        missing = [r for r in payload["targets"] if not r["found"]]
        return 2 if missing else 0
    finally:
        engine.close()


def _run_common(args: argparse.Namespace, *, write: bool) -> int:
    cfg = load_intake_config(Path(args.config))
    targets = parse_target_tokens(args.targets)
    engine = IntakeEngine(cfg)
    try:
        envelope = engine.run_many(
            targets=targets,
            write=write,
            fail_on_gap=args.fail_on_gap if hasattr(args, "fail_on_gap") else False,
            max_records=args.max_records,
            command=args.command,
        )
        payload = envelope.to_json()
        _emit_payload(payload, as_json=args.json, out_path=args.out)
        if not args.json:
            for summary in envelope.summaries:
                print(
                    f"{summary.target}: adapter={summary.adapter} source={summary.source_count} "
                    f"existing={summary.existing_count} matched={summary.matched_count} "
                    f"missing={summary.missing_count} extra={summary.extra_count} written={summary.written}"
                )
                print(f"  report: {summary.report_path}")
                if summary.snapshot_path:
                    print(f"  snapshot: {summary.snapshot_path}")
                if summary.unresolved_path:
                    print(f"  unresolved: {summary.unresolved_path}")
                if summary.write_error:
                    print(f"  write_error: {summary.write_error}")
            if args.out:
                print(f"run report written: {args.out}")

        hard_fail = False
        for summary in envelope.summaries:
            if summary.duplicate_source_count > 0 or summary.invalid_record_count > 0:
                hard_fail = True
            if getattr(args, "fail_on_gap", False):
                if write:
                    if not summary.written and summary.write_error:
                        hard_fail = True
                elif summary.missing_count > 0 or summary.extra_count > 0:
                    hard_fail = True
            if summary.write_error:
                hard_fail = True
        for issues in envelope.issues.values():
            if any(issue.severity == "error" for issue in issues):
                hard_fail = True
        return 2 if hard_fail else 0
    finally:
        engine.close()


def cmd_plan(args: argparse.Namespace) -> int:
    return _run_common(args, write=False)


def cmd_run(args: argparse.Namespace) -> int:
    return _run_common(args, write=args.write)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "discover":
            return cmd_discover(args)
        if args.command == "plan":
            return cmd_plan(args)
        if args.command == "run":
            return cmd_run(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
