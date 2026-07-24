# Contributing

Thanks for helping make n8n workflows safer to ship.

## Development setup

```bash
git clone https://github.com/Redsf/n8n-workflow-linter
cd n8n-workflow-linter
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

No runtime dependencies are allowed — the linter must keep running on the
standard library alone so it works in bare CI jobs. Dev-only tooling (pytest)
is fine.

## Adding a rule

1. Implement a `Rule` subclass in `src/n8n_linter/rules/`. Group it with related
   rules (`credentials.py`, `reliability.py`, `hygiene.py`) or add a new module.
2. Give it a kebab-case `id`, a sensible `default_severity`, and a one-line
   `summary`.
3. `check()` yields `RuleHit(message, node_name=None, line=None)`. Don't set
   severity or path — the engine does that from config.
4. Register the instance in `ALL_RULES` in `rules/__init__.py`.
5. Add a fixture that triggers it and confirm a clean fixture does **not**.

## The false-positive bar

This linter is meant to run in CI on every push. A noisy rule gets the whole
tool disabled, so the bar for a new rule is: **near-zero false positives on real
workflows.** If a rule is inherently heuristic (like `hardcoded-resource-id`),
default it to `warning`, not `error`, and document the heuristic in the code.

Prefer a rule that catches 90% of a problem with no false positives over one
that catches 100% and cries wolf.

## Tests

Every rule needs both directions covered: it fires on a bad fixture and stays
silent on a good one. Run `pytest` before opening a PR. CI runs the suite on
Python 3.9, 3.11, and 3.13.

## Commit style

Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`).
