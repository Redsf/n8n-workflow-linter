#!/usr/bin/env bash
# Run everything CI runs, in the same order, before pushing.
#
# `pytest` alone is not the gate. CI also smoke-tests the CLI and lints
# examples/ under --strict, and a new rule that fires on the clean example will
# pass the test suite and still break the build.
set -euo pipefail

echo "==> tests"
python -m pytest -q

echo "==> CLI smoke test"
n8n-lint --version
n8n-lint --list-rules > /dev/null

echo "==> examples must stay clean under --strict"
n8n-lint examples --strict

echo
echo "All CI steps passed locally."
