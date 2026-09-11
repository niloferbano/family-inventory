# Deployment

Run all commands from the repository root. The production entry point is
`deploy/docker-compose.prod.yml`; it combines infrastructure, API/workers, and
frontend/Caddy under the `family-inventory` project.

## 1. Prerequisites

- Docker Engine and the Docker Compose v2 plugin (`docker compose version`).
- A server with sufficient disk space for images, PostgreSQL, RabbitMQ, Redis,
  and backups. Build images for the server's CPU architecture.
- A domain whose DNS A record points to the server. If an AAAA record exists,
  it must also point to a reachable server address.
- Allow inbound TCP 80 and 443 for Caddy HTTP/HTTPS, and optionally UDP 443 for
  HTTP/3. Preserve your SSH access. Apply these rules to both the provider
  firewall and the host firewall. Do not expose PostgreSQL, RabbitMQ, or Redis
  publicly; production Compose publishes only Caddy's ports.
- Outbound access for image downloads, certificate issuance, and your SMTP
  provider. Ports 80 and 443 must not already be occupied by another proxy.

Caddy obtains certificates for `SITE_ADDRESS` and stores them in persistent
volumes. For a local HTTP-only check, use `SITE_ADDRESS=http://localhost`.

## 2. Environment variables

Create `.env` and `.env.docker` in the repository root. Both are ignored by Git.
Do not use `.env.docker.test` for production. No `.env.deploy` file is required.

`.env` supplies Compose interpolation values. Use separate random, URL-safe
secrets for PostgreSQL, RabbitMQ, and JWT signing (`openssl rand -hex 32` for each):

```dotenv
POSTGRES_USER=family_user
POSTGRES_PASSWORD=REPLACE_WITH_RANDOM_HEX
POSTGRES_DB=family_inventory
RABBITMQ_DEFAULT_USER=family_user
RABBITMQ_DEFAULT_PASS=REPLACE_WITH_DIFFERENT_RANDOM_HEX
JWT_SECRET_KEY=REPLACE_WITH_DIFFERENT_RANDOM_HEX
IMAGE_TAG=local
SITE_ADDRESS=inventory.niloferbano.com
EXPIRY_INTERVAL_SECONDS=3600
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=REPLACE_WITH_SMTP_USERNAME
SMTP_PASSWORD=REPLACE_WITH_SMTP_PASSWORD
SMTP_FROM_EMAIL=family.inventory.app@gmail.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

The three secrets are required. The hostname and SMTP values must match your
actual deployment/provider. For implicit SMTP TLS, typically use port 465,
`SMTP_USE_SSL=true`, and `SMTP_USE_TLS=false`, as instructed by your provider.
`localhost` inside the worker refers to that container, not the host machine.

`.env.docker` maps these values into container settings:

```dotenv
APP_ENV=production
DEBUG=false
RELOAD=false
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-family_user}:${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-family_inventory}
RABBITMQ_URL=amqp://${RABBITMQ_DEFAULT_USER:-family_user}:${RABBITMQ_DEFAULT_PASS:?Set RABBITMQ_DEFAULT_PASS}@rabbitmq:5672/
CACHE__HOST=redis
JWT_SECRET_KEY=${JWT_SECRET_KEY:?Set JWT_SECRET_KEY}
SMTP__HOST=${SMTP_HOST:-localhost}
SMTP__PORT=${SMTP_PORT:-587}
SMTP__USERNAME=${SMTP_USERNAME:-}
SMTP__PASSWORD=${SMTP_PASSWORD:-}
SMTP__FROM_EMAIL=${SMTP_FROM_EMAIL:-family.inventory.app@gmail.com}
SMTP__USE_TLS=${SMTP_USE_TLS:-true}
SMTP__USE_SSL=${SMTP_USE_SSL:-false}
EXPIRY_INTERVAL_SECONDS=${EXPIRY_INTERVAL_SECONDS:-3600}
POSTGRES_USER=${POSTGRES_USER:-family_user}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB:-family_inventory}
RABBITMQ_DEFAULT_USER=${RABBITMQ_DEFAULT_USER:-family_user}
RABBITMQ_DEFAULT_PASS=${RABBITMQ_DEFAULT_PASS:?Set RABBITMQ_DEFAULT_PASS}
```

```bash
chmod 600 .env .env.docker
```

Changing initialization credentials does not rotate credentials in existing
PostgreSQL or RabbitMQ volumes. Rotate those in the service itself before
changing the application's connection settings.

## 3. Deploy

Production uses prebuilt images; its Compose services contain no `build` blocks.
Build separately, or load images supplied by your release process. For the
`IMAGE_TAG=local` example above:

```bash
docker build --target runtime -f deploy/Dockerfile -t family-inventory:local .
docker build -f deploy/frontend.Dockerfile -t family-inventory-web:local .
```

For another release, replace `local` in both commands and in `.env` with the same
tag. If images are built elsewhere, transfer them with `docker save`/`docker load`
or pull and tag registry images with these expected names.

Validate without printing resolved credentials, then start:

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml config --quiet
docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d --no-build
```

