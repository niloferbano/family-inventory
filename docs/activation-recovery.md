# Activation recovery

POST `/api/v1/users/resend-activation` with `{"email":"user@example.com"}`.
The response is always a generic success for active, unknown, and throttled accounts.
Eligible inactive accounts receive a fresh activation email through the outbox worker.
Resends are limited per normalized email address using an atomic Redis cooldown
(default 60 seconds); suppressed requests do not enqueue email. Redis failures fail
closed. Request and enqueue audit events are logged without tokens or email addresses.

Activation links expire after `ACTIVATION_TOKEN_EXPIRE_MINUTES` (default 30).
The latest token hash is stored on the user row; older Redis tokens may remain until
TTL but are rejected after replacement. Invalid, expired, and reused links return 400.
Previously issued links without a database hash remain compatible until Redis TTL.

Apply migrations before starting the updated API and workers. Production includes
`user-cleanup`, which runs every `USER_CLEANUP_INTERVAL_SECONDS` (default 3600).
It deletes inactive accounts older than `UNACTIVATED_USER_RETENTION_DAYS` (default 7),
provided they have no unexpired activation link. Retention is measured from account
creation, not the last resend. Active accounts are never selected. Related records
follow existing database foreign-key rules; failures are logged and retried next run.

For local development run `python -m app.jobs.user_cleanup_job --loop`, or omit
`--loop` for a single cleanup. Add the settings from `.env.docker.example` to the
server's `.env.docker` to override defaults through Compose interpolation.
Cleanup deletes user records; back up the database before enabling it on an existing
installation and choose retention to match your account policy.

## Verification

Run `REQUIRE_TEST_DATABASE=true DEBUG=false poetry run pytest tests/unit/users -q`.
The integration checks require PostgreSQL and a dedicated test Redis. Set
`TEST_REDIS_URL` if Redis is not at `redis://localhost:6380/0`; GitHub Actions and
Docker test Compose supply their own addresses. Tests fail if Redis is unavailable.
They remove only their own Redis keys and close connections within each test loop.

Coverage includes real Redis expiry/cooldown, concurrent resend and activation,
API-to-outbox-to-worker email delivery with SMTP captured, audit log assertions,
and repeated cleanup with committed database deletions. The cleanup interval is
accelerated in tests. Live SMTP delivery and production container scheduling still
require deployment smoke checks; these tests do not send real emails.
