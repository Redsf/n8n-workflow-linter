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


# --- Phase C cost rules --------------------------------------------------


def test_expensive_model_flags_a_frontier_model_on_a_fast_schedule():
    hits = findings_for("expensive.json", "expensive-model-high-frequency")
    assert [h.node_name for h in hits] == ["Opus Model"]
    assert "8,640" in hits[0].message


def test_cost_estimate_states_its_assumptions():
    detail = findings_for("expensive.json", "expensive-model-high-frequency")[0].detail
    # An estimate that hides its inputs is the thing this rule exists to avoid.
    assert "assumed - not measured" in detail
    assert "runs/month" in detail
    assert "Prices last verified" in detail


def test_cost_estimate_offers_the_same_vendor_first():
    detail = findings_for("expensive.json", "expensive-model-high-frequency")[0].detail
    alternatives = detail.split("Cheaper models to evaluate against it:")[1]
    # Opus 5 is Anthropic, so Sonnet 5 should lead: no new account or credential.
    assert alternatives.strip().startswith("Claude Sonnet 5")


def test_cost_estimate_refuses_to_promise_quality():
    detail = findings_for("expensive.json", "expensive-model-high-frequency")[0].detail
    assert "not something a" in detail and "linter can know" in detail
    assert "agent-evals" in detail


def test_third_party_prices_are_labelled_as_such():
    detail = findings_for("expensive.json", "expensive-model-high-frequency")[0].detail
    assert "[price from a third-party tracker]" in detail


def test_llm_cost_unbounded_fires_when_no_max_tokens_is_set():
    hits = findings_for("expensive.json", "llm-cost-unbounded")
    assert [h.node_name for h in hits] == ["Opus Model"]


def test_polling_trigger_cost_fires_once_not_per_node():
    assert len(findings_for("expensive.json", "polling-trigger-cost")) == 1


def test_cost_rules_stay_quiet_on_a_workflow_with_no_model():
    for rule in ("expensive-model-high-frequency", "llm-cost-unbounded", "polling-trigger-cost"):
        assert findings_for("clean.json", rule) == [], rule


# --- pricing table -------------------------------------------------------


def test_model_lookup_tolerates_n8n_id_shapes():
    from n8n_linter import pricing

    assert pricing.lookup("claude-opus-5").id == "claude-opus-5"
    assert pricing.lookup("anthropic/claude-opus-5").id == "claude-opus-5"
    assert pricing.lookup("claude-sonnet-5-20260514").id == "claude-sonnet-5"
    assert pricing.lookup("GPT-4o-mini").id == "gpt-4o-mini"
    assert pricing.lookup("some-model-nobody-has-heard-of") is None
    assert pricing.lookup("") is None


def test_alternatives_never_jump_more_than_one_capability_tier():
    from n8n_linter import pricing

    for model in pricing.CATALOG:
        allowed = set(pricing.TIER_ORDER[pricing.TIER_ORDER.index(model.tier):][:2])
        for alternative in pricing.cheaper_alternatives(model):
            assert alternative.tier in allowed, f"{model.id} -> {alternative.id}"
            assert alternative.output_price < model.output_price


def test_pricing_table_declares_a_source_for_every_row():
    from n8n_linter import pricing

    for model in pricing.CATALOG:
        assert model.source in (pricing.PRIMARY, pricing.AGGREGATE), model.id
        assert model.input_price > 0 and model.output_price > 0, model.id


def test_staleness_warning_appears_once_the_table_ages():
    from datetime import timedelta

    from n8n_linter import pricing

    fresh = pricing.LAST_VERIFIED + timedelta(days=1)
    stale = pricing.LAST_VERIFIED + timedelta(days=pricing.STALE_AFTER_DAYS + 1)
    assert not pricing.is_stale(fresh)
    assert pricing.is_stale(stale)
    assert "out of date" in pricing.verification_note(stale)
    assert "out of date" not in pricing.verification_note(fresh)
