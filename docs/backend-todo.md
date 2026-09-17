# Backend TODO

## 1. Resend user activation link

- [x ] Add a resend endpoint accepting an email address.
- [x ] Support pending, inactive accounts; return a generic response for unknown or already-active accounts.
- [ x] Add a resend cooldown and rate limits to prevent email abuse.
- [ x] Generate a fresh activation token with an expiry and invalidate previous activation tokens.
- [x ] Queue the activation event through the existing outbox → RabbitMQ → notification worker → EmailSender flow.
- [x ] Use the configured `PUBLIC_BASE_URL` and the `/activate/{key}` frontend route.
- [ x] Test expired links, repeated requests, active/unknown accounts, delivery retries, and successful activation using the new link.

Acceptance: an inactive user whose activation link expired can request a replacement and activate without database or CLI intervention. Old links no longer work.

## 2. Password reset

- [ x] Add a password-reset request endpoint accepting an email address, with a generic response to avoid disclosing whether an account exists.
- [x ] Add request cooldowns and rate limits.
- [x ] Generate a secure, expiring reset token separate from activation and access tokens.
- [ x] Queue a clickable reset-link email through the existing notification pipeline.
- [x ] Add a reset-confirmation endpoint accepting the token, new password, and password confirmation.
- [ x] Apply password validation and store the new password using the existing password hashing service.
- [ x] Make token use single-use and concurrency-safe; a failed password-update transaction must remain retryable.
- [x ] Invalidate previous reset links and define how existing login sessions/access tokens are revoked after a reset.
- [x ] Keep account activation separate: password reset must not activate a pending account.
- [x ] Test unknown/inactive accounts, expiry, replay, concurrent attempts, mismatched passwords, delivery failures, and login with the new password.

Acceptance: an active user can recover access through email; the old password and used reset link no longer work. Coordinate the reset-link URL and payloads with frontend request/reset pages.

## 3. Enforce lint and type checks in CI

- [x] Fix the three existing mypy errors in notification ingestion, activation-token validation, and password-hash assignment.
- [x] Add Ruff and mypy jobs to `.github/workflows/code-quality.yml`, using the existing Poetry dependencies.
- [x] Run `poetry run ruff check .` and `poetry run mypy .` alongside pytest and coverage.
- [x] Ensure lint/type failures prevent production deployment by requiring successful `tests` and `Code Quality` runs for the same commit.
- [ ] Configure GitHub branch protection to require `ruff`, `mypy`, and `pytest` before merging.

Acceptance: lint or type errors fail CI, and production deployment proceeds only when lint, type checks, and tests all pass.
