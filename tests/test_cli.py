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
