#!/usr/bin/env bash
# Build the wheel the browser build loads, and write the manifest that tells the
# page its filename.
#
# This is what keeps the web app from drifting away from the CLI: the page does
# not carry its own copy of the rules, it installs this wheel and calls the same
# `n8n_linter.api.analyze` the tests cover. CI runs this on every push, so a rule
# added to the package is live on the site without anyone editing JavaScript.
set -euo pipefail

cd "$(dirname "$0")/.."

OUT="web/dist"
rm -rf "$OUT" build ./*.egg-info
mkdir -p "$OUT"

echo "==> building wheel"
python -m pip install --quiet --upgrade build
python -m build --wheel --outdir "$OUT" > /dev/null

WHEEL="$(basename "$(ls -1 "$OUT"/*.whl | head -n1)")"
VERSION="$(python -c "import re,pathlib; print(re.search(r'version = \"([^\"]+)\"', pathlib.Path('pyproject.toml').read_text()).group(1))")"

cat > "$OUT/wheel.json" <<JSON
{
  "file": "$WHEEL",
  "version": "$VERSION"
}
JSON

echo "==> $OUT/$WHEEL"
echo "==> manifest written for v$VERSION"
