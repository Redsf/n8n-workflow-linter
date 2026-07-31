"""Detect instance-specific n8n credential IDs left in a published export."""

from __future__ import annotations

from typing import Iterable

from ..model import Workflow
from ..report import RuleHit, Severity
from ..text_utils import redact
from .base import Rule

# IDs that are safe to publish. Anything else is an ID from a real n8n instance:
# it leaks which credential a private instance used and breaks import for anyone
# else, because credential IDs do not transfer between accounts.
PLACEHOLDER_IDS = frozenset({
    "",
    "REPLACE_WITH_CREDENTIAL_ID",
    "REPLACE_WITH_CREDENTIAL",
    "REPLACE_ME",
    "PLACEHOLDER",
    "YOUR_CREDENTIAL_ID",
})


class RealCredentialId(Rule):
    id = "real-credential-id"
    default_severity = Severity.ERROR
    summary = "A credential references a real instance ID instead of a placeholder."
    plain_title = "This file points at a login that only exists in your own n8n account"
    plain_meaning = (
        "When you connect an account in n8n (Gmail, OpenAI, Sheets), n8n stores it "
        "and gives it a private ID number. That ID number is now written inside this "
        "file. It is not your password, but it does two annoying things: it tells "
        "anyone who reads the file which of your accounts you used, and it makes the "
        "file fail to import for anybody else, because their n8n has different ID "
        "numbers."
    )
    plain_fix = (
        "If this file is just for you, you can ignore this.\n"
        "If you are about to share it, publish it, or put it on GitHub: open the "
        "file in a text editor, find the ID shown above, and replace it with the "
        "words REPLACE_WITH_CREDENTIAL_ID. The person importing it then picks their "
        "own account instead."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        for node in workflow.nodes:
            for cred_type, cred in node.credentials.items():
                if not isinstance(cred, dict):
                    continue
                cred_id = cred.get("id")
                if cred_id is None or cred_id in PLACEHOLDER_IDS:
                    continue
                yield RuleHit(
                    message=(
                        f"{cred_type} credential uses a real instance ID "
                        f"({redact(str(cred_id))}); replace with REPLACE_WITH_CREDENTIAL_ID"
                    ),
                    node_name=node.name,
                    line=node.line,
                )
