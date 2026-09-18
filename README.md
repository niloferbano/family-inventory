

# 📦 Family Inventory & Notification System

## 🧩 Problem Statement

The motivation behind this project stems from the difficulty in keeping track of and tidying products at home, which often leads to missed expiries and unnecessary waste. This system aims to solve these challenges by providing timely notifications and a streamlined inventory management experience.


A **production-grade, event-driven notification system** built around an inventory management domain.  
The system detects expiring inventory items and delivers notifications via **user-configurable channels**, including a **real-time in-app inbox**.

> This project demonstrates event-driven architecture, broker-managed retries, idempotency, distributed workers, and real-time delivery.

---

## 🚀 Features

### Inventory
- Homes with multiple users
- Inventory items with expiry dates
- Background job emits expiry events

### Notifications
- Topic-based subscriptions (e.g. `inventory.item.expired`)
- Per-user channel preferences
- Supported channels:
  - 🛎 **In-App Inbox (real-time)**
  - 📄 Log (pluggable)
  - 📧 Email (extensible)

### Reliability
- Outbox pattern for event publishing
- Broker-managed retries (RabbitMQ TTL + DLX)
- Dead-letter queue (DLQ)
- Idempotent event ingestion
- Distributed delivery claiming (safe for multiple workers)

### Real-Time
- WebSocket push for in-app notifications
- Redis Pub/Sub for multi-replica fan-out
- Read/unread state + badge count

---

## 🧱 Architecture Overview

```
Inventory Service
   │
   │ emits event
   ▼
Notification Outbox
   │
   │ publishes
   ▼
RabbitMQ (topic exchange + retry queues)
   │
   │ consume
   ▼
Notification Worker
   │
   │ deliver
   ▼
notification_inbox (Postgres)
   │
   │ push
   ▼
WebSocket / Redis → UI
```

---

inventory job → outbox row → (dispatcher) publish to RabbitMQ → notification worker consumes → ingest creates delivery rows → sender writes in_app_notifications


InventoryExpiryJob
  └─ writes NotificationOutbox (transactional)
  └─ best-effort publish

Outbox Sweeper
  └─ UPDATE ... RETURNING (claim)
  └─ publish
  └─ mark SENT / FAILED

Notification Worker
  └─ consumes broker events
  └─ creates NotificationDelivery rows
  └─ InAppSender writes inbox

## 🧠 Key Design Decisions

### Event-Driven + Outbox Pattern
- Inventory never talks to Notification directly
- Events are persisted first, then published
- Guarantees **no lost events**

### Broker-Managed Retries
- Failed messages are routed to TTL retry queues
- Automatic redelivery after delay
- Messages go to DLQ after max retries

### Idempotency
- `event_id` is the primary identifier everywhere
- Inbox uses `(user_id, event_id)` uniqueness
- Safe replays and retries

### Distributed Workers
- Delivery rows are **claimed with DB leases**
- `SELECT … FOR UPDATE SKIP LOCKED`
- Multiple workers can run safely

### Real-Time Fan-out
- Redis Pub/Sub decouples WebSocket layer
- WebSocket servers stay stateless

---

## 🛠 Tech Stack

- Python 3.12
- FastAPI
- PostgreSQL
- SQLAlchemy (async)
- RabbitMQ
- Redis
- WebSockets
- Docker & Docker Compose

---

## 🧪 Running Locally

```bash
make up
make db-upgrade
make run
make worker
make up-frontend
make run-frontend
```

---

## 🔔 Demo Flow

1. Create a home + user
2. Add an inventory item with an expired date
3. Inventory job emits `inventory.item.expired`
4. Notification worker processes event
5. In-app notification appears instantly
6. Badge count increments
7. Mark as read → badge updates

---

## 🔐 Security
- JWT-based authentication
- Home membership enforcement
- Inbox scoped per user

---

## ⚠️ Failure Scenarios & Guarantees

- RabbitMQ down at publish time (outbox + retry on reconnect)
- Worker crash mid-delivery (DB lease expires, another worker retries)
- Duplicate events (idempotent event_id handling)
- Notification channel failure (broker-managed retries, DLQ after max attempts)

---
## 💼 Resume Highlights

- Event-driven architecture with RabbitMQ
- Broker-managed retries & DLQ
- Distributed workers with DB-level locking
- Real-time WebSocket delivery with Redis
- Async Python with FastAPI & SQLAlchemy

---


## 🚧 Future Improvements
- Email/SMS providers
- Notification prioritization
- Tracing & metrics
- UI grouping & pagination
- add notification_templates table + admin endpoints + caching

---

## Cleanup

```bash
make remove-all <-- ⚠️ This will remove all the containers, networks, volumes, and images.
```

## Containers and Contabo deployment

Compose is split by responsibility:

| File | Purpose |
| --- | --- |
| `deploy/docker-compose.prod.yml` | Production entry point combining infrastructure, app, and frontend |
| `deploy/docker-compose.infra.yml` | Persistent PostgreSQL, RabbitMQ, and Redis; no host ports |
| `deploy/docker-compose.app.yml` | API, notification worker/sweeper, scheduled expiry job, migrations |
| `deploy/docker-compose.frontend.yml` | Frontend served by Caddy, HTTPS, and API/WebSocket proxy |
| `deploy/docker-compose.test.yml` | Isolated test runner, disposable PostgreSQL, and Redis |
| `deploy/docker-compose.yml` | Local infrastructure with loopback ports and a development mail catcher |

The production entry point extends the infrastructure, app, and frontend service definitions. The test file runs independently. The old RabbitMQ-only file is replaced by `deploy/docker-compose.infra.yml`.

### First deployment

On a Contabo Linux VPS with Docker Engine, the Docker Compose v2 plugin, Git, and Make installed:

