"""Plain-language report for people who build workflows in the n8n UI.

The default `text` format is a linter report: one line per finding, terse, sorted
for a developer scanning a diff. This format answers a different question — "is
this file safe to send to someone, and what do I click to fix it?" — so it groups
by rule instead of by line, states a verdict first, and gives fixes as steps in
n8n rather than edits to JSON.
"""

from __future__ import annotations

from .report import Finding, Severity
from .rules import RULES_BY_ID

WIDTH = 72

_HEADING = {
    Severity.ERROR: "MUST FIX BEFORE SHARING THIS FILE",
    Severity.WARNING: "WORTH FIXING — these cause problems later",
    Severity.INFO: "MINOR — tidy up when convenient",
}

_MARK = {Severity.ERROR: "[!]", Severity.WARNING: "[~]", Severity.INFO: "[i]"}

# The engine emits this rule id directly; it has no Rule class to read copy from.
_LOAD_ERROR_COPY = (
    "This file is not a workflow n8n can read",
    "The file is either damaged, incomplete, or not an n8n export at all. "
    "Nothing else could be checked, because there was nothing to check.",
    "Go back into n8n, open the workflow, and use the three dots menu (top "
    "right) -> Download. Make sure you save the whole file.",
)


def _wrap(text: str, indent: str = "  ") -> list[str]:
    """Wrap to WIDTH, preserving intentional line breaks (numbered steps)."""
    out: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        line = indent
        for word in para.split():
            if len(line) + len(word) + 1 > WIDTH and line.strip():
                out.append(line.rstrip())
                line = f"{indent}{word} "
            else:
                line = f"{line}{word} " if line.strip() else f"{indent}{word} "
        if line.strip():
            out.append(line.rstrip())
    return out


def _copy_for(rule_id: str) -> tuple[str, str, str]:
    rule = RULES_BY_ID.get(rule_id)
    if rule is None:
        return _LOAD_ERROR_COPY
    title = rule.plain_title or rule.summary
    return title, rule.plain_meaning, rule.plain_fix


def _verdict(errors: int, warnings: int, info: int) -> list[str]:
    if errors:
        thing = "secret" if errors == 1 else "secrets"
        return [
            "  DO NOT SHARE THIS FILE YET.",
            "",
            *_wrap(
                f"Found {errors} serious {thing} or private detail written inside "
                f"the file. Anyone you send it to could use it. Fix the items "
                f"under MUST FIX below, export the workflow again, and re-run "
                f"this check.",
            ),
        ]
    if warnings or info:
        return [
            "  SAFE TO SHARE — no passwords or API keys are inside this file.",
            "",
            *_wrap(
                f"Nothing is leaking. But {warnings + info} thing(s) below will "
                f"make this workflow fragile or confusing later. None of them "
                f"stop it working today.",
            ),
        ]
    return [
        "  ALL CLEAR.",
        "",
        *_wrap(
            "No secrets, no missing safety nets, no loose ends. Safe to share, "
            "and set up to tell you when something goes wrong."
        ),
    ]


def _affected(findings: list[Finding]) -> list[str]:
    """Name the specific nodes/lines a rule fired on, if it named any."""
    names = [f.node_name for f in findings if f.node_name]
    if names:
        unique = list(dict.fromkeys(names))
        label = "Step affected:" if len(unique) == 1 else "Steps affected:"
        return _wrap(f"{label} " + ", ".join(f'"{n}"' for n in unique), indent="  ")
    detail = findings[0].message
    return _wrap(f"Detail: {detail}", indent="  ")


def format_plain(findings: list[Finding], summary: dict, files_checked: int) -> str:
    lines: list[str] = []
    errors, warnings, info = summary["errors"], summary["warnings"], summary["info"]

    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.path, []).append(finding)

    if files_checked and not findings:
        lines.append("=" * WIDTH)
        lines.append(f"  Checked {files_checked} workflow file(s)")
        lines.append("=" * WIDTH)
        lines.append("")
        lines.extend(_verdict(0, 0, 0))
        return "\n".join(lines)

    for path, group in by_file.items():
        name = path.rsplit("/", 1)[-1]
        file_errors = sum(1 for f in group if f.severity is Severity.ERROR)
        file_warnings = sum(1 for f in group if f.severity is Severity.WARNING)
        file_info = sum(1 for f in group if f.severity is Severity.INFO)

        lines.append("=" * WIDTH)
        lines.append(f"  {name}")
        lines.append("=" * WIDTH)
        lines.append("")
        lines.extend(_verdict(file_errors, file_warnings, file_info))
        lines.append("")

        # Group by rule so an explanation is written once, however many nodes hit it.
        for severity in (Severity.ERROR, Severity.WARNING, Severity.INFO):
            at_level = [f for f in group if f.severity is severity]
            if not at_level:
                continue

            lines.append("-" * WIDTH)
            lines.append(f"  {_HEADING[severity]}")
            lines.append("-" * WIDTH)
            lines.append("")

            by_rule: dict[str, list[Finding]] = {}
            for finding in at_level:
                by_rule.setdefault(finding.rule_id, []).append(finding)

            for index, (rule_id, hits) in enumerate(by_rule.items(), start=1):
                title, meaning, fix = _copy_for(rule_id)
                lines.append(f"  {_MARK[severity]} {index}. {title}")
                lines.append("")
                lines.extend(_affected(hits))
                lines.append("")
                lines.append("  What this means")
                lines.extend(_wrap(meaning, indent="    "))
                lines.append("")
                lines.append("  How to fix it")
                lines.extend(_wrap(fix, indent="    "))
                lines.append("")

    lines.append("=" * WIDTH)
    lines.append(
        f"  Checked {files_checked} file(s): "
        f"{errors} must-fix, {warnings} worth-fixing, {info} minor."
    )
    lines.append("=" * WIDTH)
    return "\n".join(lines)
