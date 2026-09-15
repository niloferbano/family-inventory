# Backend TODO

## 1. Resend user activation link

- [ ] Add a resend endpoint accepting an email address.
- [ ] Support pending, inactive accounts; return a generic response for unknown or already-active accounts.
- [ ] Add a resend cooldown and rate limits to prevent email abuse.
- [ ] Generate a fresh activation token with an expiry and invalidate previous activation tokens.
- [ ] Queue the activation event through the existing outbox → RabbitMQ → notification worker → EmailSender flow.
- [ ] Use the configured `PUBLIC_BASE_URL` and the `/activate/{key}` frontend route.
- [ ] Test expired links, repeated requests, active/unknown accounts, delivery retries, and successful activation using the new link.

Acceptance: an inactive user whose activation link expired can request a replacement and activate without database or CLI intervention. Old links no longer work.

## 2. Password reset

- [ ] Add a password-reset request endpoint accepting an email address, with a generic response to avoid disclosing whether an account exists.
- [ ] Add request cooldowns and rate limits.
- [ ] Generate a secure, expiring reset token separate from activation and access tokens.
- [ ] Queue a clickable reset-link email through the existing notification pipeline.
- [ ] Add a reset-confirmation endpoint accepting the token, new password, and password confirmation.
- [ ] Apply password validation and store the new password using the existing password hashing service.
- [ ] Make token use single-use and concurrency-safe; a failed password-update transaction must remain retryable.
- [ ] Invalidate previous reset links and define how existing login sessions/access tokens are revoked after a reset.
- [ ] Keep account activation separate: password reset must not activate a pending account.
- [ ] Test unknown/inactive accounts, expiry, replay, concurrent attempts, mismatched passwords, delivery failures, and login with the new password.

Acceptance: an active user can recover access through email; the old password and used reset link no longer work. Coordinate the reset-link URL and payloads with frontend request/reset pages.