The commonly used command below is also accepted, but **does not build these
images** because production Compose has no build definitions. The separate build
steps above are still required:

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d --build
```

`make deploy` runs the recommended `--no-build` command. PostgreSQL must become
healthy before migrations run. The API, worker, and expiry job wait for successful
migrations and healthy infrastructure; Caddy waits for the API health check.
All services share `family-inventory_backend`.

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml ps -a
docker compose --env-file .env -f deploy/docker-compose.prod.yml exec -T api \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

Visit `https://inventory.niloferbano.com` using your configured domain. The health
endpoint checks API responsiveness, not every downstream dependency.

## 4. View logs

```bash
make deploy-logs
# Or select services:
docker compose --env-file .env -f deploy/docker-compose.prod.yml \
  logs -f --tail=100 api worker inventory-expiry-cron web
# Inspect migration output:
docker compose --env-file .env -f deploy/docker-compose.prod.yml logs migrate
```

Treat logs as sensitive: application output may include connection details.

## 5. Run migrations manually

Migrations normally run automatically through the `migrate` service. Back up the
database before applying schema changes manually:

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d --wait postgres
docker compose --env-file .env -f deploy/docker-compose.prod.yml \
  run --rm --no-deps migrate alembic upgrade head
```

Check the applied revision with:

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml \
  run --rm --no-deps migrate alembic current
```

## 6. Update the application

1. Create a database backup using the command below.
2. Check out the desired release and build its backend/frontend images, or load
   the release images. Use a new release tag for both images.
3. Set `IMAGE_TAG` in `.env` to that tag and validate Compose.
4. Run `make deploy`. Compose starts the new images and runs migrations.
5. Check `ps -a`, migration logs, API health, and the frontend. Confirm worker and
   email delivery behavior if notification code changed.

For a frontend-only update, use `make deploy-frontend`; it also starts required
dependencies as needed. Production deployment never rebuilds images implicitly.
Keep the project name stable to reuse volumes. `make deploy-down` preserves data;
`down -v` deletes volumes and must not be used for a normal update.

## 7. Back up and restore PostgreSQL

Create a custom-format backup. Shell expansion of PostgreSQL variables happens
inside the container; the output file is written on the host:

```bash
mkdir -p backups
umask 077
docker compose --env-file .env -f deploy/docker-compose.prod.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > backups/family-inventory.dump
```

Use a unique filename for each backup, check the command succeeded, and keep
copies off the server. The example restore below accepts this custom-format
archive, not a plain SQL dump. Restore with the matching application release and
compatible PostgreSQL version; take a fresh backup of the destination first.

**Restoration replaces the destination database.** Stop application writers and
prevent incoming requests before proceeding. Also stop any external jobs or
clients that write to this database.

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml \
  stop web api worker inventory-expiry-cron migrate
docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d --wait postgres
# Check that the archive can be read before replacing the database:
docker compose --env-file .env -f deploy/docker-compose.prod.yml exec -T postgres \
  pg_restore --list < backups/family-inventory.dump
# Run these separately; stop if either fails:
docker compose --env-file .env -f deploy/docker-compose.prod.yml exec -T postgres \
  sh -c 'dropdb -U "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB"'
docker compose --env-file .env -f deploy/docker-compose.prod.yml exec -T postgres \
  sh -c 'createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose --env-file .env -f deploy/docker-compose.prod.yml exec -T postgres \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl --exit-on-error --single-transaction' \
  < backups/family-inventory.dump
```

Keep services stopped if restoration fails. After a successful restore, apply any
required migrations with the matching release image, then run `make deploy` and
verify health, login, inventory, and notifications.

This backup covers PostgreSQL only. RabbitMQ queues, Redis state, and Caddy
certificates live in separate volumes. Restoring an older database does not rewind
queued messages or cached state; reconcile those with the restored database before
restarting workers to avoid replaying notifications unintentionally.
