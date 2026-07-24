"""Findings, severities, and output formatters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum


class Severity(IntEnum):
    """Ordered so a run's worst severity is just `max(...)`."""

    INFO = 10
    WARNING = 20
    ERROR = 30

    @classmethod
    def parse(cls, value: str) -> "Severity":
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            raise ValueError(f"unknown severity: {value!r}") from exc

    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    message: str
    path: str
    line: int | None = None
    node_name: str | None = None


@dataclass(frozen=True)
class RuleHit:
    """What a rule yields. The engine stamps on severity, path, and rule id."""

    message: str
    node_name: str | None = None
    line: int | None = None


# ANSI colors, applied only when writing to a TTY.
_COLORS = {
    Severity.ERROR: "\033[31m",   # red
    Severity.WARNING: "\033[33m",  # yellow
    Severity.INFO: "\033[36m",     # cyan
}
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"


def _location(finding: Finding) -> str:
    if finding.line is not None:
        return f"{finding.path}:{finding.line}"
    return finding.path


def format_text(findings: list[Finding], *, color: bool) -> str:
    """Human-readable output, grouped by file in source order."""

    def paint(text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if color else text

    lines: list[str] = []
    by_path: dict[str, list[Finding]] = {}
    for finding in findings:
        by_path.setdefault(finding.path, []).append(finding)

    for path, group in by_path.items():
        lines.append(paint(path, _BOLD))
        for finding in sorted(group, key=lambda f: (f.line or 0, f.rule_id)):
            loc = f":{finding.line}" if finding.line is not None else ""
            sev = paint(finding.severity.label().ljust(7), _COLORS[finding.severity])
            node = paint(f" ({finding.node_name})", _DIM) if finding.node_name else ""
            lines.append(f"  {loc:<5} {sev} {finding.message}{node} {paint(finding.rule_id, _DIM)}")
        lines.append("")

    return "\n".join(lines).rstrip("\n")


def format_github(findings: list[Finding]) -> str:
    """GitHub Actions workflow commands — render as inline PR annotations.

    https://docs.github.com/actions/using-workflows/workflow-commands-for-github-actions
    """
    level = {Severity.ERROR: "error", Severity.WARNING: "warning", Severity.INFO: "notice"}
    lines = []
    for finding in findings:
        loc = f"file={finding.path}"
        if finding.line is not None:
            loc += f",line={finding.line}"
        title = f"{finding.rule_id}"
        message = finding.message
        if finding.node_name:
            message += f" (node: {finding.node_name})"
        lines.append(f"::{level[finding.severity]} {loc},title={title}::{message}")
    return "\n".join(lines)


def format_json(findings: list[Finding], summary: dict) -> str:
    payload = {
        "summary": summary,
        "findings": [
            {
                "rule": f.rule_id,
                "severity": f.severity.label(),
                "message": f.message,
                "path": f.path,
                "line": f.line,
                "node": f.node_name,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2)


def summarize(findings: list[Finding], files_checked: int) -> dict:
    counts = {sev.label(): 0 for sev in Severity}
    for finding in findings:
        counts[finding.severity.label()] += 1
    return {
        "files_checked": files_checked,
        "errors": counts["error"],
        "warnings": counts["warning"],
        "info": counts["info"],
    }
