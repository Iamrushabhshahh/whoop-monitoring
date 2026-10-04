# Contributing

1. `make install` — creates `.venv` and installs pre-commit hooks.
2. Make the change. Add or update a test in `tests/unit/`.
3. `make check` — lint, format check, mypy and tests must pass.
4. New log events: follow [LOGGING.md](LOGGING.md) and add them to the event catalogue.
5. New dashboard panels: edit `src/whoopmon/provision/dashboards.py`, then `make provision`.
   The generated JSON in `openobserve/` is committed so reviewers can see the change.
6. Record a design change as a new ADR in `docs/adr/`.

Commit messages: imperative mood, max 72 characters in the first line.
