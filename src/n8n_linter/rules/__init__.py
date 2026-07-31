"""Rule registry.

To add a rule: implement a Rule subclass in one of the modules here and add an
instance to ALL_RULES. Nothing else needs to change — the engine, config, and
docs all read from this list.
"""

from __future__ import annotations

from .base import Rule
from .cost import ExpensiveModelHighFrequency, LlmCostUnbounded, PollingTriggerCost
from .credentials import RealCredentialId
from .embedded import CredentialInUrl, EmbeddedSecret
from .hardcoded_ids import HardcodedResourceId
from .hygiene import DefaultNodeNames, DisabledNode, PinnedData, UnauthenticatedWebhook
from .reliability import (
    ErrorOutputSwallowed,
    MissingRetry,
    MissingTimeout,
    NoErrorTrigger,
    OrphanNode,
)
from .secrets import HardcodedSecret

ALL_RULES: tuple[Rule, ...] = (
    # Leaks first — these are the ones that must not reach a public repo.
    RealCredentialId(),
    HardcodedSecret(),
    EmbeddedSecret(),
    CredentialInUrl(),
    HardcodedResourceId(),
    # Then reliability.
    NoErrorTrigger(),
    MissingRetry(),
    MissingTimeout(),
    ErrorOutputSwallowed(),
    OrphanNode(),
    # Then cost — what it spends, and what it could spend instead.
    ExpensiveModelHighFrequency(),
    LlmCostUnbounded(),
    PollingTriggerCost(),
    # Then hygiene.
    PinnedData(),
    UnauthenticatedWebhook(),
    DefaultNodeNames(),
    DisabledNode(),
)

RULES_BY_ID: dict[str, Rule] = {rule.id: rule for rule in ALL_RULES}
