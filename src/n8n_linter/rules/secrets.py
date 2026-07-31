"""Detect live API keys and other hardcoded secrets in a workflow export."""

from __future__ import annotations

import re
from typing import Iterable

from ..model import Workflow
from ..report import RuleHit, Severity
from ..text_utils import line_of_offset, redact
from .base import Rule

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI API key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("AWS access key ID", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("Stripe secret key", re.compile(r"sk_live_[0-9A-Za-z]{20,}")),
    ("Twilio account SID", re.compile(r"AC[0-9a-fA-F]{32}")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+")),
)

# A match containing any of these is a documented placeholder, not a live secret.
PLACEHOLDER_MARKERS = ("REPLACE", "YOUR", "EXAMPLE", "PLACEHOLDER", "XXXX", "<", "...", "DUMMY", "TEST_")


def _is_placeholder(match: str) -> bool:
    upper = match.upper()
    return any(marker in upper for marker in PLACEHOLDER_MARKERS)


class HardcodedSecret(Rule):
    id = "hardcoded-secret"
    default_severity = Severity.ERROR
    summary = "A live API key, token, or private key is embedded in the workflow."
    plain_title = "A password or API key is written inside this file"
    plain_meaning = (
        "An API key is like a password for a paid service — OpenAI, Google, Slack. "
        "This one is typed directly into the workflow instead of being stored in "
        "n8n's Credentials vault. Anyone who opens this file can copy that key and "
        "spend your money or read your data with it. This is the serious one."
    )
    plain_fix = (
        "Two steps, and do them in this order:\n"
        "1. Go to the website the key belongs to (OpenAI, Google, etc.) and delete "
        "or regenerate that key. Assume it is already burned — it has been sitting "
        "in a file in plain text.\n"
        "2. In n8n, open the node that needed it. Instead of typing the key into a "
        "text box, click the Credential dropdown and create a proper credential. "
        "n8n keeps those encrypted and leaves them out of exports."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        text = workflow.raw_text
        reported: set[tuple[str, int]] = set()

        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group()
                if _is_placeholder(value):
                    continue
                line = line_of_offset(text, match.start())
                key = (value, line)
                if key in reported:
                    continue
                reported.add(key)
                yield RuleHit(
                    message=f"possible {label} embedded in file ({redact(value)})",
                    line=line,
                )
