# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
