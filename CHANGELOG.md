# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow SemVer.

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
