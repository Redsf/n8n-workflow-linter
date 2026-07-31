"""Cost rules: what this workflow will spend, and what it could spend instead.

Security and reliability rules ask whether a workflow is safe and whether it
survives contact with production. These ask a third question nobody's linter
asks: what does running it cost, and is that the cheapest way to get this done?

Two deliberate limits on what these rules will claim.

They never assert a cheaper model is *good enough*. Nothing here has seen the
prompt or the data, and swapping a frontier model for a small one is a change of
product, not a configuration tweak. What the estimate can honestly say is what
each option costs and what the difference would be, and then point at an eval
harness for the part it cannot answer.

They always print their assumptions. An estimate that hides the token count it
assumed is the same trick as an ROI projection that hides its baseline: right up
until someone checks it.
"""

from __future__ import annotations

from typing import Iterable

from .. import pricing
from ..model import Node, Workflow
from ..report import RuleHit, Severity
from .base import Rule

# Node types that bill per token.
LLM_NODE_SUFFIXES = (
    "lmChatOpenAi", "lmChatAnthropic", "lmChatGoogleGemini", "lmChatGoogleVertex",
    "lmChatGroq", "lmChatMistralCloud", "lmChatDeepSeek", "lmChatOpenRouter",
    "lmChatAzureOpenAi", "lmChatXAiGrok", "lmChatCohere", "lmOpenAi", "openAi",
)

# Where different vendor nodes keep the model name.
MODEL_PARAM_KEYS = ("model", "modelName", "modelId", "deploymentName")
MAX_TOKEN_KEYS = ("maxTokens", "maxTokensToSample", "maxOutputTokens", "maxCompletionTokens")

RUNS_PER_MONTH = {
    "seconds": 30 * 24 * 60 * 60,
    "minutes": 30 * 24 * 60,
    "hours": 30 * 24,
    "days": 30,
    "weeks": 30 / 7,
    "months": 1,
}

# Assumptions, stated in every report that uses them. A workflow file cannot
# reveal how long its prompts are, so the estimate is a range and says so.
ASSUMED_INPUT_TOKENS = 1_000
ASSUMED_OUTPUT_LOW = 300
ASSUMED_OUTPUT_HIGH = 1_500

HOURLY_RUNS_PER_MONTH = RUNS_PER_MONTH["hours"]  # more often than this is "high frequency"
FREQUENT_POLL_MINUTES = 5


def _param(node: Node, keys: tuple[str, ...]) -> object | None:
    """Read the first matching key from parameters or parameters.options.

    n8n stores a resource-locator value as {"value": "gpt-4o", "mode": "list"},
    so unwrap that shape too.
    """
    sources = [node.parameters]
    options = node.parameters.get("options")
    if isinstance(options, dict):
        sources.append(options)

    for source in sources:
        for key in keys:
            if key not in source:
                continue
            value = source[key]
            if isinstance(value, dict) and "value" in value:
                value = value["value"]
            if value not in (None, ""):
                return value
    return None


def _llm_nodes(workflow: Workflow) -> list[Node]:
    return [
        node for node in workflow.nodes
        if not node.disabled and node.type_is(*LLM_NODE_SUFFIXES)
    ]


def runs_per_month(workflow: Workflow) -> tuple[float | None, str]:
    """Estimated runs per month, and a plain description of where it came from.

    Returns (None, "") when the trigger's rate cannot be read — a webhook fires
    as often as something calls it, and guessing would be dishonest.
    """
    for node in workflow.nodes:
        if node.disabled or not node.type_is("scheduleTrigger", "interval", "cron"):
            continue
        rule = node.parameters.get("rule")
        intervals = rule.get("interval") if isinstance(rule, dict) else None
        if not isinstance(intervals, list):
            continue

        for entry in intervals:
            if not isinstance(entry, dict):
                continue
            field = entry.get("field")
            if field not in RUNS_PER_MONTH:
                continue  # cronExpression and friends: not worth guessing
            every = entry.get(f"{field[:-1]}sInterval") or entry.get(f"{field}Interval") or 1
            try:
                every = float(every) or 1.0
            except (TypeError, ValueError):
                every = 1.0
            runs = RUNS_PER_MONTH[field] / every
            unit = field[:-1] if every == 1 else f"{every:g} {field}"
            return runs, f"Schedule Trigger fires every {unit}"
    return None, ""


def _cost_range(model: pricing.Model, runs: float, max_tokens: float | None) -> tuple[float, float]:
    high_out = float(max_tokens) if max_tokens else ASSUMED_OUTPUT_HIGH
    low_out = min(ASSUMED_OUTPUT_LOW, high_out)
    return (
        runs * model.cost_for(ASSUMED_INPUT_TOKENS, low_out),
        runs * model.cost_for(ASSUMED_INPUT_TOKENS, high_out),
    )


