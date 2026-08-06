"""Tests for the in-process API the browser build calls.

The web front end has no filesystem and no stdout, so it goes through
`api.analyze` rather than the CLI. These tests hold that path to the same
standard as the CLI: same verdicts, same rules, and a result that survives a
round trip through JSON — because on the far side it is JavaScript, and a
dataclass or an enum that leaks through is a runtime error in a browser nobody
is watching.
"""

from __future__ import annotations

import json
from pathlib import Path

from n8n_linter import api

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_clean_workflow_reports_all_clear():
    result = api.analyze(fixture("clean.json"), "clean.json")
    assert result["verdict"] == api.VERDICT_CLEAN
    assert result["summary"] == {"errors": 0, "warnings": 0, "info": 0, "nodes": 4}
    assert result["groups"] == []


def test_a_leak_is_the_verdict_even_when_other_things_are_wrong():
    result = api.analyze(fixture("embedded.json"), "embedded.json")
    assert result["verdict"] == api.VERDICT_LEAK
    assert result["summary"]["errors"] == 3


def test_warnings_alone_are_still_safe_to_share():
    result = api.analyze(fixture("sloppy.json"), "sloppy.json")
    assert result["verdict"] == api.VERDICT_SAFE
    assert result["summary"]["errors"] == 0
    assert result["summary"]["warnings"] > 0


def test_broken_json_is_unreadable_not_a_crash():
    result = api.analyze("{ not json at all", "broken.json")
    assert result["ok"] is False
    assert result["verdict"] == api.VERDICT_UNREADABLE
    assert "invalid JSON" in result["error"]


def test_valid_json_that_is_not_a_workflow_is_rejected():
    result = api.analyze('{"hello": "world"}', "x.json")
    assert result["verdict"] == api.VERDICT_UNREADABLE
    assert "nodes" in result["error"]


def test_result_survives_a_json_round_trip():
    # The browser does JSON.parse on this. A dataclass or an enum surviving into
    # the payload would fail there, far from any test.
    result = api.analyze(fixture("expensive.json"), "expensive.json")
    assert json.loads(json.dumps(result)) == result


def test_findings_are_grouped_by_rule_with_every_node_listed():
    result = api.analyze(fixture("sloppy.json"), "sloppy.json")
    names = {g["rule"]: g for g in result["groups"]}
    swallowed = names["error-output-swallowed"]
    assert swallowed["count"] == 2
    assert set(swallowed["nodes"]) == {"HTTP Request", "HTTP Request1"}


def test_every_group_carries_its_plain_language_copy():
    # The UI renders these directly; a rule shipping without them would render a
    # blank card rather than fail loudly.
    result = api.analyze(fixture("sloppy.json"), "sloppy.json")
    for group in result["groups"]:
        assert group["title"], group["rule"]
        assert group["meaning"], group["rule"]
        assert group["fix"], group["rule"]


def test_cost_detail_is_carried_through_to_the_front_end():
    result = api.analyze(fixture("expensive.json"), "expensive.json")
    cost = next(g for g in result["groups"] if g["rule"] == "expensive-model-high-frequency")
    detail = "\n".join(cost["details"])
    assert "Cheaper models to evaluate against it" in detail
    assert "assumed - not measured" in detail


def test_analyze_json_returns_a_parseable_string():
    parsed = json.loads(api.analyze_json(fixture("clean.json"), "clean.json"))
    assert parsed["verdict"] == api.VERDICT_CLEAN


def test_rule_catalogue_covers_every_rule():
    from n8n_linter.rules import ALL_RULES

    catalogue = api.rule_catalogue()
    assert len(catalogue) == len(ALL_RULES)
    assert all(entry["title"] and entry["severity"] for entry in catalogue)


def test_api_and_cli_loader_agree_on_what_a_workflow_is():
    # Two parsers for one file format is how a web build starts quietly
    # disagreeing with CI about whether a file is valid.
    from n8n_linter.loader import load

    for name in ("clean.json", "leaky.json", "expensive.json", "sloppy.json"):
        from_disk = load(FIXTURES / name)
        from_text = api.parse(fixture(name), name)
        assert [n.name for n in from_text.nodes] == [n.name for n in from_disk.nodes]
        assert [n.line for n in from_text.nodes] == [n.line for n in from_disk.nodes]

    for bad in ("malformed.json", "not_workflow.json"):
        assert type(api.parse(fixture(bad), bad)) is type(load(FIXTURES / bad))


# --- the web page's static rule list ------------------------------------


def test_static_rule_list_in_the_page_matches_the_catalogue():
    """The page ships the rule list as HTML so the section is not blank before
    the checker loads. That copy has no way of noticing when a rule is added,
    renamed, or re-graded, so this asserts the two still agree."""
    import html as html_mod
    import re

    page = (Path(__file__).parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    block = re.search(r'<div id="rule-list".*?>(.*?)</div>\s*</div>', page, re.S)
    assert block, "could not find the #rule-list block in web/index.html"

    rows = re.findall(
        r'<span class="rule-sev (\w+)">[^<]+</span><span>(.*?)</span>', block.group(1)
    )
    listed = [(sev, html_mod.unescape(title)) for sev, title in rows]
    expected = [(r["severity"], r["title"]) for r in api.rule_catalogue()]

    assert listed == expected, (
        "web/index.html rule list is out of date. Regenerate it from "
        "api.rule_catalogue()."
    )
