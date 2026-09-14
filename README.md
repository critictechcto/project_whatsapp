# project_whatsapp

Multi-tenant platform that lets businesses connect their own WhatsApp number (via Meta Embedded Signup) and send, schedule and automate messages using the official WhatsApp Business Platform (Cloud API).

## Folder map

```
docs/        Architecture notes, Meta setup checklist
infra/       docker/ (Dockerfiles), nginx/ (reverse proxy)
scripts/     Dev and deploy helper scripts
backend/     Django + DRF API, managed with uv
  config/      Django project package (settings, urls, asgi/wsgi, celery, routing)
  apps/        accounts, tenants, whatsapp, message_templates, contacts,
               campaigns, inbox, automations, webhooks, billing,
               analytics, developer_api (each with its own tests/)
  common/      Shared base models, tenancy, errors, encryption, events, test helpers
  tests/       Cross-app tests
frontend/    React + Vite + TypeScript + Tailwind
  src/features/landing/    Marketing landing page
  src/features/dashboard/  App UI (not built yet)
```

## Stack

- **Backend:** Python 3.12, Django, DRF, PostgreSQL, Redis, Celery, Django Channels — packages managed with **uv**
- **Frontend:** React, Vite, TypeScript, Tailwind CSS — packages managed with npm
- **WhatsApp:** Meta Cloud API + Embedded Signup
- **Billing:** Razorpay

## Run the landing page

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # production build in frontend/dist
```

## Deploy the landing page to GitHub Pages

`.github/workflows/deploy-pages.yml` builds `frontend/` and publishes `frontend/dist` on every push to `main` that touches `frontend/` (or manually from the Actions tab). Vite uses `base: './'`, so the same build works at `https://<user>.github.io/<repo>/` or on a custom domain.

One-time setup:

1. Push this project to a GitHub repository (e.g. `project_whatsapp`) with `main` as the default branch.
2. In the repo, go to **Settings → Pages → Build and deployment** and set **Source** to **GitHub Actions**.
3. Push to `main` or run the workflow manually. The site URL appears in the run summary and under Settings → Pages.

## Backend

Django + DRF API in `backend/`. See [backend/README.md](backend/README.md) for the layout and conventions.

### Prerequisites

- [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and every package. Don't use pip or venv.
- Docker, for local PostgreSQL and Redis.

### Run it locally

1. Start Postgres and Redis from the repo root. Postgres listens on host port **5433** so it doesn't clash with a locally installed PostgreSQL. Redis listens on 6379.

   ```bash
   docker compose -f infra/docker/compose.dev.yml up -d
   ```

2. Copy `.env.example` to `.env` at the repo root.
3. Put a Fernet key in `TOKEN_ENCRYPTION_KEYS`. Generate one with:

   ```bash
   cd backend
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   The Meta and Razorpay values can stay empty until you work on those integrations. Setting `WHATSAPP_GRAPH_CLIENT=apps.whatsapp.client.fake.FakeGraphClient` avoids calling Meta.

4. Install, migrate, create an admin user and run the server:

   ```bash
   cd backend
   uv sync
   uv run python manage.py migrate
   uv run python manage.py createsuperuser
   uv run python manage.py runserver      # ASGI via daphne, http://localhost:8000
   ```

   - API docs: http://localhost:8000/api/docs/ (OpenAPI schema at `/api/schema/`)
   - Django admin: `/admin/`
   - Health checks: `/healthz/` and `/readyz/`

5. For background jobs, run the Celery worker and beat in separate terminals from `backend/`:

   ```bash
   uv run celery -A config worker -l info                # add --pool=solo on Windows
   uv run celery -A config beat -l info                  # scheduled jobs (database scheduler)
   ```

### Tests and checks

From `backend/`, with the Docker services running:

```bash
uv run pytest                      # add --create-db after migration changes
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py spectacular --validate --fail-on-warn --file schema.yml
```

- Tests use `config.settings.test`. It needs no `.env` and never calls Meta.
- `.github/workflows/backend-ci.yml` runs these checks on pushes to `main` and on pull requests that touch `backend/`.
