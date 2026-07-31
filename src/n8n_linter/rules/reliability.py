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
    plain_title = "Nobody gets told when this workflow breaks"
    plain_meaning = (
        "Right now, if this workflow fails at 3am, it fails quietly. No email, no "
        "message. You find out days later when you notice nothing has happened — or "
        "worse, a client notices first. n8n has a node whose whole job is to catch "
        "failures and tell someone, and this workflow does not have an active one."
    )
    plain_fix = (
        "Build a tiny second workflow that does the shouting:\n"
        "1. New workflow in n8n → add node → search 'Error Trigger' → add it.\n"
        "2. Connect it to a Telegram, Slack, or Gmail node that sends you a message.\n"
        "3. Save it, and give it a name like 'Error Alerts'.\n"
        "4. Go back to THIS workflow → three dots menu (top right) → Settings → "
        "'Error Workflow' → pick 'Error Alerts'.\n"
        "Now any failure pings you. Do this once and reuse it for every workflow."
    )

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
    plain_title = "One bad internet moment kills the whole run"
    plain_meaning = (
        "This step fetches something from another website or service. Those hiccup "
        "constantly — a half-second timeout, a momentary 'too many requests'. With "
        "retry switched off, one blip kills the entire workflow run, even though "
        "trying again two seconds later would have worked fine. This is the single "
        "most common reason a working automation randomly 'stops working'."
    )
    plain_fix = (
        "In n8n, for each node named above:\n"
        "1. Double-click the node to open it.\n"
        "2. Click the 'Settings' tab at the top of the panel.\n"
        "3. Turn ON 'Retry On Fail'.\n"
        "4. Leave the defaults (3 tries, 1 second apart) unless you have a reason.\n"
        "Takes about ten seconds per node and prevents most mystery failures."
    )

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
    plain_title = "A step is floating loose and will never run"
    plain_meaning = (
        "This node sits on the canvas with no line connecting it to anything. n8n "
        "only runs steps that are wired into the chain, so this one does nothing. "
        "Usually it means either you meant to connect it and forgot — in which case "
        "part of your automation silently is not happening — or it is leftover from "
        "an older version."
    )
    plain_fix = (
        "Open the workflow in n8n and look at the node named above.\n"
        "If you meant it to run: drag a line from the previous step's dot into it.\n"
        "If it is leftover: click it and press Delete. Leaving it there will confuse "
        "you (or a client) in three months."
    )

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
