"""Detect hardcoded instance-specific resource IDs (Google files, Gmail labels).

These are not secrets, but publishing them leaks which spreadsheet, drive file,
or label a real deployment used, and they break import for anyone reusing the
workflow. Heuristic by nature, so it defaults to a warning rather than an error.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..model import Workflow
from ..report import RuleHit, Severity
from ..text_utils import line_of_offset, redact
from .base import Rule

# Gmail label IDs are extremely specific — near-zero false positives.
LABEL_ID = re.compile(r'"(Label_[0-9]{10,})"')
# Google Drive / Sheets file IDs: 40+ char base64url tokens appearing as a JSON
# string value. Restricting to quoted values keeps this off code-node bodies.
GOOGLE_ID = re.compile(r'"([A-Za-z0-9_\-]{40,44})"')

PLACEHOLDER_MARKERS = ("REPLACE", "YOUR", "EXAMPLE", "PLACEHOLDER", "XXXX")

_HAS_UPPER = re.compile(r"[A-Z]")
_HAS_LOWER = re.compile(r"[a-z]")
_HAS_DIGIT = re.compile(r"[0-9]")


def _is_placeholder(value: str) -> bool:
    upper = value.upper()
    return any(marker in upper for marker in PLACEHOLDER_MARKERS)


def _looks_like_google_id(value: str) -> bool:
    """Real Google file IDs are high-entropy base64url: mixed case AND digits.

    Same-length lookalikes that aren't IDs — webhook paths like
    `syncbricks-com-tutorial-candidate-shortlist`, hyphenated slugs, all-lower
    hashes — lack this mix, so requiring all three character classes removes
    them without dropping any genuine Google ID.
    """
    return bool(_HAS_UPPER.search(value) and _HAS_LOWER.search(value) and _HAS_DIGIT.search(value))


class HardcodedResourceId(Rule):
    id = "hardcoded-resource-id"
    default_severity = Severity.WARNING
    summary = "A hardcoded Google file ID or Gmail label ID is baked into the workflow."

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        text = workflow.raw_text
        reported: set[tuple[str, int]] = set()

        for pattern, label in ((LABEL_ID, "Gmail label ID"), (GOOGLE_ID, "Google resource ID")):
            for match in pattern.finditer(text):
                value = match.group(1)
                if _is_placeholder(value):
                    continue
                if pattern is GOOGLE_ID and not _looks_like_google_id(value):
                    continue
                line = line_of_offset(text, match.start())
                key = (value, line)
                if key in reported:
                    continue
                reported.add(key)
                yield RuleHit(
                    message=f"possible hardcoded {label} ({redact(value)}); parameterize it",
                    line=line,
                )
