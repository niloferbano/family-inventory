POETRY = poetry
CLI = python -m family_cli.main

APP_MODULE = app.main:app
HOST = 0.0.0.0
PORT = 8000

.PHONY: run up down logs restart db-reset db-create db-drop test test-verbose lint format type-check clean prod help

run:
	$(POETRY) run $(CLI) run server

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose down
	docker compose up -d

db-reset:
	$(POETRY) run $(CLI) db reset

db-create:
	$(POETRY) run $(CLI) db create

db-drop:
	$(POETRY) run $(CLI) db drop

# ---------- TESTING ----------
test:
	$(POETRY) run pytest -q

test-verbose:
	$(POETRY) run pytest -vv

lint:
	$(POETRY) run ruff check .

format:
	$(POETRY) run ruff check --fix .
	$(POETRY) run black .
	$(POETRY) run isort .

type-check:
	$(POETRY) run mypy .

clean:
	@echo "🧹 Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete

prod:
	$(POETRY) run uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) --workers 4

help:
	@echo ""
	@echo "Available commands:"
	@awk -F':' '/^[a-zA-Z0-9_-]+:/ {print "  - " $$1}' Makefile
	@echo ""
install:
	poetry install --no-root