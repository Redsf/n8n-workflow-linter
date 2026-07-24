# n8n-workflow-linter

[![ci](https://github.com/Redsf/n8n-workflow-linter/actions/workflows/ci.yml/badge.svg)](https://github.com/Redsf/n8n-workflow-linter/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Static analysis for [n8n](https://n8n.io) workflow exports. Catches leaked
credentials, hardcoded secrets, missing error handling, and other problems in
CI — before a broken or leaky workflow lands in `main`.

Version-controlling n8n workflows as JSON is now common. Linting them is not.
A workflow JSON export will happily carry a live API key, a credential ID from
your private instance, real customer records pinned as test data, or an HTTP
call with no retry — and nothing tells you until it's in the repo or failing at
2am. This is the missing check.

```text
$ n8n-lint workflows/
workflows/cold_email.json
  :12   error   openAiApi credential uses a real instance ID (8gccIj…aoEr); replace with REPLACE_WITH_CREDENTIAL_ID (Personalize Email)
  :40   warning HTTP Request has retryOnFail disabled — a transient error will fail the run (Send)
        warning workflow ships pinned data for: Get Leads — remove it before publishing; it commonly contains real records

Checked 1 workflow file(s): 1 error(s), 2 warning(s), 0 info.
```

**Zero runtime dependencies.** The whole linter runs on the Python standard
library, so it works in any CI job that has `python` and nothing else.

## Install

```bash
pip install n8n-workflow-linter
```

Or run the latest without installing:

```bash
pipx run n8n-workflow-linter workflows/
```

## Quickstart

```bash
# Lint a directory (recurses into subfolders)
n8n-lint workflows/

# Lint a single file
n8n-lint workflows/cold_email.json

# Fail on warnings too, not just errors
n8n-lint workflows/ --strict

# See every rule
n8n-lint --list-rules
```

## The rules

| Rule | Default | What it catches |
|---|---|---|
| `real-credential-id` | **error** | A credential referencing an ID from a real n8n instance instead of a placeholder. These leak which credential a private instance used and break import for anyone else — credential IDs don't transfer between accounts. |
| `hardcoded-secret` | **error** | A live API key, token, or private key embedded anywhere in the file (OpenAI, Anthropic, AWS, Google, Slack, Stripe, Twilio, GitHub, JWTs, PEM blocks). Documented placeholders are ignored. |
| `hardcoded-resource-id` | warning | A hardcoded Google Drive/Sheets file ID or Gmail label ID baked into a node. Leaks which resource a real deployment used and breaks reuse. |
| `no-error-trigger` | warning | No active **Error Trigger** node — a workflow failure will alert nobody. |
| `missing-retry` | warning | An **HTTP Request** to an external service with `retryOnFail` off — a transient network error fails the whole run. |
| `orphan-node` | warning | A node connected to nothing on the canvas. It will never run, and usually means a wire got deleted. |
| `pinned-data` | warning | Pinned test data left in the export. It bloats the file and frequently contains real customer records. |
| `unauthenticated-webhook` | warning | A **Webhook** trigger with no authentication — anyone with the URL can fire it. |
| `disabled-node` | info | A disabled node left on the canvas. |

Every default is calibrated against real workflows to keep false positives near
zero. `real-credential-id` and `hardcoded-secret` are errors because they should
block a merge; the rest are advisory unless you opt into `--strict`.

## Use it in CI

### GitHub Actions

```yaml
name: lint-workflows
on: [push, pull_request]

jobs:
  n8n-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Redsf/n8n-workflow-linter@v1
        with:
          path: workflows/
          strict: "false"   # set "true" to fail on warnings
```

Findings appear as inline annotations on the pull request — the action emits
GitHub workflow commands, so each one is pinned to its file and line.

### pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Redsf/n8n-workflow-linter
    rev: v0.1.0
    hooks:
      - id: n8n-lint
        args: ["--strict"]
```

### Any other CI

It's a normal CLI with a meaningful exit code:

```bash
pip install n8n-workflow-linter
n8n-lint workflows/ --strict
```

## Configuration

Drop a `.n8nlintrc.json` in your repo root to change severities or turn rules
off. Every rule can be set to `error`, `warning`, `info`, or `off`:

```json
{
  "rules": {
    "disabled-node": "off",
    "hardcoded-resource-id": "error",
    "missing-retry": "warning"
  }
}
```

Point at a different file with `--config path/to/config.json`, or disable rules
ad hoc from the command line:

```bash
n8n-lint workflows/ --disable missing-retry --disable disabled-node
```

## Output formats

| `--format` | Use it for |
|---|---|
| `text` (default) | Humans. Colored when writing to a terminal; use `--no-color` to disable. |
| `github` | GitHub Actions. Emits `::error`/`::warning` workflow commands for inline PR annotations. |
| `json` | Scripting and dashboards. Stable schema: `{summary, findings[]}`. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | No blocking findings. (Warnings present but not `--strict`.) |
| `1` | At least one error — or any warning under `--strict`. |
| `2` | Usage error: bad config, unknown rule, or no workflow files found. |

## What it deliberately does not do

- **It does not validate against a live n8n instance.** It reads exported JSON
  statically, so it runs anywhere with no n8n and no network.
- **It does not check node-version deprecation.** That needs a per-node version
  database tracking the n8n release line, which would go stale between releases.
  Rules here are ones that can be checked correctly and offline. (On the
  roadmap, gated behind a bundled version manifest.)
- **It does not auto-fix.** Findings are reported, not rewritten — a linter that
  silently edits workflow JSON is a linter you can't trust in CI.

## Adding a rule

Rules are small and self-contained. Implement a `Rule` subclass in
[`src/n8n_linter/rules/`](src/n8n_linter/rules/), add an instance to `ALL_RULES`
in [`rules/__init__.py`](src/n8n_linter/rules/__init__.py), and add a
good/bad fixture pair under [`tests/fixtures/`](tests/fixtures/). The engine,
config system, and `--list-rules` all read from the registry, so nothing else
needs to change. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
