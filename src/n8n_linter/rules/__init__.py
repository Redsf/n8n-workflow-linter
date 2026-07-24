"""Rule registry.

To add a rule: implement a Rule subclass in one of the modules here and add an
instance to ALL_RULES. Nothing else needs to change — the engine, config, and
docs all read from this list.
"""

from __future__ import annotations

from .base import Rule
from .credentials import RealCredentialId
from .hardcoded_ids import HardcodedResourceId
from .hygiene import DisabledNode, PinnedData, UnauthenticatedWebhook
from .reliability import MissingRetry, NoErrorTrigger, OrphanNode
from .secrets import HardcodedSecret

ALL_RULES: tuple[Rule, ...] = (
    RealCredentialId(),
    HardcodedSecret(),
    HardcodedResourceId(),
    NoErrorTrigger(),
    MissingRetry(),
    OrphanNode(),
    PinnedData(),
    UnauthenticatedWebhook(),
    DisabledNode(),
)

RULES_BY_ID: dict[str, Rule] = {rule.id: rule for rule in ALL_RULES}
