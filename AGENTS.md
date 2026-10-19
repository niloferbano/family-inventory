# Repository Guidelines

See [docs/architecture.md](docs/architecture.md) for the application's components, data flows, and deployment architecture.

## Project Structure & Module Organization
- `app/` is the FastAPI backend, organized **domain-per-package** under `app/apis/<domain>/`: typically `models.py`, `exceptions.py`, `schema.py`/`schemas.py`, `repository.py`, `service.py`, `router.py`. Not every domain has all six files — e.g. `household_categories/` has no `router.py` of its own; its create/rename/delete endpoints are exposed through `homes/router.py` (`POST /homes/{id}/categories`) and `homes/settings.py`, and it's read from `inventory/router.py`. Check whether a domain's endpoints already live in a *different* router before adding a new one.
  - `app/iam/` — auth/JWT (`token_service.py`), permissions (`PermissionsValidator`), and `websocket_auth.py` (WS auth accepts `Authorization: Bearer` **or** a `?token=` query param, since browser/React-Native `WebSocket` clients can't set custom headers).
  - `app/core/` — settings (`configs/config.py`, uses `env_nested_delimiter="__"`), DB session/pagination, the domain error hierarchy (`database/exceptions.py`, `database/error_codes.py`), the centralized `exception_handlers.py`, and Prometheus metrics (`monitoring.py`).
  - `app/integrations/` — external API clients (e.g. `product_catalog/open_food_facts.py`).
  - `app/jobs/` — scheduled jobs (e.g. `inventory_expiry_job.py`).
- `frontend/` — Vite + React 19 + TypeScript SPA, PWA-enabled (`vite-plugin-pwa` wired in `vite.config.mjs`; manifest/icons under `public/`). `src/api/*.ts` mirrors the backend routers 1:1, one file per domain.
- `tests/unit/` groups backend tests by domain; `tests/conftest.py` supplies shared fixtures.
- `alembic/versions/` holds database migrations. `family_cli/` provides management commands; `deploy/` contains Docker configuration; `docs/` contains operational guides.

When a backend schema or endpoint changes, keep `frontend/src/api/`, FastAPI response models, and API tests consistent with the updated contract.

## Build, Test, and Development Commands
Use Python 3.12, matching CI, and Poetry for backend dependencies.
- `make install`: install Python dependencies.
- `make up`: start local Docker services using `.env`.
- `make db-upgrade`: apply migrations; `make db-migrate msg="describe change"` generates a migration for review.
- `make run`: start the API; `make worker`: start the notification worker.
- `make up-frontend` and `make run-frontend`: install frontend dependencies and start Vite. `npm run dev --prefix frontend` also serves a dev-mode service worker (`devOptions.enabled: true` in `vite.config.mjs`), so the PWA install prompt can be tested without a full build.
- `npm run build --prefix frontend`: build frontend production assets.
- `make test`: run pytest; `make test-docker`: build and run containerized tests.
- `make lint`, `make format`, and `make type-check`: run Ruff, apply Ruff fixes/isort/Black formatting, and run mypy respectively.

## Coding Style & Naming Conventions
- Python: four-space indentation, snake_case functions/modules, PascalCase classes, type annotations compatible with mypy (`ignore_missing_imports = true`). Follow Black formatting and isort's Black profile. Most existing modules open with `from __future__ import annotations` (PEP 563) — this predates the project's actual Python floor (`>=3.10`, which supports `X | None` natively) but is the established convention; match it in new domain files rather than dropping it.
- Pydantic v2 throughout: `field_validator`/`model_validator`, `Annotated[...] + AfterValidator` for path/query param normalization (see the barcode validator in `app/apis/product/router.py`), `ConfigDict(from_attributes=True, extra="forbid")`, and shared `Literal` types imported from the module that defines them rather than redeclared elsewhere (e.g. `LookupSource` is defined in `product/service.py` and imported into `product/router.py`).
- Domain errors: raise `DomainNotFoundError` / `DomainConflictError` / `DomainPermissionError` (subclasses of `DomainError` in `app/core/database/exceptions.py`) with an `ErrorCode` from `app/core/database/error_codes.py`. Don't raise a bare `HTTPException` from inside a service — `app/core/exception_handlers.py` is what translates domain errors into HTTP responses. Add new error codes to the shared `ErrorCode` StrEnum instead of inlining strings.
- Permission checks: use `HomeUserRepository` membership lookups and preserve the authorization rules for each operation. Managing home settings and categories requires membership in that specific home and either its owner role or the global `User.is_admin` flag. Global admin status alone does not bypass the membership requirement for these operations. There is no home-level "admin" role; only `UserType.OWNER | RESIDENCE | GUEST`.
- Idempotent writes: use `on_conflict_do_nothing(constraint=...)` for upsert-by-unique-constraint (see `ProductRepository.find_or_create_by_barcode` and `HouseholdCategoryRepository.create`).
- Resource lifecycle: FastAPI lifespan initializes application resources on startup and closes them on shutdown. Storing resources on `app.state` is valid and is used for Redis and the notification publisher in `app/main.py`. The product catalog client uses lazy module-level initialization with explicit cleanup via `get_catalog_client`/`close_catalog_client` in `app/apis/product/router.py`. Preserve initialization and cleanup for whichever pattern a resource uses.
- Metrics: Prometheus `Counter`/`Gauge`/`Histogram` names follow `<domain>_<component>_<metric>_total|_seconds`, with labels like `["status", "topic"]` (see `app/core/monitoring.py`).
- TypeScript: match existing formatting, generally two-space indentation; PascalCase component filenames, camelCase functions. Before adding a new `frontend/src/api/*.ts` call, check the actual FastAPI route signature — e.g. a `list[UUID] | None = Query(default=None)` filter needs repeated query params (`?key=a&key=b`), not a comma-joined string.

## Testing Guidelines
Use pytest, pytest-asyncio, and HTTPX fixtures; name files `test_*.py`. Add regression tests alongside the relevant domain tests. Configure `TEST_DATABASE_URL` for a dedicated PostgreSQL database and Redis where needed. Set `REQUIRE_TEST_DATABASE=true` to fail instead of skipping when PostgreSQL is unavailable. CI collects branch coverage for `app` and `family_cli`; no minimum percentage is configured. No frontend test script is currently defined.
The current HTTPX `ASGITransport` test fixture does not run application lifespan. Tests that need startup resources must initialize them explicitly or run lifespan, and must close any resources they create. For tests using lazy module-level async clients, use fixtures to close/reset those clients between tests to prevent shared state and connections from leaking across tests.

## Commit & Pull Request Guidelines
History uses short, action-oriented subjects such as `add api to create categories`; no strict prefix convention is evident. Reference related issues. PRs should describe behavior changes, validation performed, and migration/configuration impacts; include screenshots for UI changes. Ensure pytest, Ruff, and mypy checks pass.

## Security & Configuration
Use the provided `.env*.example` templates. Keep credentials out of commits and use isolated test services. Preserve household authorization checks and notification idempotency when modifying these flows. WebSocket auth accepts a `?token=` query-param fallback for clients that can't set custom headers (see above) — treat it with the same care as the `Authorization` header path, and don't log full WebSocket connection URLs.

## WebSocket Guidelines

Apply these requirements when adding or changing WebSocket behavior; this is not a claim that every safeguard is already implemented.

- Authenticate connections using the shared WebSocket authentication helper. Restrict user-specific events to the authenticated user, and verify membership in the specific home before subscribing to home-specific events. Do not trust client-supplied user or home IDs as authorization.
- Never log authentication tokens, authorization headers, or connection URLs containing tokens. Preserve this rule in application and proxy logging.
- On disconnect, release subscriptions, cancel and await connection-owned background tasks, and close connection-owned resources without closing clients shared with other connections.
- Clients should reconnect with bounded exponential backoff and refresh relevant data after reconnecting because events may have been missed. Stop reconnecting on logout or component unmount; authentication failures require valid credentials before retrying.
- Test unauthenticated access, unauthorized user/home subscriptions, disconnect cleanup, and client reconnection behavior when changing these flows. Record any unimplemented requirements as explicit follow-ups.
