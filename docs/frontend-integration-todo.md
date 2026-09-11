# Frontend API integration backlog

Reviewed against the repository on 2026-09-11. Each numbered section can become
one GitHub epic; checkboxes are candidate child issues. All HTTP paths below are
relative to `/api/v1`. Priorities describe suggested implementation order.

## Already integrated

Login/logout, listing and creating homes, adding existing users to homes,
inventory create/list/edit/delete, notification inbox preview and unread counts,
marking notifications read, subscription CRUD, and WebSocket notifications exist.
These need regression coverage, not duplicate implementations. The WebSocket
client already has reconnect logic.

## Epic 1 — Registration and account activation (P1)

APIs: `POST /users/register`, `POST /users/activate/{key}`.

- [ ] Add a registration route and links from login/navigation.
- [ ] Submit username and email; handle duplicate accounts and validation errors.
- [ ] Add an activation screen accepting a key and password/confirmation.
- [ ] Match backend password validation and show invalid/expired key errors.
- [ ] Route successful activation to login; verify the new account can sign in.
- [ ] Test successful registration/activation and duplicate, expired-key, and
      password-mismatch cases.

Acceptance: a new user can complete account creation through the browser without
CLI or database access.

Backend update: registration now queues activation email and returns a status
message, not the key. `/activate?key=...` is implemented; a registration page and
resend flow remain outstanding. SMTP and the notification worker must be configured.

## Epic 2 — Current-user and session integration (P1)

API: `GET /users/me`.

- [ ] Load the authenticated user after login and on application startup.
- [ ] Replace token-presence-only authentication with a loading/validated session
      state; handle expired tokens without displaying protected screens.
- [ ] Show username/account information and use `is_admin` for admin navigation.
- [ ] Centralize authenticated requests and distinguish 401, 403, validation,
      network, and server errors. Clear stale credentials on authentication failure.
- [ ] Handle empty 204 responses and parse API errors once; the homes API helper
      currently attempts to read a response body again after JSON parsing.
- [ ] Test reload, expired token, permission denial, logout, and network failure.

Acceptance: session state survives valid reloads and invalid sessions return to
login with a clear message. Frontend role checks supplement backend authorization.

## Epic 3 — Home details and membership management (P1)

APIs: `GET /homes/{home_id}`, `DELETE /homes/{home_id}`,
`PATCH /homeuser/{home_id}/users/{user_id}`,
`DELETE /homeuser/{home_id}/users/{user_id}`.
Membership data is already available from `GET /homes/`.

- [ ] Add a home details/settings route with direct-link loading and not-found states.
- [ ] Add member role-change controls using the existing API role values.
- [ ] Add member removal with confirmation and refresh membership after success.
- [ ] Add home deletion with confirmation and clear stale selected-home state.
- [ ] Show actions appropriate to permissions and display backend rejections.
- [ ] Test owner/member/guest behavior, removal, deletion, and inaccessible homes.

Acceptance: authorized users manage home membership and deletion without API tools.
Adding an existing member is already implemented; this is not an email-invite flow.

## Epic 4 — Inventory pagination and filters (P1)

API: `GET /inventory/{home_id}` with `page`, `page_size`, `expiry`, `days`, and
repeated `category` parameters.

- [ ] Extend the API helper to accept server-side pagination and filters.
- [ ] Add page navigation using returned count/page metadata; reset the page when
      the home or filters change.
- [ ] Add expired/expiring-soon filters and the expiring-soon day window.
- [ ] Add category selection and preserve useful filter state in the URL.
- [ ] Handle loading, empty results, request failures, and stale response races.
- [ ] Test multiple pages, combined filters, and deletion of the last item on a page.

Acceptance: users can reach inventory beyond the first page and filter against
server results rather than only the items already loaded.

## Epic 5 — Correct notification subscription contracts (P1)

APIs: existing `/notifications/subscriptions` GET/POST/PATCH/DELETE routes.

- [ ] Replace frontend `inapp` with the API value `in_app` in types, defaults,
      options, and request payloads; test reading existing subscriptions too.
- [ ] Align offered channels with actual delivery support. The worker configures
      email, in-app, and log senders; SMS and push require backend delivery work.
- [ ] Support existing wildcard subscriptions such as `inventory.item.*` with
      readable labels and edit/toggle controls. They currently appear unsupported.
- [ ] Show actionable duplicate/validation/permission errors.
- [ ] Add browser/API contract tests for create, edit, disable, and delete for each
      supported channel/topic combination.

Acceptance: every selectable channel/topic produces a valid API request and users
can manage existing wildcard subscriptions. Do not imply that an accepted email
subscription guarantees delivery when SMTP is unavailable.

## Epic 6 — Full notification inbox and reconnect recovery (P2)

APIs: `GET /notifications/inbox`, `GET /notifications/unread-count`,
`PATCH /notifications/{notification_id}/read`; WebSocket `/notifications/ws`.

- [ ] Add an inbox route beyond the existing limited notification-bell preview.
- [ ] Connect home/unread filters and limit/offset pagination to the existing helper.
- [ ] Keep unread counts and read state consistent across the inbox and bell.
- [ ] Audit reconnect behavior and fetch missed persisted notifications after
      reconnect; avoid duplicate entries from overlapping HTTP/WS results.
- [ ] Show connection status and handle expired WebSocket authentication.
- [ ] Test incoming events, reconnect gaps, duplicate messages, and mark-read flows.

Acceptance: users can browse older notifications and recover missed updates after
a disconnection. Bulk “mark all read” is not an existing backend endpoint.

## Epic 7 — Admin users and homes screens (P2)

APIs: `GET /users/`, `GET /homes/admin/homes` (both paginated and admin-only).

- [ ] Add admin routes/navigation based on the validated current user (Epic 2).
- [ ] Integrate paginated user and home listings with loading/empty/error states.
- [ ] Show available membership/account information without inventing unsupported
      edit/delete operations.
- [ ] Test admin access, non-admin denial, direct navigation, and pagination.

Acceptance: admins can inspect the existing listing APIs through the frontend;
non-admin users cannot access their data.

## Epic 8 — Resolve unused event composer (P2, product/backend decision)

`frontend/src/components/AddEvent.tsx` and `frontend/src/api/events.ts` exist but
are not routed. The helper posts to `/notifications/events`, which has no matching
backend route.

- [ ] Decide whether manual notification creation is a supported product feature.
- [ ] If not, remove the unused form and API helper.
- [ ] If yes, specify recipients, permissions, validation, and delivery semantics;
      implement the backend endpoint before connecting a frontend route.
- [ ] Add authorization and end-to-end delivery tests if the feature is retained.

Acceptance: no frontend feature relies on a nonexistent API endpoint.

## Shared definition of done

- [ ] Add frontend tests for each new flow, including error and permission cases.
- [ ] Add a frontend test command and execute it in GitHub Actions; the existing
      workflow runs Python tests only.
- [ ] Verify production frontend build and same-origin API routing through Caddy.
- [ ] Verify WebSockets through Caddy for notification-related changes.
- [ ] Use isolated test accounts and an SMTP capture service for email tests.

## Separate backend work, not missing frontend wiring

Password reset/change, profile editing, activation email/resend, home renaming,
bulk mark-read, and delivery/outbox administration have no corresponding public
routes in the reviewed routers. Scope backend APIs first if these features are
wanted. SMTP configuration and expiry-job execution are server responsibilities;
frontend code should not connect directly to SMTP, RabbitMQ, or the database.
