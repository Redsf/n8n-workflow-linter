"""Configuration: per-rule severity overrides and disabling.

Config is optional. With no config file and no flags, every rule runs at its
default severity. A `.n8nlintrc.json` in the working directory (or one named
with --config) can override severities or turn rules off:

    {
      "rules": {
        "missing-retry": "off",
        "hardcoded-resource-id": "error",
        "disabled-node": "warning"
      }
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .report import Severity
from .rules import RULES_BY_ID

DEFAULT_CONFIG_NAME = ".n8nlintrc.json"


@dataclass
class Config:
    # rule id -> Severity, or None meaning "disabled".
    severities: dict[str, Severity | None] = field(default_factory=dict)

    def severity_for(self, rule_id: str, default: Severity) -> Severity | None:
        """Effective severity for a rule: an override if set, else its default."""
        if rule_id in self.severities:
            return self.severities[rule_id]
        return default


class ConfigError(ValueError):
    """Raised when a config file is malformed or names an unknown rule/severity."""


def _parse_rules(rules: dict) -> dict[str, Severity | None]:
    severities: dict[str, Severity | None] = {}
    for rule_id, value in rules.items():
        if rule_id not in RULES_BY_ID:
            raise ConfigError(f"unknown rule in config: {rule_id!r}")
        if not isinstance(value, str):
            raise ConfigError(f"severity for {rule_id!r} must be a string")
        if value.lower() == "off":
            severities[rule_id] = None
            continue
        try:
            severities[rule_id] = Severity.parse(value)
        except ValueError as exc:
            raise ConfigError(f"{rule_id!r}: {exc}") from exc
    return severities


def from_dict(data: dict) -> Config:
    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        raise ConfigError("'rules' must be an object")
    return Config(severities=_parse_rules(rules))


def load_config(explicit_path: str | None) -> Config:
    """Load config from an explicit path, or the default file if it exists."""
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            raise ConfigError(f"config file not found: {explicit_path}")
    else:
        path = Path(DEFAULT_CONFIG_NAME)
        if not path.exists():
            return Config()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be an object")
    return from_dict(data)


def apply_cli_disables(config: Config, disabled: list[str]) -> Config:
    """Turn off rules named with repeated --disable flags."""
    for rule_id in disabled:
        if rule_id not in RULES_BY_ID:
            raise ConfigError(f"unknown rule passed to --disable: {rule_id!r}")
        config.severities[rule_id] = None
    return config
