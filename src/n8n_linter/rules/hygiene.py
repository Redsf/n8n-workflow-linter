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
    plain_title = "Saved test data is stored inside this file"
    plain_meaning = (
        "While testing, n8n lets you 'pin' the result of a step so it reuses that "
        "same data instead of fetching fresh every time. Handy while building — but "
        "pinned data gets saved into the exported file. If what you pinned was real "
        "customer records, real emails, or real order data, that data is now sitting "
        "in this file, and it travels wherever the file goes."
    )
    plain_fix = (
        "1. Open the workflow in n8n and find the node named above.\n"
        "2. Look for the pin icon on that node — it will be highlighted.\n"
        "3. Click it to unpin, then save the workflow and export again.\n"
        "Before you do: click the node and actually look at the pinned data. If it is "
        "just made-up test values, this is harmless. If it is real people's "
        "information, unpin it before this file goes anywhere."
    )

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
    plain_title = "Anyone who has the link can trigger this workflow"
    plain_meaning = (
        "A webhook is a public web address that starts your workflow when something "
        "visits it. This one has no lock on it. Anybody who learns or guesses the "
        "URL can fire your workflow as many times as they like — sending emails, "
        "burning OpenAI credit, writing rows into your sheet. Webhook URLs leak more "
        "easily than people expect: browser history, screenshots, shared docs."
    )
    plain_fix = (
        "1. Double-click the Webhook node in n8n.\n"
        "2. Find the 'Authentication' dropdown — it is currently 'None'.\n"
        "3. Choose 'Header Auth' and create a credential with any long random value "
        "as the key.\n"
        "4. Whatever calls this webhook must now send that header, so update it too.\n"
        "If the webhook is genuinely meant to be public, this warning is fine to "
        "ignore — just be sure that is a decision, not an accident."
    )

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
    plain_title = "A switched-off step is still sitting on the canvas"
    plain_meaning = (
        "This step is turned off, so it does not run. Nothing is broken. It matters "
        "only because in six months nobody — including you — will remember whether "
        "it is switched off on purpose or by accident. That is how a workflow ends "
        "up doing less than everyone thinks it does."
    )
    plain_fix = (
        "Either delete the node, or add a Sticky Note next to it in n8n saying why it "
        "stays off. Both are fine. Doing neither is the problem."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        for node in workflow.nodes:
            if node.disabled:
                yield RuleHit(
                    message="node is disabled — remove it or document why it stays",
                    node_name=node.name,
                    line=node.line,
                )
