"""Rule-level tests: each rule fires on the bad fixture and stays quiet on the good one."""

from __future__ import annotations

from pathlib import Path

import pytest

from n8n_linter.config import Config
from n8n_linter.engine import lint_workflow
from n8n_linter.loader import load
from n8n_linter.model import LoadError, Workflow

FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> Workflow:
    result = load(FIXTURES / name)
    assert isinstance(result, Workflow), result
    return result


def rule_ids(name: str) -> set[str]:
    findings = lint_workflow(load_workflow(name), Config())
    return {f.rule_id for f in findings}


def test_clean_workflow_has_no_findings():
    assert rule_ids("clean.json") == set()


def test_leaky_workflow_flags_credentials_secrets_and_data():
    ids = rule_ids("leaky.json")
    assert "real-credential-id" in ids
    assert "hardcoded-secret" in ids
    assert "hardcoded-resource-id" in ids
    assert "pinned-data" in ids
    assert "unauthenticated-webhook" in ids


def test_unreliable_workflow_flags_reliability_gaps():
    ids = rule_ids("unreliable.json")
    assert "no-error-trigger" in ids
    assert "missing-retry" in ids
    assert "orphan-node" in ids
    assert "disabled-node" in ids


def test_sticky_note_is_not_an_orphan():
    findings = lint_workflow(load_workflow("unreliable.json"), Config())
    orphans = {f.node_name for f in findings if f.rule_id == "orphan-node"}
    assert "Notes" not in orphans
    assert "Orphan Node" in orphans


def test_real_credential_id_is_redacted():
    findings = lint_workflow(load_workflow("leaky.json"), Config())
    cred = next(f for f in findings if f.rule_id == "real-credential-id")
    assert "8gccIjcuf3gvaoEr" not in cred.message  # never echo the raw id
    assert "…" in cred.message


def test_secret_finding_carries_a_line_number():
    findings = lint_workflow(load_workflow("leaky.json"), Config())
    secret = next(f for f in findings if f.rule_id == "hardcoded-secret")
    assert secret.line is not None and secret.line > 0


def test_placeholder_credentials_do_not_fire():
    findings = lint_workflow(load_workflow("clean.json"), Config())
    assert not any(f.rule_id == "real-credential-id" for f in findings)


def test_malformed_json_is_a_load_error():
    result = load(FIXTURES / "malformed.json")
    assert isinstance(result, LoadError)
    assert "invalid JSON" in result.message


def test_non_workflow_json_is_a_load_error():
    result = load(FIXTURES / "not_workflow.json")
    assert isinstance(result, LoadError)
    assert "not an n8n workflow" in result.message


def test_google_id_heuristic_ignores_lowercase_slugs():
    """A 44-char lowercase webhook path must not be mistaken for a Google ID."""
    from n8n_linter.rules.hardcoded_ids import _looks_like_google_id

    assert not _looks_like_google_id("syncbricks-com-tutorial-candidate-shortlist")
    assert _looks_like_google_id("1zcuAB3I_PDgwjmAvXOEoKM2lZFGizrJZU1IMIs6LpXI")
