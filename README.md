# project_whatsapp (working brand: Relaybox)

Multi-tenant platform that lets businesses connect their own WhatsApp number (via Meta Embedded Signup) and send, schedule and automate messages using the official WhatsApp Business Platform (Cloud API).

## Folder map

```
docs/        Architecture notes, Meta setup checklist
infra/       docker/ (Dockerfiles), nginx/ (reverse proxy)
scripts/     Dev and deploy helper scripts
backend/     Django + DRF API, managed with uv (not built yet)
  config/      Django project package (settings, urls, asgi/wsgi, celery)
  apps/        accounts, tenants, whatsapp, message_templates, contacts,
               campaigns, inbox, automations, webhooks, billing,
               analytics, developer_api
  common/      Shared base models, encryption, utils
  tests/
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

## Backend (later)

```bash
cd backend
uv add django djangorestframework   # when development starts
uv run python manage.py runserver
```

Copy `.env.example` to `.env` before running anything that needs secrets.