def _money(value: float) -> str:
    if value >= 100:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:,.2f}"
    # Sub-dollar token prices need a third place for $0.435, but $0.50 should
    # not render as $0.500 — or, worse, as $0.5.
    return f"${value:.2f}" if round(value, 3) == round(value, 2) else f"${value:.3f}"


def _assumption_block(runs: float, source: str, max_tokens: float | None) -> list[str]:
    out_note = (
        f"{max_tokens:,.0f} tokens out (your maxTokens setting)" if max_tokens
        else f"{ASSUMED_OUTPUT_LOW:,}-{ASSUMED_OUTPUT_HIGH:,} tokens out (assumed - not measured)"
    )
    return [
        "Based on:",
        f"  {source} -> {runs:,.0f} runs/month",
        f"  {ASSUMED_INPUT_TOKENS:,} tokens in (assumed - not measured), {out_note}",
        "  One model call per run. An agent that calls tools loops more than once,",
        "  so treat this as a floor, not a ceiling.",
    ]


def _alternatives_block(model: pricing.Model, runs: float, max_tokens: float | None) -> list[str]:
    alternatives = pricing.cheaper_alternatives(model)
    if not alternatives:
        return []

    _, current_high = _cost_range(model, runs, max_tokens)
    lines = ["", "Cheaper models to evaluate against it:"]
    for other in alternatives:
        _, other_high = _cost_range(other, runs, max_tokens)
        saving = current_high - other_high
        flag = "" if other.source == pricing.PRIMARY else "  [price from a third-party tracker]"
        lines.append(
            f"  {other.display:<24} {_money(other.input_price)}/{_money(other.output_price)} per 1M"
            f"  ->  ~{_money(other_high)}/mo, saves ~{_money(saving)}{flag}"
        )
        if other.note:
            lines.append(f"      {other.note}")

    lines += [
        "",
        "Whether any of these is good enough for THIS task is not something a",
        "linter can know - it depends on your prompt and your data. Do not swap",
        "on price alone. Build a small suite of real cases, run it against each",
        "model, compare the scores, then decide.",
        "  https://github.com/Redsf/agent-evals",
        "",
        pricing.verification_note(),
    ]
    return lines


