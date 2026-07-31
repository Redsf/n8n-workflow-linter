"""Rule base class.

A rule inspects one Workflow and yields RuleHits. The engine — not the rule —
decides the severity (default or config override) and attaches the file path, so
severity policy lives in one place and rules stay declarative.
"""

from __future__ import annotations

from typing import Iterable

from ..model import Workflow
from ..report import RuleHit, Severity


class Rule:
    id: str = ""
    default_severity: Severity = Severity.WARNING
    summary: str = ""

    # Plain-language copy for `--format plain`, aimed at someone who builds
    # workflows in the n8n UI and does not read JSON. `plain_fix` is written as
    # clicks in n8n, not as edits to the file.
    plain_title: str = ""
    plain_meaning: str = ""
    plain_fix: str = ""

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:  # pragma: no cover
        raise NotImplementedError
