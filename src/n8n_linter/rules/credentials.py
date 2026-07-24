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