class LlmCostUnbounded(Rule):
    id = "llm-cost-unbounded"
    # Info, not warning, and the calibration corpus is why: this fires on 85% of
    # 59 real workflows, because n8n does not set a token cap by default. A rule
    # that flags the default state of almost every workflow is describing a
    # preference, not a defect, whatever its author thinks of the preference.
    # Turn it up in .n8nlintrc.json if a runaway bill is a live concern for you.
    default_severity = Severity.INFO
    summary = "An LLM node has no maximum output length, so the cost of one call has no ceiling."

    plain_title = "There is no limit on how much one AI reply can cost"
    plain_meaning = (
        "This step has no cap on how long the model's answer may be. Almost "
        "always the answer is short and the bill is small. The problem is the "
        "day it is not: a confused prompt, a document that arrives ten times "
        "longer than usual, a model that starts repeating itself. Output tokens "
        "are the expensive half of the bill, and without a cap a single run can "
        "cost hundreds of times what a normal one does, with nothing to stop it."
    )
    plain_fix = (
        "1. Double-click the model step in n8n (the one connected underneath your "
        "AI Agent or chain).\n"
        "2. Under 'Options', click 'Add Option' and choose 'Maximum Number of "
        "Tokens'.\n"
        "3. Set it a bit above the longest answer you actually want. For a short "
        "classification, 256 is plenty. For a written summary, 1000-2000.\n"
        "This is a cost ceiling, not a quality setting - a sensible cap changes "
        "nothing about normal runs and prevents the expensive ones."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        runs, source = runs_per_month(workflow)

        for node in _llm_nodes(workflow):
            if _param(node, MAX_TOKEN_KEYS):
                continue

            model_id = _param(node, MODEL_PARAM_KEYS)
            model = pricing.lookup(str(model_id)) if model_id else None

            detail = ""
            if model and runs:
                low, high = _cost_range(model, runs, None)
                detail = "\n".join(
                    [
                        f"{model.display} at {_money(model.input_price)}/{_money(model.output_price)} "
                        f"per 1M tokens (in/out)",
                        f"Estimated: {_money(low)} - {_money(high)} per month",
                        "",
                        *_assumption_block(runs, source, None),
                        "",
                        "That upper figure assumes answers stay around "
                        f"{ASSUMED_OUTPUT_HIGH:,} tokens. With no cap set, nothing "
                        "enforces that.",
                        "",
                        pricing.verification_note(),
                    ]
                )

            named = f" ({model.display})" if model else ""
            yield RuleHit(
                message=(
                    f"no maximum output length set{named} — one unusually long "
                    f"reply has no cost ceiling"
                ),
                node_name=node.name,
                line=node.line,
                detail=detail,
            )


class ExpensiveModelHighFrequency(Rule):
    id = "expensive-model-high-frequency"
    default_severity = Severity.WARNING
    summary = "A frontier-tier model runs on a schedule firing more than once an hour."

    plain_title = "An expensive model is running on a fast schedule"
    plain_meaning = (
        "The most capable models cost roughly ten to fifty times what a mid-tier "
        "one does per word produced. That is money well spent when the task is "
        "genuinely hard. On a schedule that fires every few minutes it multiplies "
        "into a real monthly bill, and plenty of scheduled work - summarising, "
        "tagging, extracting fields, reformatting - is handled just as well by a "
        "cheaper model. The estimate below shows what the difference would be."
    )
    plain_fix = (
        "Two independent questions, worth answering in this order.\n"
        "1. Does it need to run this often? Halving the schedule halves the bill "
        "and usually costs nothing else. Check whether anyone actually reads the "
        "output between runs.\n"
        "2. Does it need this model? See the comparison above. Do not swap on "
        "price alone - build a small set of real test cases, run them against "
        "both models, and compare the results before you change anything."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        runs, source = runs_per_month(workflow)
        if not runs or runs <= HOURLY_RUNS_PER_MONTH:
            return

        for node in _llm_nodes(workflow):
            model_id = _param(node, MODEL_PARAM_KEYS)
            model = pricing.lookup(str(model_id)) if model_id else None
            if model is None or model.tier != pricing.FRONTIER:
                continue

            max_tokens = _param(node, MAX_TOKEN_KEYS)
            try:
                max_tokens = float(max_tokens) if max_tokens else None
            except (TypeError, ValueError):
                max_tokens = None

            low, high = _cost_range(model, runs, max_tokens)
            detail = "\n".join(
                [
                    f"Current: {model.display} at {_money(model.input_price)}/"
                    f"{_money(model.output_price)} per 1M tokens (in/out)",
                    f"Estimated: {_money(low)} - {_money(high)} per month",
                    "",
                    *_assumption_block(runs, source, max_tokens),
                    *_alternatives_block(model, runs, max_tokens),
                ]
            )

            yield RuleHit(
                message=(
                    f"{model.display} (frontier tier) runs {runs:,.0f} times a month — "
                    f"estimated {_money(low)}-{_money(high)}/mo"
                ),
                node_name=node.name,
                line=node.line,
                detail=detail,
            )


class PollingTriggerCost(Rule):
    id = "polling-trigger-cost"
    default_severity = Severity.WARNING
    summary = "A schedule fires every few minutes, spending API calls mostly on finding nothing."

    plain_title = "This runs every few minutes whether there is anything to do or not"
    plain_meaning = (
        "Checking on a timer means most runs find nothing changed and do the work "
        "anyway: an API call, an execution counted against your n8n plan, and "
        "whatever the workflow spends per run. It is also the slowest option - "
        "you learn about a change up to a full interval after it happened. A "
        "webhook inverts that. The service tells you the moment something "
        "happens, so you run exactly as often as there is work, and the news "
        "arrives instantly rather than up to minutes late."
    )
    plain_fix = (
        "1. Check whether the service you are polling offers a trigger node in "
        "n8n, or supports webhooks. Most large ones do - Gmail, Slack, Stripe, "
        "Shopify, Notion, Airtable, GitHub, Telegram.\n"
        "2. If it does: replace the Schedule Trigger with that trigger node, or "
        "with a Webhook node you register with the service. Strictly better - "
        "fewer calls and faster.\n"
        "3. If it genuinely has no webhook: widen the interval to the slowest "
        "one anybody would actually notice. Going from every minute to every ten "
        "cuts the calls by 90% and usually nobody can tell."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        runs, source = runs_per_month(workflow)
        threshold = RUNS_PER_MONTH["minutes"] / FREQUENT_POLL_MINUTES
        if not runs or runs < threshold:
            return

        for node in workflow.nodes:
            if node.disabled or not node.type_is("scheduleTrigger", "interval", "cron"):
                continue
            yield RuleHit(
                message=(
                    f"{source.lower()} — about {runs:,.0f} runs a month, most of "
                    f"them finding nothing to do"
                ),
                node_name=node.name,
                line=node.line,
                detail="\n".join([
                    f"{source} -> {runs:,.0f} runs/month.",
                    "",
                    "Every one of those is an API call and an n8n execution, whether",
                    "or not anything changed. A webhook would fire only when there is",
                    "genuinely something to process, and would arrive immediately",
                    f"instead of up to {FREQUENT_POLL_MINUTES} minutes late.",
                ]),
            )
            return
