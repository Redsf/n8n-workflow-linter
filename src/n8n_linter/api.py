"""In-process API: lint a workflow held in memory and get structured results.

The CLI reads files off disk and prints text. That is the wrong shape for a
caller that already has the JSON as a string and wants to render its own UI —
the browser build being the obvious one, since a page has no filesystem and no
stdout.

`analyze()` takes the raw text and returns plain dicts and lists: no dataclasses,
no enums, nothing that needs a converter on the far side. `json.dumps` on the
result is valid, which is what makes it usable from JavaScript.

It carries the plain-language copy with each finding rather than expecting the
caller to look it up, so there is one source of truth for what a rule means and
every front end says the same thing.
"""

from __future__ import annotations

import json

from .config import Config
from .engine import lint_workflow
from .model import LoadError, Node, Workflow
from .report import Finding, Severity
from .rules import ALL_RULES, RULES_BY_ID
from .text_utils import line_of_node

VERDICT_LEAK = "leak"
VERDICT_SAFE = "safe"
VERDICT_CLEAN = "clean"
VERDICT_UNREADABLE = "unreadable"


def parse(text: str, filename: str = "workflow.json") -> Workflow | LoadError:
    """Same checks as `loader.load`, against a string instead of a path.

    Kept deliberately in step with the loader: a file that the CLI rejects must
    be rejected here for the same reason and with the same wording, or the two
    front ends disagree about what a valid workflow is.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return LoadError(filename, f"invalid JSON — {exc}")

    if not isinstance(data, dict) or "nodes" not in data:
        return LoadError(filename, "not an n8n workflow export (no top-level 'nodes')")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list):
        return LoadError(filename, "'nodes' is not a list")

    nodes = tuple(
        Node(
            name=str(raw.get("name", "?")),
            type=str(raw.get("type", "")),
            raw=raw,
            line=line_of_node(text, str(raw.get("name", ""))),
        )
        for raw in raw_nodes
        if isinstance(raw, dict)
    )

    return Workflow(
        path=filename,
        name=str(data.get("name") or filename),
        nodes=nodes,
        connections=data.get("connections") or {},
        pin_data=data.get("pinData") or {},
        raw=data,
        raw_text=text,
    )


def _finding_dict(finding: Finding) -> dict:
    rule = RULES_BY_ID.get(finding.rule_id)
    return {
        "rule": finding.rule_id,
        "severity": finding.severity.label(),
        "message": finding.message,
        "node": finding.node_name,
        "line": finding.line,
        "detail": finding.detail,
        "title": (rule.plain_title or rule.summary) if rule else finding.message,
        "meaning": rule.plain_meaning if rule else "",
        "fix": rule.plain_fix if rule else "",
        "summary": rule.summary if rule else "",
    }


def _group_by_rule(findings: list[Finding]) -> list[dict]:
    """One entry per rule, carrying every node that tripped it.

    The UI explains a rule once however many nodes hit it — twelve copies of the
    same paragraph is how a report stops being read.
    """
    order: list[str] = []
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        if finding.rule_id not in grouped:
            grouped[finding.rule_id] = []
            order.append(finding.rule_id)
        grouped[finding.rule_id].append(finding)

    out = []
    for rule_id in order:
        hits = grouped[rule_id]
        base = _finding_dict(hits[0])
        base["count"] = len(hits)
        base["nodes"] = list(dict.fromkeys(h.node_name for h in hits if h.node_name))
        base["lines"] = [h.line for h in hits if h.line is not None]
        # Detail is computed per finding (cost tables); keep each distinct one.
        base["details"] = list(dict.fromkeys(h.detail for h in hits if h.detail))
        out.append(base)
    return out


def analyze(text: str, filename: str = "workflow.json", config: Config | None = None) -> dict:
    """Lint one workflow given as text. Returns JSON-serialisable results."""
    parsed = parse(text, filename)

    if isinstance(parsed, LoadError):
        return {
            "ok": False,
            "filename": filename,
            "workflow_name": None,
            "verdict": VERDICT_UNREADABLE,
            "summary": {"errors": 1, "warnings": 0, "info": 0, "nodes": 0},
            "error": parsed.message,
            "groups": [],
            "findings": [],
        }

    findings = lint_workflow(parsed, config or Config())
    counts = {
        "errors": sum(1 for f in findings if f.severity is Severity.ERROR),
        "warnings": sum(1 for f in findings if f.severity is Severity.WARNING),
        "info": sum(1 for f in findings if f.severity is Severity.INFO),
        "nodes": len(parsed.nodes),
    }

    if counts["errors"]:
        verdict = VERDICT_LEAK
    elif counts["warnings"] or counts["info"]:
        verdict = VERDICT_SAFE
    else:
        verdict = VERDICT_CLEAN

    return {
        "ok": True,
        "filename": filename,
        "workflow_name": parsed.name,
        "verdict": verdict,
        "summary": counts,
        "error": None,
        "groups": _group_by_rule(findings),
        "findings": [_finding_dict(f) for f in findings],
    }


def analyze_json(text: str, filename: str = "workflow.json") -> str:
    """`analyze` as a JSON string — the form a JS caller can hand to JSON.parse."""
    return json.dumps(analyze(text, filename))


def rule_catalogue() -> list[dict]:
    """Every rule and its default severity, for an about/help panel."""
    return [
        {
            "id": rule.id,
            "severity": rule.default_severity.label(),
            "summary": rule.summary,
            "title": rule.plain_title or rule.summary,
        }
        for rule in ALL_RULES
    ]
