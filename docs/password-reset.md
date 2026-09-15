# Password reset API

## Request a reset

`POST /api/v1/users/password-reset/request`

```json
{"email":"user@example.com"}
```

Returns HTTP 200 with the same message for existing, unknown, or inactive accounts:

```json
{"message":"If an eligible account exists, a password reset email will be sent."}
```

Active accounts receive an email via the transactional outbox, RabbitMQ, and
notification worker. Inactive accounts must complete activation first. A successful
request means the email is queued, not that the SMTP provider has delivered it.

## Confirm the reset

`POST /api/v1/users/password-reset/confirm`

```json
{"token":"TOKEN_FROM_EMAIL","password":"NewPassword1","confirm_password":"NewPassword1"}
```

Returns HTTP 200 after committing the new password and invalidating the token.
Invalid, expired, superseded, or reused tokens return HTTP 400 with the same error.
Password validation failures return HTTP 422 without consuming the token.
Passwords use the existing policy (at least six characters and a number), with a
72-byte maximum to avoid bcrypt truncation.

Tokens contain 32 random bytes, expire after `PASSWORD_RESET_EXPIRE_MINUTES`
(default 30), and are validated against a SHA-256 hash stored on the user row.
The new password and cleared reset state commit together. Row locking serializes
confirmation and requests, preventing concurrent token reuse. Each request replaces
the previous token; older emails may still arrive but their links no longer work.
The raw link is retained in notification/outbox email content for asynchronous delivery;
restrict access to those records and backups. Logs contain request/completion/rejection
event names, never emails, passwords, or reset tokens.

## Setup and integration

- Run `make db-upgrade` before restarting a local API/worker. The migration adds two
  nullable user columns and a unique reset-hash constraint.
- Restart both local processes after updating the code (`make run`, `make worker`).
- The default worker bindings include `users.password_reset.requested`. If
  `NOTIFICATION_BINDINGS` is overridden, append this topic to the existing bindings.
- Configure SMTP as for activation email.
- Set `PUBLIC_BASE_URL` to the frontend origin. Email links use
  `/reset-password/{token}`; a frontend screen for this route must submit the token
  and new password to the confirmation endpoint. This backend ticket does not add
  that screen or a forgot-password form.
- An optional expiry override must reach the API's environment (for Docker, add it
  to `.env.docker` as well as the corresponding Compose interpolation source).

Existing access JWTs are not revoked by this change; they retain their current expiry.
Password-reset rate limits and session revocation are separate follow-up work.

Tests use an isolated PostgreSQL database and mocked SMTP/RabbitMQ boundaries,
including delivery through the real notification consumer and EmailSender.
