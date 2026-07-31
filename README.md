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
pip install git+https://github.com/Redsf/n8n-workflow-linter
```

> Not on PyPI yet, so install from git. The package builds a normal wheel
> (`python -m build`) if you'd rather vendor it. The GitHub Action below needs
> no install at all.

## Quickstart

```bash
# Lint a directory (recurses into subfolders)
n8n-lint workflows/

# Lint a single file
n8n-lint workflows/cold_email.json

# Explain every finding in plain language, with n8n fix steps
n8n-lint workflows/cold_email.json --explain

# Fail on warnings too, not just errors
n8n-lint workflows/ --strict

# See every rule
n8n-lint --list-rules
```

### `--explain` — for people who build in the n8n UI, not in JSON

The default output is a linter report: one terse line per finding. `--explain`
answers a different question — *is this safe to send to someone, and what do I
click to fix it?*

```
========================================================================
  Social Media AI Agent - Telegram.json
========================================================================

  SAFE TO SHARE — no passwords or API keys are inside this file.

  Nothing is leaking. But 4 thing(s) below will make this workflow
  fragile or confusing later. None of them stop it working today.

------------------------------------------------------------------------
  WORTH FIXING — these cause problems later
------------------------------------------------------------------------

  [~] 1. Nobody gets told when this workflow breaks

  Detail: no active Error Trigger — a workflow failure will not alert
  anyone

  What this means
    Right now, if this workflow fails at 3am, it fails quietly. No
    email, no message. You find out days later when you notice nothing
    has happened — or worse, a client notices first. ...

  How to fix it
    Build a tiny second workflow that does the shouting:
    1. New workflow in n8n → add node → search 'Error Trigger' → add it.
    ...
```

It leads with a verdict (`DO NOT SHARE THIS FILE YET` / `SAFE TO SHARE` /
`ALL CLEAR`), groups by rule so an explanation appears once no matter how many
nodes tripped it, and writes every fix as clicks in n8n rather than edits to
the JSON. Exit codes are unchanged, so it is safe in scripts.

## The rules

| Rule | Default | What it catches |
|---|---|---|
| `real-credential-id` | **error** | A credential referencing an ID from a real n8n instance instead of a placeholder. These leak which credential a private instance used and break import for anyone else — credential IDs don't transfer between accounts. |
| `hardcoded-secret` | **error** | A live API key, token, or private key embedded anywhere in the file (OpenAI, Anthropic, AWS, Google, Slack, Stripe, Twilio, GitHub, JWTs, PEM blocks). Documented placeholders are ignored. |
| `embedded-secret` | **error** | A credential-shaped value assigned inside a **Code** node or a header/query parameter. Where `hardcoded-secret` asks "does this look like an OpenAI key?", this asks "is a high-entropy value sitting in a field called `token`?" — so it catches internal and customer keys that match no known vendor format. |
| `credential-in-url` | **error** | An API key or token passed in a URL query string. Beyond sitting in the file, URLs get logged by the target service, by proxies, and by error trackers — into logs you cannot clean. |
| `hardcoded-resource-id` | warning | A hardcoded Google Drive/Sheets file ID or Gmail label ID baked into a node. Leaks which resource a real deployment used and breaks reuse. |
| `no-error-trigger` | warning | No active **Error Trigger** node — a workflow failure will alert nobody. |
| `missing-retry` | warning | An **HTTP Request** to an external service with `retryOnFail` off — a transient network error fails the whole run. |
| `missing-timeout` | warning | An **HTTP Request** with no timeout. n8n falls back to 5 minutes, so one hanging endpoint stalls the run — per item, inside a loop. |
| `error-output-swallowed` | warning | A node set to continue on the *normal* output when it fails, passing empty data downstream while the run still reports success. `continueErrorOutput` — a real error branch — is correctly ignored. |
| `orphan-node` | warning | A node connected to nothing on the canvas. It will never run, and usually means a wire got deleted. |
| `pinned-data` | warning | Pinned test data left in the export. It bloats the file and frequently contains real customer records. |
| `unauthenticated-webhook` | warning | A **Webhook** trigger with no authentication — anyone with the URL can fire it. |
| `default-node-names` | info | Three or more nodes still called `HTTP Request1`, `Code2`, `Edit Fields3`. Unreadable later, and it makes every error message useless. |
| `disabled-node` | info | A disabled node left on the canvas. |

Every default is calibrated against real workflows to keep false positives near
zero — see [Calibration](#calibration) for the measured rates. The five error
rules block a merge; the rest are advisory unless you opt into `--strict`.

## Calibration

A linter that cries wolf gets disabled, and then it protects nothing. Every rule
is measured against a corpus of 59 real published workflows before it ships:

| Rule | Files it fires on |
|---|---|
| `embedded-secret` | 0% |
| `credential-in-url` | 0% |
| `error-output-swallowed` | 15% |
| `default-node-names` | 20% |
| `missing-timeout` | 42% |

The bar for accepting a rule:

- An **error** rule firing on more than 5% of the corpus has every hit inspected
  by hand before release. Errors block merges, so they have to be right.
- A **warning** firing on more than two thirds of the corpus is an opinion, not a
  defect. It gets downgraded to info or cut.
- Rules are measured in isolation, one at a time, so a noisy rule cannot hide
  behind a quiet one.

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
pip install git+https://github.com/Redsf/n8n-workflow-linter
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
| `text` (default) | Humans reading a diff. Colored when writing to a terminal; use `--no-color` to disable. |
| `plain` | Humans who do not read JSON. Verdict first, then what each finding means and how to fix it in n8n. `--explain` is shorthand for this. |
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
