# backend

Django + DRF API for UpChatz, managed with **uv** (Python 3.12). PostgreSQL, Redis, Celery (+ Beat with the database scheduler) and Django Channels. Setup steps are in the [root README](../README.md#backend).

## Layout

- `config/` — the Django project package.
  - `settings/`: `base.py`, `dev.py` (the default), `test.py` and `prod.py`.
  - `urls.py` mounts every app once. It also serves `/healthz/`, `/readyz/`, `/api/schema/` and `/api/docs/`.
  - `celery.py` merges beat entries from each app's `schedules.py`.
  - `routing.py` collects WebSocket routes from each app's `routing.py`.
  - `asgi.py` / `wsgi.py` are the server entry points.
- `common/` — code shared by every app. Apps may import it; apps don't import each other.
  - `models.py`: `UUIDTimeStampedModel` and `TenantScopedModel` (UUID pk, `workspace` FK).
  - `tenancy.py`: workspace resolution and role permissions for API views.
  - `roles.py`: owner > admin > agent > viewer.
  - `exceptions.py`: the error envelope.
  - `pagination.py`: cursor pagination on `created_at`.
  - `crypto.py` / `fields.py`: Fernet encryption and `EncryptedTextField` for stored secrets.
  - `phone.py`: E.164 normalization and WhatsApp ids.
  - `events.py`: dataclasses and signals for cross-app events.
  - `testing.py`: test helpers.
- `apps/` — one Django app per domain: accounts, tenants, whatsapp, message_templates, contacts, campaigns, inbox, automations, webhooks, billing, analytics, developer_api. Tests live in each app's `tests/`.

## Conventions

- **Workspace header.** Tenant-owned endpoints read the workspace from the `X-Workspace-ID` header.
  - Views use `common.tenancy.WorkspaceScopedMixin`, or `WorkspaceScopedViewSet` / `WorkspaceScopedGenericViewSet` / `WorkspaceScopedAPIView`.
  - Set `read_role`, `write_role` and optionally `action_roles`.
  - Querysets are filtered to the workspace, and created objects get it set.
  - A missing header is a 400. A non-member gets a 404, and a member with too low a role gets a 403.
  - When composing DRF mixins with `WorkspaceScopedGenericViewSet`, list the scoped base first. Otherwise `CreateModelMixin.perform_create` shadows the one that sets the workspace.
- **Errors.** Every API error is `{"error": {"code", "message", "details"}}`.
- **Secrets.** Meta tokens and PINs use `EncryptedTextField`. They are never serialized or logged. `TOKEN_ENCRYPTION_KEYS` holds Fernet keys: the first key encrypts, and all keys decrypt.
- **Meta Graph API.** Access goes only through `apps.whatsapp.client.get_client()`. Tests use the `fake_graph` fixture and never hit the network.
- **Optional per-app modules.** These are discovered automatically:
  - `receivers.py` holds signal receivers. It is imported by `common.apps.BaseAppConfig`, and receivers must be idempotent.
  - `schedules.py` defines `BEAT_SCHEDULE = {...}`. Entry names must be unique across apps. Keep it import-light: no models.
  - `routing.py` defines `websocket_urlpatterns = [...]`.
  - `schema_enums.py` defines `ENUM_NAME_OVERRIDES = {...}` for drf-spectacular enum names.
  - `factories.py` holds factory_boy model factories.
- **Celery task names** are explicit: `"<app>.<verb_noun>"`.

## Tests and checks

Run from `backend/` with Postgres from `infra/docker/compose.dev.yml` running (host port 5433):

```bash
uv run pytest                      # add --create-db after migration changes
uv run pytest common config        # foundation tests only
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
DJANGO_SETTINGS_MODULE=config.settings.test uv run python manage.py spectacular --validate --fail-on-warn --file openapi.yml
```

- `openapi.yml` is committed. After any API change, regenerate it with the command above (LF line endings), commit it, then run `npm run api:types` in `frontend/`. CI regenerates it and fails if `git diff --exit-code -- openapi.yml` finds a difference.
- Cross-app flows (signed Meta and Razorpay webhooks through receivers, the realtime socket) are tested in `tests/`.

- Tests use `config.settings.test`, which needs no `.env`. It uses an eager Celery, in-memory cache and channel layer, and the fake Graph client.
- Each git checkout or worktree gets its own test database, `test_upchatz_<folder>`.
- Shared fixtures (`api_client`, `user`, `workspace`, `other_workspace`, `auth_client(role)`, `fake_graph`) are in `conftest.py`.
- `common/testing.py` has `make_api_client` and `assert_tenant_isolated`.
- `config/tests` also runs the OpenAPI warning gate, so schema warnings fail `pytest`.
- CI (`.github/workflows/backend-ci.yml`) runs all of the above on pushes to `main` and on pull requests that touch `backend/`.

Add packages with `uv add <package>` (or `uv add --dev <package>`). Never use pip.

## Demo data

With `DEBUG` on, `uv run python manage.py seed_demo` creates (or refreshes) the demo user, workspace and connected number, then runs each app's `apps/<app>/demo.py` `seed(workspace)` in `INSTALLED_APPS` order, in one transaction. It is safe to run repeatedly.

## Razorpay setup (owner)

Billing uses Razorpay, and Razorpay plans are the only source of plan prices. UpChatz reads each plan's amount from Razorpay (`apps/billing/prices.py`); it stores no prices of its own. The amount of a Razorpay plan is what the customer pays, including GST when `BILLING_GST_ENABLED` is on.

1. In the Razorpay dashboard (Subscriptions → Plans), create one plan per UpChatz plan and interval: period monthly for monthly, and yearly (or monthly × 12) for annual, in INR. A Razorpay plan can't be edited, so a price change means a new plan.
2. In Django admin (`/admin/` → Billing → Plans), paste each plan's two ids and save. UpChatz fetches each plan and refuses an id that doesn't exist (for example a test id with live keys), has the wrong period or isn't in INR. The dashboard, Pay once, Auto-pay and the public website then use these prices.
   `RAZORPAY_PLAN_IDS` in `.env` still works as a fallback for plans without ids in admin:
   ```
   RAZORPAY_PLAN_IDS={"starter": {"monthly": "plan_…", "annual": "plan_…"}, "growth": {"monthly": "plan_…", "annual": "plan_…"}, "pro": {"monthly": "plan_…", "annual": "plan_…"}}
   ```
3. Set the API keys: `RAZORPAY_TEST_API_KEY_ID`/`RAZORPAY_TEST_API_KEY_SECRET` (`rzp_test_…`) and `RAZORPAY_API_KEY_ID`/`RAZORPAY_API_KEY_SECRET` (`rzp_live_…`). `RAZORPAY_ENV` (`test` by default, or `live`) picks the pair; a key from the other mode stops settings from loading, and optionally `RAZORPAY_TIMEOUT` (seconds, default 20).
4. Set the seller details printed on GST invoices:
   - `BILLING_SELLER_LEGAL_NAME`, `BILLING_SELLER_ADDRESS`
   - `BILLING_SELLER_GSTIN`, with `BILLING_SELLER_STATE_CODE` matching its first two digits
   - `BILLING_SAC_CODE` (default `998314`) and `BILLING_GST_RATE_PERCENT` (default `18`)
5. Add a webhook pointing to `https://<api host>/webhooks/razorpay/`. Give it a secret and set the same value as `RAZORPAY_WEBHOOK_SECRET`. Enable these events:
   - `subscription.authenticated`, `subscription.activated`, `subscription.charged`, `subscription.pending`, `subscription.halted`, `subscription.cancelled`, `subscription.completed`
   - `payment.failed`

Keys and the webhook secret are secrets: keep them in `.env` only, and never log them.
