"""Hygiene rules: leaked pinned data, unauthenticated webhooks, disabled nodes."""

from __future__ import annotations

from typing import Iterable

from ..model import Workflow
from ..report import RuleHit, Severity
from ..text_utils import line_of_node
from .base import Rule


class PinnedData(Rule):
    id = "pinned-data"
    default_severity = Severity.WARNING
    summary = "Pinned test data is embedded in the export — it bloats the file and often leaks real records."

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        if not workflow.pin_data:
            return
        pinned_nodes = ", ".join(sorted(workflow.pin_data.keys())) or "?"
        line = line_of_node(workflow.raw_text, "pinData")  # falls through to None
        yield RuleHit(
            message=(
                f"workflow ships pinned data for: {pinned_nodes} — remove it before "
                f"publishing; it commonly contains real records"
            ),
            line=line,
        )


class UnauthenticatedWebhook(Rule):
    id = "unauthenticated-webhook"
    default_severity = Severity.WARNING
    summary = "A Webhook trigger accepts requests with no authentication."

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        for node in workflow.nodes:
            if node.disabled or not node.type_is("webhook"):
                continue
            auth = node.parameters.get("authentication")
            if auth in (None, "", "none"):
                yield RuleHit(
                    message="Webhook has no authentication — anyone with the URL can trigger it",
                    node_name=node.name,
                    line=node.line,
                )


class DisabledNode(Rule):
    id = "disabled-node"
    default_severity = Severity.INFO
    summary = "A disabled node is left on the canvas."

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        for node in workflow.nodes:
            if node.disabled:
                yield RuleHit(
                    message="node is disabled — remove it or document why it stays",
                    node_name=node.name,
                    line=node.line,
                )
