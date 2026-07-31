"""Model prices and capability tiers, used by the cost rules.

Hand-maintained on purpose. Fetching prices at runtime would mean a network call
from a tool whose whole promise is that it reads your workflow offline and sends
nothing anywhere, so the table lives here and carries the date it was last
checked. Every cost report prints that date, and the linter says so out loud once
the table is more than STALE_AFTER_DAYS old. A wrong number stated confidently is
worse than no number, so the failure mode here is "tell the user it might be
stale", never "quietly use 2026 prices in 2028".

`source` records where each row came from. PRIMARY means the vendor's own pricing
page; AGGREGATE means a third-party comparison site, which is usually right and
occasionally months behind. Suggestions surface the distinction so nobody quotes
an aggregate number to a client without checking it.

Prices are USD per million tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Bump this whenever a price is checked, even if nothing changed.
LAST_VERIFIED = date(2026, 7, 31)
STALE_AFTER_DAYS = 90

PRIMARY = "primary"      # taken from the vendor's own pricing page
AGGREGATE = "aggregate"  # taken from a third-party comparison site

# Capability tiers. Suggestions only ever step down one tier at a time: a
# frontier-to-small jump is a different product, not a cost optimisation.
FRONTIER = "frontier"
MID = "mid"
SMALL = "small"

TIER_ORDER = (FRONTIER, MID, SMALL)


@dataclass(frozen=True)
class Model:
    id: str
    display: str
    provider: str
    tier: str
    input_price: float
    output_price: float
    source: str
    context: int | None = None
    note: str = ""

    def cost_for(self, input_tokens: float, output_tokens: float) -> float:
        return (
            input_tokens * self.input_price / 1_000_000
            + output_tokens * self.output_price / 1_000_000
        )


# Ordered roughly by provider. Only models reachable from an n8n node (directly
# or through OpenRouter/Groq) are worth carrying.
CATALOG: tuple[Model, ...] = (
    # --- OpenAI - developers.openai.com/api/docs/pricing
    Model("gpt-5.6-sol", "GPT-5.6 Sol", "OpenAI", FRONTIER, 5.00, 30.00, PRIMARY, 1_000_000),
    Model("gpt-5.6-terra", "GPT-5.6 Terra", "OpenAI", MID, 2.00, 12.00, PRIMARY, 1_000_000),
    Model("gpt-5.6-luna", "GPT-5.6 Luna", "OpenAI", SMALL, 0.20, 1.20, PRIMARY, 1_000_000),
    Model("gpt-5.5", "GPT-5.5", "OpenAI", FRONTIER, 5.00, 30.00, PRIMARY, 272_000),
    Model("gpt-5.5-pro", "GPT-5.5 Pro", "OpenAI", FRONTIER, 30.00, 180.00, PRIMARY, 272_000),
    Model("gpt-5", "GPT-5", "OpenAI", MID, 1.25, 10.00, AGGREGATE, 400_000),
    Model("gpt-5-mini", "GPT-5 mini", "OpenAI", SMALL, 0.25, 2.00, AGGREGATE, 400_000),
    Model("gpt-5-nano", "GPT-5 nano", "OpenAI", SMALL, 0.05, 0.40, AGGREGATE, 400_000),
    Model("gpt-4.1", "GPT-4.1", "OpenAI", MID, 2.00, 8.00, AGGREGATE, 1_000_000),
    Model("gpt-4.1-mini", "GPT-4.1 mini", "OpenAI", SMALL, 0.40, 1.60, AGGREGATE, 1_000_000),
    Model("gpt-4.1-nano", "GPT-4.1 nano", "OpenAI", SMALL, 0.10, 0.40, AGGREGATE, 1_000_000),
    Model("gpt-4o", "GPT-4o", "OpenAI", MID, 2.50, 10.00, PRIMARY, 128_000),
    Model("gpt-4o-mini", "GPT-4o mini", "OpenAI", SMALL, 0.15, 0.60, PRIMARY, 128_000),
    Model("gpt-4-turbo", "GPT-4 Turbo (legacy)", "OpenAI", MID, 10.00, 30.00, AGGREGATE, 128_000),
    Model("gpt-4", "GPT-4 (legacy)", "OpenAI", FRONTIER, 30.00, 60.00, AGGREGATE, 8_192,
          note="Superseded and priced accordingly — almost never the right choice now."),
    Model("o1", "o1", "OpenAI", FRONTIER, 15.00, 60.00, PRIMARY, 200_000),
    Model("o1-pro", "o1-pro", "OpenAI", FRONTIER, 150.00, 600.00, PRIMARY, 200_000),

    # --- Anthropic - platform.claude.com/docs/en/about-claude/pricing
    Model("claude-fable-5", "Claude Fable 5", "Anthropic", FRONTIER, 10.00, 50.00, PRIMARY, 1_000_000),
    Model("claude-opus-5", "Claude Opus 5", "Anthropic", FRONTIER, 5.00, 25.00, PRIMARY, 1_000_000),
    Model("claude-opus-4-8", "Claude Opus 4.8", "Anthropic", FRONTIER, 5.00, 25.00, PRIMARY, 1_000_000),
    Model(
        "claude-sonnet-5", "Claude Sonnet 5", "Anthropic", MID, 2.00, 10.00, PRIMARY, 1_000_000,
        note="Introductory pricing through 2026-08-31; $3/$15 from 2026-09-01.",
    ),
    Model("claude-sonnet-4-6", "Claude Sonnet 4.6", "Anthropic", MID, 3.00, 15.00, PRIMARY, 1_000_000),
    Model("claude-haiku-4-5", "Claude Haiku 4.5", "Anthropic", SMALL, 1.00, 5.00, PRIMARY, 200_000),

    # --- Google - ai.google.dev/gemini-api/docs/pricing
    Model("gemini-3.1-pro", "Gemini 3.1 Pro Preview", "Google", FRONTIER, 2.00, 12.00, PRIMARY, 1_000_000,
          note="Rises to $4/$18 above 200k input tokens."),
    Model("gemini-2.5-pro", "Gemini 2.5 Pro", "Google", FRONTIER, 1.25, 10.00, PRIMARY, 1_000_000,
          note="Rises to $2.50/$15 above 200k input tokens."),
    Model("gemini-3.6-flash", "Gemini 3.6 Flash", "Google", MID, 1.50, 7.50, PRIMARY, 1_000_000),
    Model("gemini-3.5-flash", "Gemini 3.5 Flash", "Google", MID, 1.50, 9.00, PRIMARY, 1_000_000),
    Model("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "Google", SMALL, 0.30, 2.50, PRIMARY, 1_000_000),
    Model("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", "Google", SMALL, 0.25, 1.50, PRIMARY, 1_000_000),
    Model("gemini-2.5-flash", "Gemini 2.5 Flash", "Google", SMALL, 0.30, 2.50, PRIMARY, 1_000_000),
    Model("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", "Google", SMALL, 0.10, 0.40, PRIMARY, 1_000_000),
    Model("gemini-2.0-flash", "Gemini 2.0 Flash (legacy)", "Google", SMALL, 0.10, 0.40, AGGREGATE, 1_000_000),
    Model("gemini-1.5-pro", "Gemini 1.5 Pro (legacy)", "Google", MID, 1.25, 5.00, AGGREGATE, 2_000_000),

    # --- DeepSeek - api-docs.deepseek.com/quick_start/pricing
    Model("deepseek-v4-pro", "DeepSeek V4 Pro", "DeepSeek", MID, 0.435, 0.87, PRIMARY, 1_000_000),
    Model("deepseek-v4-flash", "DeepSeek V4 Flash", "DeepSeek", SMALL, 0.14, 0.28, PRIMARY, 1_000_000),

    # --- Moonshot / Kimi
    Model("kimi-k3", "Kimi K3", "Moonshot", FRONTIER, 3.00, 15.00, AGGREGATE, 1_000_000),
    Model("kimi-k2.6", "Kimi K2.6", "Moonshot", MID, 0.95, 4.00, AGGREGATE, 262_144),
    Model("kimi-k2.5", "Kimi K2.5", "Moonshot", SMALL, 0.60, 3.00, AGGREGATE, 262_144),

    # --- Zhipu / Z.ai
    Model("glm-5.2", "GLM-5.2", "Zhipu", MID, 1.40, 4.40, AGGREGATE, 200_000),

    # --- MiniMax
    Model("minimax-m3", "MiniMax M3", "MiniMax", SMALL, 0.30, 1.20, AGGREGATE, 512_000,
          note="Promotional 50% rate; list price is $0.60/$2.40."),

    # --- Alibaba Qwen
    Model("qwen3.5-plus", "Qwen3.5 Plus", "Alibaba", MID, 0.40, 2.40, AGGREGATE, 262_144),
    Model("qwen3.5-flash", "Qwen3.5 Flash", "Alibaba", SMALL, 0.10, 0.40, AGGREGATE, 262_144),
    Model("qwen3.7-flash", "Qwen3.7 Flash", "Alibaba", SMALL, 0.03, 0.13, AGGREGATE, 1_000_000),

    # --- xAI
    Model("grok-build-0.1", "Grok Build 0.1", "xAI", MID, 1.00, 2.00, AGGREGATE, 256_000),

    # --- Mistral
    Model("mistral-large", "Mistral Large", "Mistral", MID, 2.00, 6.00, AGGREGATE, 262_144),
    Model("open-mixtral-8x7b", "Mixtral 8x7B (legacy)", "Mistral", SMALL, 0.70, 0.70, AGGREGATE, 32_768),
    Model("mistral-small", "Mistral Small 3", "Mistral", SMALL, 0.10, 0.30, AGGREGATE, 131_072),
    Model("mistral-nemo", "Mistral Nemo", "Mistral", SMALL, 0.019, 0.030, AGGREGATE, 131_072),

    # --- Open-weight, via Groq
    Model("gpt-oss-120b", "GPT-OSS 120B", "Groq", SMALL, 0.15, 0.60, AGGREGATE, 128_000),
    Model("llama-3.3-70b-versatile", "Llama 3.3 70B", "Groq", SMALL, 0.59, 0.79, AGGREGATE, 128_000),
    Model("llama-3.1-8b-instant", "Llama 3.1 8B Instant", "Groq", SMALL, 0.05, 0.08, AGGREGATE, 128_000),
)

BY_ID = {model.id: model for model in CATALOG}

# Trailing release dates n8n keeps on model ids, in both the shapes vendors use:
# claude-sonnet-4-5-20250929 and gpt-4o-2024-08-06.
_DATE_SUFFIX = re.compile(r"[-_]?20\d{2}-?\d{2}-?\d{2}$")
_SEPARATORS = re.compile(r"[_\s]+")


def normalize(model_id: str) -> str:
    value = _SEPARATORS.sub("-", model_id.strip().lower())
    # Provider-prefixed ids from OpenRouter and friends: "anthropic/claude-opus-5".
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    value = _DATE_SUFFIX.sub("", value)
    return value.rstrip("-")


def lookup(model_id: str) -> Model | None:
    """Best-effort match of an n8n model parameter to a catalogue entry.

    Exact first, then longest-prefix, so `claude-opus-5-20260514` resolves and an
    unknown `claude-opus-9` does not silently match `claude-opus-5`.
    """
    if not model_id:
        return None
    value = normalize(model_id)
    if value in BY_ID:
        return BY_ID[value]

    dotted = value.replace(".", "-")
    candidates = [
        model for model in CATALOG
        if value.startswith(model.id) or dotted.startswith(model.id.replace(".", "-"))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda m: len(m.id))


def cheaper_alternatives(model: Model, limit: int = 3) -> list[Model]:
    """Cheaper models worth *evaluating* against this one.

    Same tier or exactly one step down — never further. A frontier-to-small swap
    is a change of product, and this table has no way to know whether the smaller
    model can do the task. Ranked by how much they save on output tokens, which
    is where the money goes in practice.
    """
    tier_index = TIER_ORDER.index(model.tier)
    allowed = set(TIER_ORDER[tier_index:tier_index + 2])

    candidates = [
        other for other in CATALOG
        if other.id != model.id
        and other.tier in allowed
        and other.output_price < model.output_price
    ]
    candidates.sort(key=lambda m: (m.output_price, m.input_price))

    picked: list[Model] = []
    seen_providers: set[str] = set()

    # The same vendor's cheaper model first. It is the swap that needs no new
    # account, no new credential in n8n, and no second bill to reconcile — often
    # the difference between a suggestion that gets acted on and one that doesn't.
    for candidate in candidates:
        if candidate.provider == model.provider:
            picked.append(candidate)
            seen_providers.add(candidate.provider)
            break

    # Then spread across vendors: three models from one provider is a worse
    # answer than one each from three.
    for candidate in candidates:
        if len(picked) == limit:
            return picked
        if candidate.provider not in seen_providers:
            picked.append(candidate)
            seen_providers.add(candidate.provider)

    for candidate in candidates:
        if len(picked) == limit:
            break
        if candidate not in picked:
            picked.append(candidate)
    return picked


def days_since_verified(today: date | None = None) -> int:
    return ((today or date.today()) - LAST_VERIFIED).days


def is_stale(today: date | None = None) -> bool:
    return days_since_verified(today) > STALE_AFTER_DAYS


def verification_note(today: date | None = None) -> str:
    days = days_since_verified(today)
    line = f"Prices last verified {LAST_VERIFIED.isoformat()} ({days} days ago)."
    if is_stale(today):
        return (
            line + " This table is out of date — model prices move monthly. "
            "Check the vendor's pricing page before quoting any of these figures."
        )
    return line + " Verify before quoting a client."
