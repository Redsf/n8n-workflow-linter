# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

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
