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
| `expensive-model-high-frequency` | warning | A frontier-tier model on a schedule firing more than hourly. Reports an estimated monthly cost, names cheaper models with the saving for each, and states every assumption it made. |
| `polling-trigger-cost` | warning | A schedule firing more often than every 5 minutes — most runs find nothing changed, and a webhook would be both cheaper and faster. |
| `default-node-names` | info | Three or more nodes still called `HTTP Request1`, `Code2`, `Edit Fields3`. Unreadable later, and it makes every error message useless. |
| `llm-cost-unbounded` | info | An LLM node with no `maxTokens`, so one unusually long reply has no cost ceiling. Info rather than warning — see [Calibration](#calibration). |
| `disabled-node` | info | A disabled node left on the canvas. |

### What the cost rules will and will not claim

They will tell you what a model costs, what the alternatives cost, and what the
difference would be at your trigger frequency. That is arithmetic.

They will **never** tell you a cheaper model is good enough for your task. A
linter has not seen your prompt or your data, and swapping a frontier model for
a small one is a change of product, not a configuration tweak. Suggestions step
down at most one capability tier, prefer the same vendor first (no new account,
no new credential), and end by pointing at an eval harness for the question the
linter cannot answer.

Every estimate prints the assumptions behind it — assumed token counts, runs per
month, and the date the price table was last checked. An estimate that hides its
inputs is the same trick as an ROI projection that hides its baseline.

Every default is calibrated against real workflows to keep false positives near
zero — see [Calibration](#calibration) for the measured rates. The five error
rules block a merge; the rest are advisory unless you opt into `--strict`.

## Calibration

A linter that cries wolf gets disabled, and then it protects nothing. Every rule
is measured against a corpus of 59 real published workflows before it ships:

| Rule | Files it fires on | Outcome |
|---|---|---|
| `embedded-secret` | 0% | shipped as error |
| `credential-in-url` | 0% | shipped as error |
| `expensive-model-high-frequency` | 0% | shipped as warning — never fired on the corpus |
| `polling-trigger-cost` | 0% | shipped as warning — never fired on the corpus |
| `error-output-swallowed` | 15% | shipped as warning |
| `default-node-names` | 20% | shipped as info |
| `missing-timeout` | 42% | shipped as warning |
| `llm-cost-unbounded` | **85%** | **downgraded to info** |

The bar for accepting a rule:

- An **error** rule firing on more than 5% of the corpus has every hit inspected
  by hand before release. Errors block merges, so they have to be right.
- A **warning** firing on more than two thirds of the corpus is an opinion, not a
  defect. It gets downgraded to info or cut.
- Rules are measured in isolation, one at a time, so a noisy rule cannot hide
  behind a quiet one.

Two results from the last pass worth stating plainly, because a calibration
section that only ever vindicates its author is decoration:

**`llm-cost-unbounded` failed the bar and was downgraded.** It fires on 85% of
the corpus, because n8n does not set a token cap by default. Flagging the default
state of almost every workflow as a warning is a preference, not a defect —
however defensible the preference. It ships as info; raise it in
`.n8nlintrc.json` if a runaway bill is a live concern for you.

**Two cost rules never fired at all.** 0% here means "no false positives" and
nothing more — the corpus happens to contain no frontier model on a fast
schedule. They are covered by fixtures, not by production evidence, and that is
a weaker claim than the 0% next to `embedded-secret`, which was measured against
workflows that do contain secrets-adjacent patterns.

Model coverage is measured too. Across the corpus, 66% of LLM nodes resolve to a
priced model; the remainder set no model parameter at all and inherit the node's
default, which cannot be priced from the file. An earlier pass sat at 28%, which
looked like "no expensive models found" and was actually a gap in the price
table — worth knowing that a quiet rule and a broken rule look identical from
the outside.

## Use it without installing anything

**[redsf.github.io/n8n-workflow-linter](https://redsf.github.io/n8n-workflow-linter)**

Drop a workflow export on the page and get the same 17 rules, the same verdict,
and the same plain-language explanations — no Python, no terminal. There is a
sample workflow on the page if you want to see what a report looks like before
finding a file of your own.

**Your workflow is never uploaded.** This is a tool for finding leaked
credentials; asking you to send the file containing those credentials to a server
would be a strange way to build it. The page runs the real Python package
compiled to WebAssembly, inside your own tab. Open your browser's Network tab and
drop a file in — no request fires.

The page is not a reimplementation. CI builds a wheel from this repo on every
push to `main` and the page installs it, so the two cannot drift: a rule added
here is live on the site without anyone editing JavaScript. Both front ends call
`n8n_linter.api.analyze`, which the test suite covers.

The CLI remains the right tool for CI, pre-commit, and scanning a whole folder.

```bash
bash scripts/build-web.sh   # build the wheel the page loads
python3 -m http.server -d web 8899
```

## The price table

`src/n8n_linter/pricing.py` carries per-model prices, capability tiers, and a
`LAST_VERIFIED` date. It is hand-maintained on purpose: fetching prices at
runtime would mean a network call from a tool whose promise is that it reads your
workflow offline and sends nothing anywhere.

Every row records where its number came from — `PRIMARY` for the vendor's own
pricing page, `AGGREGATE` for a third-party tracker. Aggregate figures are
labelled in the output, because they are usually right and occasionally months
behind, and nobody should quote one to a client without checking.

Every cost report prints the verification date. Once the table is more than 90
days old it says so in the output rather than continuing to sound confident. The
failure mode is designed to be "this might be stale", never a wrong number
stated well.

Updating it is a one-file pull request. Prices move monthly; corrections are
welcome.

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