1. Clone this repository and enter its directory.
2. Point your domain's DNS A record (and AAAA record if used) to the VPS. Allow inbound TCP 80/443 and your SSH port; UDP 443 is optional for HTTP/3.
3. Copy the deployment template:

   ```bash
   cp .env.example .env
   cp .env.docker.example .env.docker
   chmod 600 .env .env.docker
   ```

4. Edit `.env`. Set `SITE_ADDRESS` to your hostname and fill in `POSTGRES_PASSWORD`, `RABBITMQ_DEFAULT_PASS`, and `JWT_SECRET_KEY`. Generate a separate value for each with `openssl rand -hex 32`. Use URL-safe credentials (hex avoids URL escaping issues). Configure a real SMTP provider for email delivery.
5. Build images with tags matching `IMAGE_TAG`, then start (example uses `local`):

   ```bash
   docker build --target runtime -f deploy/Dockerfile -t family-inventory:local .
   docker build -f deploy/frontend.Dockerfile -t family-inventory-web:local .
   make deploy
   make deploy-logs
   ```

The equivalent Compose command is:

```bash
docker compose --env-file .env -p family-inventory \
  -f deploy/docker-compose.prod.yml up -d --no-build
```

Open `https://YOUR_DOMAIN`. Caddy serves the built React frontend and proxies API and WebSocket requests on the same origin. It provisions and renews certificates automatically when DNS and ports are configured ([Caddy HTTPS requirements](https://caddyserver.com/docs/automatic-https)). Only the web service publishes ports. Database, broker, Redis, and API are reachable within the Compose network.

Migrations must finish successfully before API/workers start, and infrastructure health checks gate startup ([Compose startup ordering](https://docs.docker.com/compose/how-tos/startup-order/)). The expiry job runs immediately and then every `EXPIRY_INTERVAL_SECONDS` (default 3600) after each run. The notification worker includes the outbox sweeper. Runtime Python containers run as an unprivileged user; `.env` files are excluded from image builds.

### Updates and operations

Build or load the desired backend and frontend images, set `IMAGE_TAG` to their release tag, and run `make deploy` to start them and apply migrations. Back up PostgreSQL before deploying schema changes. `make deploy-down` stops the deployment while preserving named data volumes. Keep the project name `family-inventory` stable so subsequent deployments reuse those volumes. Changing database or broker credentials in the env file does not rotate credentials already stored in an existing volume.

For infra only, use `make infra-up`. For an interactive admin command:

```bash
docker compose --env-file .env -p family-inventory \
  -f deploy/docker-compose.prod.yml \
  exec api python -m family_cli.main user create-admin
```

For a local full-stack smoke check without public DNS, set `SITE_ADDRESS=http://localhost` in a separate deployment env file and use the combined Compose command with that file. This uses plain HTTP locally.

### Container tests

Copy the isolated test environment file once, then run the tests:

```bash
cp .env.docker.test.example .env.docker.test
make test-docker
make test-docker-down
```

The first command builds the test image and returns pytest's exit status. The second removes test containers and volumes. Test PostgreSQL uses temporary storage and the separate `family-inventory-test` project; it does not connect to deployment infrastructure. No deployment secrets are required.

### Local host development

`make up` starts infrastructure only. Add `POSTGRES_PASSWORD=family_pass`, `RABBITMQ_DEFAULT_USER=guest`, and `RABBITMQ_DEFAULT_PASS=guest` to your local `.env` to match the Python development defaults, or configure matching `DATABASE_URL` and `RABBITMQ_URL` values. Then follow the local commands above. SMTP listens at localhost:8025 and the mail catcher UI at http://localhost:8026. Run `make inventory-expiry-job` when needed. Use the container test command for an isolated test database.

Existing local PostgreSQL and Redis named volumes retain their original names. Do not use `down -v` against a deployment whose data you want to keep.

Application containers load their settings from `.env.docker` (copy `.env.docker.example` first). Its credential placeholders resolve from `.env` locally or `--env-file .env` during deployment. Keep using the deployment env file for Compose settings such as infrastructure credentials and image tags.

### Deployment file layout

Dockerfiles and Compose files live in `deploy/`. Build contexts remain the repository root, where `.dockerignore` and the environment files stay. Run commands from the repository root. Use `make up` for local infrastructure and `make deploy` for the complete stack.

To deploy the prebuilt frontend/Caddy image, starting its dependencies as needed and waiting for a healthy API:

```bash
make deploy-frontend
```

Use the production entry point so Compose resolves all dependencies:

```bash
docker compose --env-file .env -p family-inventory \
  -f deploy/docker-compose.prod.yml up -d --no-build web
```

Keep the same project name so frontend and API share `family-inventory_backend` and existing Caddy certificate volumes. Caddy serves the built SPA and proxies `/api/*` (including WebSockets) to `api:8000`.

Production Compose uses prebuilt images only: `family-inventory:${IMAGE_TAG:-local}` and `family-inventory-web:${IMAGE_TAG:-local}`. Build them separately from the repository root before deployment (use the same tag in the deployment environment):

```bash
docker build --target runtime -f deploy/Dockerfile -t family-inventory:local .
docker build -f deploy/frontend.Dockerfile -t family-inventory-web:local .
```

For another host, transfer these images with `docker save` / `docker load`, or pull and tag your registry images before deployment. Test Compose continues to build its isolated test image.

See [the deployment guide](docs/deployment.md) for environment setup, updates, and database recovery.

### Local commit checks

Run `make install-hooks` once after cloning to enable the versioned Git hooks.
Each commit runs `poetry run mypy .` and stops if type checking fails. Install the
project dependencies with Poetry first. This checks the working tree, including
unstaged changes; CI also runs mypy independently.
