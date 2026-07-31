"""Command-line entry point for n8n-lint."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import ConfigError, apply_cli_disables, load_config
from .engine import lint_paths
from .explain import format_plain
from .report import (
    Severity,
    format_github,
    format_json,
    format_text,
    summarize,
)
from .rules import ALL_RULES

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="n8n-lint",
        description="Lint n8n workflow JSON exports for leaks, reliability gaps, and hygiene issues.",
    )
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories to lint (default: .)")
    parser.add_argument("--config", help=f"path to a config file (default: .n8nlintrc.json if present)")
    parser.add_argument(
        "--format",
        choices=("text", "plain", "github", "json"),
        default="text",
        help="output format (default: text; 'plain' explains each finding in "
             "non-technical language with n8n fix steps)",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="shorthand for --format plain",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on warnings as well as errors",
    )
    parser.add_argument(
        "--disable",
        action="append",
        default=[],
        metavar="RULE",
        help="disable a rule by id (repeatable)",
    )
    parser.add_argument("--no-color", action="store_true", help="disable colored output")
    parser.add_argument("--list-rules", action="store_true", help="print all rules and exit")
    parser.add_argument("--version", action="version", version=f"n8n-lint {__version__}")
    return parser


def list_rules() -> str:
    lines = ["Available rules:", ""]
    width = max(len(rule.id) for rule in ALL_RULES)
    for rule in ALL_RULES:
        lines.append(f"  {rule.id.ljust(width)}  [{rule.default_severity.label()}]  {rule.summary}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_rules:
        print(list_rules())
        return EXIT_OK

    try:
        config = load_config(args.config)
        config = apply_cli_disables(config, args.disable)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    paths = args.paths or ["."]
    findings, files_checked = lint_paths(paths, config)

    # Stable ordering: by file, then line, then rule.
    findings.sort(key=lambda f: (f.path, f.line or 0, f.rule_id))
    summary = summarize(findings, files_checked)

    color = sys.stdout.isatty() and not args.no_color
    output_format = "plain" if args.explain else args.format

    if output_format == "json":
        print(format_json(findings, summary))
    elif output_format == "plain":
        if files_checked:
            print(format_plain(findings, summary, files_checked))
    elif output_format == "github":
        if findings:
            print(format_github(findings))
        _print_summary(summary, files_checked)
    else:
        if findings:
            print(format_text(findings, color=color))
            print()
        _print_summary(summary, files_checked)

    if files_checked == 0:
        print("No workflow JSON files found.", file=sys.stderr)
        return EXIT_USAGE

    if summary["errors"]:
        return EXIT_FINDINGS
    if args.strict and summary["warnings"]:
        return EXIT_FINDINGS
    return EXIT_OK


def _print_summary(summary: dict, files_checked: int) -> None:
    print(
        f"Checked {files_checked} workflow file(s): "
        f"{summary['errors']} error(s), "
        f"{summary['warnings']} warning(s), "
        f"{summary['info']} info."
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
