"""CLI-level tests: exit codes, formats, config, and strict mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from n8n_linter.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main

FIXTURES = Path(__file__).parent / "fixtures"


def run(args: list[str]) -> int:
    return main(args)


def test_clean_file_exits_zero(capsys):
    assert run([str(FIXTURES / "clean.json")]) == EXIT_OK


def test_leaky_file_exits_one_on_errors(capsys):
    assert run([str(FIXTURES / "leaky.json")]) == EXIT_FINDINGS


def test_warnings_alone_pass_without_strict(capsys):
    # unreliable.json has warnings and info but no errors.
    assert run([str(FIXTURES / "unreliable.json")]) == EXIT_OK


def test_warnings_fail_under_strict(capsys):
    assert run([str(FIXTURES / "unreliable.json"), "--strict"]) == EXIT_FINDINGS


def test_disable_rule_suppresses_it(capsys):
    # unreliable.json's only non-info findings are warnings; disable them all
    # and --strict should then pass.
    code = run([
        str(FIXTURES / "unreliable.json"),
        "--strict",
        "--disable", "no-error-trigger",
        "--disable", "missing-retry",
        "--disable", "orphan-node",
    ])
    assert code == EXIT_OK


def test_unknown_disable_rule_is_usage_error(capsys):
    assert run([str(FIXTURES / "clean.json"), "--disable", "no-such-rule"]) == EXIT_USAGE


def test_json_format_is_parseable(capsys):
    run([str(FIXTURES / "leaky.json"), "--format", "json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["errors"] >= 1
    assert any(f["rule"] == "real-credential-id" for f in payload["findings"])


def test_github_format_emits_workflow_commands(capsys):
    run([str(FIXTURES / "leaky.json"), "--format", "github"])
    out = capsys.readouterr().out
    assert "::error " in out
    assert "file=" in out


def test_no_files_found_is_usage_error(tmp_path, capsys):
    assert run([str(tmp_path)]) == EXIT_USAGE


def test_list_rules_exits_zero(capsys):
    assert run(["--list-rules"]) == EXIT_OK
    assert "real-credential-id" in capsys.readouterr().out


def test_malformed_file_is_reported_as_error(capsys):
    assert run([str(FIXTURES / "malformed.json")]) == EXIT_FINDINGS
    assert "invalid-workflow" in capsys.readouterr().out


def test_plain_format_leads_with_a_verdict(capsys):
    assert run([str(FIXTURES / "leaky.json"), "--format", "plain"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "DO NOT SHARE THIS FILE YET" in out
    assert "What this means" in out
    assert "How to fix it" in out


def test_plain_format_says_safe_when_only_warnings(capsys):
    assert run([str(FIXTURES / "unreliable.json"), "--format", "plain"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "SAFE TO SHARE" in out
    assert "DO NOT SHARE" not in out


def test_plain_format_says_all_clear_on_a_clean_file(capsys):
    assert run([str(FIXTURES / "clean.json"), "--format", "plain"]) == EXIT_OK
    assert "ALL CLEAR" in capsys.readouterr().out


def test_explain_flag_is_shorthand_for_plain(capsys):
    run([str(FIXTURES / "leaky.json"), "--explain"])
    explained = capsys.readouterr().out
    run([str(FIXTURES / "leaky.json"), "--format", "plain"])
    assert explained == capsys.readouterr().out


def test_plain_format_explains_an_unparseable_file(capsys):
    assert run([str(FIXTURES / "malformed.json"), "--explain"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    # Falls back to load-error copy rather than crashing on a missing Rule class.
    assert "not a workflow n8n can read" in out


def test_plain_format_does_not_repeat_an_explanation_per_node(capsys):
    # unreliable.json trips orphan-node on two separate nodes; the explanation
    # should appear once, with both node names listed.
    run([str(FIXTURES / "unreliable.json"), "--explain"])
    out = capsys.readouterr().out
    assert out.count("A step is floating loose and will never run") == 1
    assert "Steps affected:" in out


def test_every_rule_has_plain_language_copy():
    from n8n_linter.rules import ALL_RULES

    for rule in ALL_RULES:
        assert rule.plain_title, f"{rule.id} has no plain_title"
        assert rule.plain_meaning, f"{rule.id} has no plain_meaning"
        assert rule.plain_fix, f"{rule.id} has no plain_fix"
