SHELL := /bin/bash
VENV  := .venv
BIN   := $(VENV)/bin
SINCE ?= 2023-01-01

.DEFAULT_GOAL := help
.PHONY: help install lint fmt typecheck test test-integration check login status doctor sync backfill provision \
        up down logs serve tunnel clean

help: ## Show targets
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

$(BIN)/whoopmon:
	python3 -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -e '.[dev]'

install: $(BIN)/whoopmon ## Create .venv and install with dev tools
	$(BIN)/pre-commit install >/dev/null 2>&1 || true

lint: install ## Ruff lint + format check
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

fmt: install ## Auto-format
	$(BIN)/ruff check --fix src tests
	$(BIN)/ruff format src tests

typecheck: install ## mypy
	$(BIN)/mypy src

test: install ## Unit tests
	$(BIN)/pytest -q -p no:logging

test-integration: install ## Run every dashboard/alert query against the local OpenObserve
	$(BIN)/pytest -q -p no:logging -m integration

check: lint typecheck test ## Everything CI runs

login: install ## One-time WHOOP login in your browser
	LOG_FORMAT=console $(BIN)/whoopmon auth login

status: install ## Token state and connected user
	LOG_FORMAT=console $(BIN)/whoopmon auth status

doctor: install ## Check WHOOP + OpenObserve connectivity
	LOG_FORMAT=console $(BIN)/whoopmon doctor

sync: install ## One incremental sync from the host
	LOG_FORMAT=console $(BIN)/whoopmon sync

backfill: install ## Load history: make backfill SINCE=2024-01-01
	LOG_FORMAT=console $(BIN)/whoopmon backfill --since $(SINCE)

provision: install ## Create dashboards (and alerts if ALERT_WEBHOOK_URL is set)
	LOG_FORMAT=console $(BIN)/whoopmon provision

up: ## Start the collector container
	docker compose up -d --build collector

down: ## Stop all containers
	docker compose --profile webhook --profile o2 down

logs: ## Follow collector logs
	docker compose logs -f collector

serve: install ## Run the webhook receiver on the host (:8080)
	LOG_FORMAT=console $(BIN)/whoopmon serve --no-with-scheduler

tunnel: ## Start a cloudflared tunnel to the collector; prints the public URL
	docker compose --profile webhook up -d tunnel
	@sleep 5; docker compose logs tunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1

clean: ## Remove caches (keeps data/ and .env)
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist src/*.egg-info
