"""The lint engine: load files, run rules, collect findings."""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .loader import collect_files, load
from .model import LoadError, Workflow
from .report import Finding, Severity
from .rules import ALL_RULES

# A file that cannot be parsed is always an error — a broken export in a repo of
# workflows is exactly what CI should catch. Not configurable.
LOAD_ERROR_RULE = "invalid-workflow"


def lint_workflow(workflow: Workflow, config: Config) -> list[Finding]:
    findings: list[Finding] = []
    for rule in ALL_RULES:
        severity = config.severity_for(rule.id, rule.default_severity)
        if severity is None:  # rule disabled
            continue
        for hit in rule.check(workflow):
            findings.append(
                Finding(
                    rule_id=rule.id,
                    severity=severity,
                    message=hit.message,
                    path=workflow.path,
                    line=hit.line,
                    node_name=hit.node_name,
                    detail=hit.detail,
                )
            )
    return findings


def lint_paths(paths: list[str], config: Config) -> tuple[list[Finding], int]:
    """Lint every workflow found under `paths`. Returns (findings, files_checked)."""
    files = collect_files(paths)
    findings: list[Finding] = []

    for path in files:
        loaded = load(path)
        if isinstance(loaded, LoadError):
            findings.append(
                Finding(
                    rule_id=LOAD_ERROR_RULE,
                    severity=Severity.ERROR,
                    message=loaded.message,
                    path=loaded.path,
                )
            )
            continue
        findings.extend(lint_workflow(loaded, config))

    return findings, len(files)


def worst_severity(findings: list[Finding]) -> Severity | None:
    return max((f.severity for f in findings), default=None)
