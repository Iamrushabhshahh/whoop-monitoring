# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow SemVer.

## [Unreleased]

### Added
- WHOOP · Overview dashboard: latest scored recovery, HRV, resting HR and main sleep, 7-day
  averages, daily trends and a last-7-days table. `make provision` now creates 5 dashboards.

### Changed
- Strain & Training: Sport mix sits beside the heart-rate zones, and Recent workouts spans the
  full width.

## [1.0.1] - 2026-10-13

### Fixed
- Type the metric attributes in the WHOOP client so mypy passes with OpenTelemetry 1.45.

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
