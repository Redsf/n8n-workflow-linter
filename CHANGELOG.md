# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-07-31

### Added

- **Cost rules.** Three rules that ask a question no other n8n linter asks: what
  will this workflow spend, and is that the cheapest way to get the job done.
  - `expensive-model-high-frequency` (warning) — a frontier-tier model on a
    schedule firing more than hourly. Reports an estimated monthly range, names
    cheaper models with the saving for each, and prints every assumption behind
    the number.
  - `polling-trigger-cost` (warning) — a schedule firing more often than every
    five minutes, where a webhook would be both cheaper and faster.
  - `llm-cost-unbounded` (info) — an LLM node with no `maxTokens`.
- `pricing.py` — per-model prices, capability tiers, and a `LAST_VERIFIED` date,
  covering OpenAI, Anthropic, Google, DeepSeek, Moonshot, Zhipu, MiniMax,
  Alibaba, xAI, Mistral and Groq-hosted open weights. Each row records whether
  its price came from the vendor's own page or a third-party tracker, and the
  distinction is surfaced in the output. Reports go stale loudly after 90 days
  rather than continuing to sound confident.
- `RuleHit.detail` — per-finding computed context, rendered by `--format plain`
  and omitted from the one-line formats.

### Changed

- Cost suggestions never claim a cheaper model is good enough for the task. They
  step down at most one capability tier, prefer the same vendor first (no new
  account or credential to add), and route the quality question to an eval
  harness.

### Calibration

Measured against 59 published workflows, one rule at a time:

- `expensive-model-high-frequency` 0%, `polling-trigger-cost` 0% — no false
  positives, but the corpus contains no case that triggers them, so these are
  covered by fixtures rather than production evidence.
- `llm-cost-unbounded` 85% — **failed the documented bar and was downgraded from
  warning to info.** n8n sets no token cap by default, so flagging it as a
  warning describes a preference rather than a defect.
- Price-table coverage across the corpus is 66% of LLM nodes; the rest set no
  model parameter and inherit the node default, which a file cannot reveal. An
  earlier pass measured 28% and looked like a clean result — it was a gap in the
  table, not an absence of expensive models.

## [0.1.1] — 2026-07-30

### Added

- Five new rules, taking the set from 9 to 14:
  - `embedded-secret` (error) — entropy-based detection of credentials assigned
    inside Code nodes or header/query parameters. Complements `hardcoded-secret`,
    which only recognises known vendor key formats and therefore misses internal
    and customer keys.
  - `credential-in-url` (error) — an API key passed in a URL query string, where
    it ends up in logs nobody can clean.
  - `missing-timeout` (warning) — an HTTP Request with no timeout, falling back
    to n8n's 5-minute default.
  - `error-output-swallowed` (warning) — a node continuing on its normal output
    after a failure, so the run reports success while passing empty data on.
    `continueErrorOutput` is correctly treated as the good setting.
  - `default-node-names` (info) — three or more nodes still named `Code2`,
    `HTTP Request1`.
- `shannon_entropy` helper, used to separate real credentials from placeholders
  sitting in credential-shaped fields.
- A documented calibration bar in the README, with measured false-positive rates
  for every new rule against a 59-workflow corpus.

- `--format plain` (and its shorthand `--explain`): a non-technical report that
  leads with a share/do-not-share verdict, explains what each finding actually
  means, and gives the fix as steps to click in the n8n UI rather than edits to
  the JSON. Findings are grouped by rule, so an explanation appears once however
  many nodes tripped it.
- Every rule now carries `plain_title`, `plain_meaning`, and `plain_fix` copy,
  enforced by a test so a new rule cannot ship without them.

## [0.1.0] — 2026-07-24

Initial release.

### Added

- Nine rules across three categories: security (`real-credential-id`,
  `hardcoded-secret`, `hardcoded-resource-id`), reliability (`no-error-trigger`,
  `missing-retry`, `orphan-node`), and hygiene (`pinned-data`,
  `unauthenticated-webhook`, `disabled-node`).
- `n8n-lint` CLI with `text`, `github`, and `json` output formats.
- Per-rule severity configuration via `.n8nlintrc.json` and `--disable`.
- `--strict` mode to fail CI on warnings.
- Composite GitHub Action and a pre-commit hook.
- Zero runtime dependencies — standard library only.
