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


# --- Phase B rules -------------------------------------------------------


def findings_for(name: str, rule_id: str):
    return [f for f in lint_workflow(load_workflow(name), Config()) if f.rule_id == rule_id]


def test_embedded_secret_finds_a_key_assigned_in_a_code_node():
    hits = findings_for("embedded.json", "embedded-secret")
    assert any(h.node_name == "Build Request" for h in hits)


def test_embedded_secret_finds_a_key_in_a_header_parameter():
    messages = " ".join(f.message for f in findings_for("embedded.json", "embedded-secret"))
    assert "x-api-key" in messages


def test_embedded_secret_ignores_placeholders_and_prose():
    # The fixture's code node also holds REPLACE_WITH_TOKEN and a plain English
    # sentence; neither should be reported.
    redacted = " ".join(f.message for f in findings_for("embedded.json", "embedded-secret"))
    assert "REPLACE" not in redacted
    assert "hello" not in redacted


def test_embedded_secret_never_prints_a_whole_secret():
    for finding in findings_for("embedded.json", "embedded-secret"):
        assert "…" in finding.message, finding.message


def test_credential_in_url_flags_a_key_in_the_query_string():
    hits = findings_for("embedded.json", "credential-in-url")
    assert [h.node_name for h in hits] == ["Fetch Items"]


def test_credential_in_url_ignores_an_n8n_expression():
    # "Fetch Safely" passes api_key={{ $credentials.apiKey }} — resolved at run
    # time, not a literal, so it must not fire.
    assert all(h.node_name != "Fetch Safely" for h in findings_for("embedded.json", "credential-in-url"))


def test_error_output_swallowed_catches_both_the_new_and_legacy_setting():
    hits = findings_for("sloppy.json", "error-output-swallowed")
    names = {h.node_name for h in hits}
    assert names == {"HTTP Request", "HTTP Request1"}  # onError=..., continueOnFail=true


def test_error_output_swallowed_allows_a_real_error_branch():
    # clean.json sets nothing; embedded.json sets nothing. Neither should fire.
    assert findings_for("clean.json", "error-output-swallowed") == []


def test_missing_timeout_fires_on_an_http_node_without_one():
    assert {h.node_name for h in findings_for("sloppy.json", "missing-timeout")} == {
        "HTTP Request", "HTTP Request1"
    }


def test_missing_timeout_quiet_when_timeout_is_set():
    assert findings_for("embedded.json", "missing-timeout") == []


def test_default_node_names_fires_once_the_threshold_is_reached():
    names = {h.node_name for h in findings_for("sloppy.json", "default-node-names")}
    assert names == {"HTTP Request", "HTTP Request1", "Code2"}


def test_default_node_names_stays_quiet_below_the_threshold():
    # embedded.json has descriptive names throughout.
    assert findings_for("embedded.json", "default-node-names") == []


def test_entropy_floor_separates_a_key_from_a_repeated_placeholder():
    from n8n_linter.text_utils import shannon_entropy

    assert shannon_entropy("xxxxxxxxxxxxxxxx") < 3.0
    assert shannon_entropy("7f3Ka92mFhs82nXqL4vZ") >= 3.0
