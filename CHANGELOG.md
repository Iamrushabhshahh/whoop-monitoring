# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow SemVer.

## [Unreleased]

## [1.0.0] - 2026-10-13

### Added
- `WEBHOOK_PORT` to move the collector off 8080 when that port is taken.
- Community files: Code of Conduct, Support, Maintainers, issue and pull request templates,
  CODEOWNERS; README badges, screenshots and a "who this is for" section.
- ARCHITECTURE: OAuth and telemetry diagrams, and a plan-vs-as-built table.
- Package metadata (authors, URLs, classifiers).

### Changed
- Collector traces go to their own trace stream, `whoopmon_app`, instead of `default`.
- OpenObserve pinned to v1.0.4; the docs point to openobserve-playground for a local instance.

### Fixed
- `whoopmon_token_refresh_failed` failed on every run because it selected a column that did
  not exist.

## [0.1.0] - 2026-10-05

### Added
- OAuth login with refresh-token rotation and a cross-process lock.
- WHOOP v2 client: pagination, 429 handling, retries.
- Sync engine with watermarks, 72 h re-read and version de-duplication.
- OpenObserve sink and 5 health streams.
- structlog JSON logging, redaction, OTLP logs/metrics/traces to OpenObserve.
- Four dashboards and five alerts as code.
- Webhook receiver with HMAC verification.
- Docker image, compose profiles, Makefile, CI.
