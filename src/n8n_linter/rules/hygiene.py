"""Hygiene rules: leaked pinned data, unauthenticated webhooks, disabled nodes."""

from __future__ import annotations

import re
from typing import Iterable

from ..model import Workflow
from ..report import RuleHit, Severity
from ..text_utils import line_of_node
from .base import Rule

# The name n8n gives a node when you drop it on the canvas, with the numeric
# suffix it adds for duplicates. Anchored, so a node deliberately called
# "Code that cleans the CSV" is not caught.
DEFAULT_NAME = re.compile(
    r"""(?ix)^\s*(
        HTTP\ Request | Webhook | Code | Function(\ Item)? | Set | Edit\ Fields |
        If | Switch | Merge | Wait | NoOp | No\ Operation,\ do\ nothing |
        Filter | Sort | Limit | Aggregate | Summarize | Item\ Lists |
        Split\ In\ Batches | Loop\ Over\ Items | Split\ Out | Execute\ Workflow |
        Date\ &\ Time | Crypto | HTML | XML | Compare\ Datasets | Respond\ to\ Webhook |
        Basic\ LLM\ Chain | AI\ Agent | Edit\ Image | Convert\ to\ File | Extract\ from\ File
    )\s*\d*\s*$"""
)

# One leftover default name is noise; several means nobody named anything.
DEFAULT_NAME_THRESHOLD = 3


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


class DefaultNodeNames(Rule):
    id = "default-node-names"
    default_severity = Severity.INFO
    summary = "Several nodes still carry n8n's default names, making the canvas unreadable."

    plain_title = "Several steps are still called things like 'HTTP Request1'"
    plain_meaning = (
        "n8n names a step after the node type until you rename it. A canvas full "
        "of 'Code1', 'Edit Fields2', 'HTTP Request3' is readable while you are "
        "building it and unreadable three months later — including to you. It "
        "also makes every error message useless, because 'HTTP Request2 failed' "
        "does not tell you what was being fetched."
    )
    plain_fix = (
        "In n8n, double-click each step's name at the top of its panel and "
        "describe what it does, not what it is: 'Fetch HN front page' rather than "
        "'HTTP Request1', 'Drop leads without an email' rather than 'Filter'.\n"
        "Takes a couple of minutes and pays for itself the first time something "
        "breaks at 3am."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        defaults = [
            node for node in workflow.nodes
            if not node.type_is("stickyNote") and DEFAULT_NAME.match(node.name)
        ]
        if len(defaults) < DEFAULT_NAME_THRESHOLD:
            return
        for node in defaults:
            yield RuleHit(
                message=(
                    f"node still has n8n's default name "
                    f"({len(defaults)} nodes in this workflow do) — rename it to "
                    f"describe what it does"
                ),
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
