"""Reliability rules: error handling, retries, and orphaned nodes."""

from __future__ import annotations

from typing import Iterable

from ..model import Workflow
from ..report import RuleHit, Severity
from .base import Rule

# Node types that legitimately sit unconnected on the canvas.
STANDALONE_TYPES = ("stickyNote",)

# Trigger nodes are valid connection sources even with nothing upstream. An
# orphan among these means the trigger fires into nothing, which is still worth
# flagging, so triggers are NOT excluded — only genuinely standalone types are.


class NoErrorTrigger(Rule):
    id = "no-error-trigger"
    default_severity = Severity.WARNING
    summary = "Workflow has no active Error Trigger, so failures pass unnoticed."

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        if len(workflow.nodes) <= 1:
            return
        has_active = any(
            node.type_is("errorTrigger") and not node.disabled
            for node in workflow.nodes
        )
        if not has_active:
            yield RuleHit(
                message="no active Error Trigger — a workflow failure will not alert anyone"
            )


class MissingRetry(Rule):
    id = "missing-retry"
    default_severity = Severity.WARNING
    summary = "An HTTP Request to an external service has no retry configured."

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        for node in workflow.nodes:
            if node.disabled or not node.type_is("httpRequest"):
                continue
            if not node.retry_on_fail:
                yield RuleHit(
                    message="HTTP Request has retryOnFail disabled — a transient error will fail the run",
                    node_name=node.name,
                    line=node.line,
                )


class OrphanNode(Rule):
    id = "orphan-node"
    default_severity = Severity.WARNING
    summary = "A node is not connected to anything on the canvas."

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        if len(workflow.nodes) <= 1:
            return

        connected = self._connected_names(workflow.connections)
        for node in workflow.nodes:
            if node.type_is(*STANDALONE_TYPES):
                continue
            if node.name not in connected:
                yield RuleHit(
                    message="node is not connected to anything and will never run",
                    node_name=node.name,
                    line=node.line,
                )

    @staticmethod
    def _connected_names(connections: dict) -> set[str]:
        names = set(connections.keys())
        for outputs in connections.values():
            if not isinstance(outputs, dict):
                continue
            for branches in outputs.values():
                for branch in branches or []:
                    for link in branch or []:
                        if isinstance(link, dict) and "node" in link:
                            names.add(link["node"])
        return names
