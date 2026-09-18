POETRY = poetry
CLI = python -m family_cli.main

APP_MODULE = app.main:app
HOST = 0.0.0.0
PORT = 8000
FRONTEND_DIR = frontend

.PHONY: \
	run up down logs restart \
	db-reset db-create db-drop db-migrate db-upgrade db-downgrade db-current db-history \
	worker inventory-expiry-job \
	test test-verbose lint format type-check install-hooks clean prod help install create-admin

# ---------- APP ----------
run:
	$(POETRY) run $(CLI) run server

prod:
	$(POETRY) run uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) --workers 4

# ---------- DOCKER ----------
LOCAL_COMPOSE = docker compose --env-file .env -f deploy/docker-compose.yml
up:
	$(LOCAL_COMPOSE) up -d

down:
	$(LOCAL_COMPOSE) down

remove-all:
	$(LOCAL_COMPOSE) down -v --remove-orphans

logs:
	$(LOCAL_COMPOSE) logs -f

restart:
	$(LOCAL_COMPOSE) down
	$(LOCAL_COMPOSE) up -d

# ---------- DATABASE (CLI WRAPPED) ----------
db-reset:
	@test "$(ENV)" = "dev" || (echo "db-reset only allowed in dev"; exit 1)
	$(POETRY) run $(CLI) db reset

db-create:
	$(POETRY) run $(CLI) db create

db-drop:
	$(POETRY) run $(CLI) db drop

# ---------- DATABASE (ALEMBIC DIRECT) ----------
# Usage: make db-migrate msg="add notification locks"
db-migrate:
	$(POETRY) run alembic revision --autogenerate -m "$(msg)"

db-upgrade:
	$(POETRY) run alembic upgrade head

db-downgrade:
	$(POETRY) run alembic downgrade -1

db-current:
	$(POETRY) run alembic current

db-history:
	$(POETRY) run alembic history

# ---------- WORKERS / JOBS ----------
worker:
	$(POETRY) run python -m app.apis.notifications.worker

inventory-expiry-job:
	$(POETRY) run python -m app.jobs.inventory_expiry_job

# ---------- USERS ----------
create-admin:
	$(POETRY) run $(CLI) user create-admin

# ---------- TESTING ----------
test:
	PYTHONPATH=. $(POETRY) run pytest -q

test-verbose:
	PYTHONPATH=. $(POETRY) run pytest -vv

# ---------- QUALITY ----------
lint:
	$(POETRY) run ruff check .

format:
	$(POETRY) run ruff check --fix .
	$(POETRY) run isort .
	$(POETRY) run black .

type-check:
	$(POETRY) run mypy .

install-hooks:
	chmod +x .githooks/pre-commit
	git config --local core.hooksPath .githooks

# ---------- MAINTENANCE ----------
clean:
	@echo "🧹 Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete

install:
	$(POETRY) install --no-root

help:
	@echo ""
	@echo "Available commands:"
	@awk -F':' '/^[a-zA-Z0-9_-]+:/ {print "  - " $$1}' Makefile
	@echo ""

# ---------- Frontend ----------
audit-frontend:
	npm audit --prefix $(FRONTEND_DIR)

up-frontend:
	npm install --prefix $(FRONTEND_DIR)

ci-up-frontend:
	npm ci --prefix $(FRONTEND_DIR)

run-frontend:
	npm run dev --prefix $(FRONTEND_DIR)

# ---------- CONTAINER DEPLOYMENT ----------
DEPLOY = docker compose --env-file .env -p family-inventory -f deploy/docker-compose.prod.yml
TEST_COMPOSE = docker compose -p family-inventory-test -f deploy/docker-compose.test.yml

.PHONY: deploy deploy-down deploy-logs infra-up test-docker test-docker-down
deploy:
	$(DEPLOY) up -d --no-build

deploy-down:
	$(DEPLOY) down

deploy-logs:
	$(DEPLOY) logs -f --tail=100

infra-up:
	$(DEPLOY) up -d postgres rabbitmq redis

test-docker:
	$(TEST_COMPOSE) up --build --abort-on-container-exit --exit-code-from test

test-docker-down:
	$(TEST_COMPOSE) down -v

.PHONY: deploy-frontend
deploy-frontend:
	$(DEPLOY) up -d --no-build web
