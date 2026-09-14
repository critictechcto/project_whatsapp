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
uv run python manage.py spectacular --validate --fail-on-warn --file schema.yml
```

- Tests use `config.settings.test`, which needs no `.env`. It uses an eager Celery, in-memory cache and channel layer, and the fake Graph client.
- Each git checkout or worktree gets its own test database, `test_upchatz_<folder>`.
- Shared fixtures (`api_client`, `user`, `workspace`, `other_workspace`, `auth_client(role)`, `fake_graph`) are in `conftest.py`.
- `common/testing.py` has `make_api_client` and `assert_tenant_isolated`.
- `config/tests` also runs the OpenAPI warning gate, so schema warnings fail `pytest`.
- CI (`.github/workflows/backend-ci.yml`) runs all of the above on pushes to `main` and on pull requests that touch `backend/`.

Add packages with `uv add <package>` (or `uv add --dev <package>`). Never use pip.
