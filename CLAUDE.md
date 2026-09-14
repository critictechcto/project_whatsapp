# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

UpChatz ([upchatz.com](https://upchatz.com)) — a multi-tenant WhatsApp SaaS for Indian businesses. Businesses connect their own number via **Meta Embedded Signup** and send/schedule/automate messages through the **official WhatsApp Business Platform (Cloud API)**. Unofficial WhatsApp Web automation (whatsapp-web.js, Baileys, QR-code tools) is out of scope — never suggest it.

Current state: the marketing landing page (`frontend/`) is built. The backend is being built in waves: wave 0 (foundation: settings, `common/`, accounts, tenants, whatsapp models + Graph client contract) is done; wave 1 builds whatsapp onboarding, webhooks, message_templates and contacts. The dashboard UI comes after the backend. Only build what the user has approved.

## Workflow

The user's preferred way of working: split a task into independent pieces and run **many agents in parallel, each in its own git worktree** (Agent tool with `isolation: "worktree"`, all launched in one message). Give each agent a self-contained brief with clear file ownership so branches merge cleanly, then review and merge the results. Worktrees require git — run `git init` and an initial commit first if the repo doesn't exist yet.

## Commands

Frontend (npm — run from `frontend/`):
```bash
npm install
npm run dev       # Vite dev server, http://localhost:5173
npm run build     # tsc --noEmit (type-check) + vite build → dist/
npm run preview   # serve the production build
```
The frontend has no linter or test suite yet; `npm run build` is the correctness check (CI runs the same). Deployment: `.github/workflows/deploy-pages.yml` publishes `frontend/dist` to GitHub Pages on push to `main`; `vite.config.ts` uses `base: './'` so assets resolve under a project subpath — keep asset URLs relative (no leading `/` in code).

Backend (Python 3.12, **uv only** — never pip/venv/poetry; run from `backend/`):
```bash
docker compose -f ../infra/docker/compose.dev.yml up -d   # Postgres on host port 5433, Redis 6379
uv run python manage.py migrate
uv run python manage.py runserver                        # ASGI via daphne; API docs at /api/docs/
uv run celery -A config worker --pool=solo -l info       # --pool=solo on Windows
uv run pytest                                            # add --create-db after migration changes
uv run pytest apps/tenants/tests/test_members.py::test_invitation_flow
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py spectacular --validate --fail-on-warn --file schema.yml
```
`.github/workflows/backend-ci.yml` runs these checks (ruff, migrations, schema, pytest) on changes to `backend/**`. Set `UV_LINK_MODE=copy` on this machine (uv cache on C:, repo on D:). Settings default to `config.settings.dev`; tests use `config.settings.test`, which needs no `.env` and gives each git worktree its own test database. A native PostgreSQL service also runs on 5432 here, which is why Docker Postgres is on 5433.

Copy `.env.example` to `.env` (repo root) for secrets (Meta app, Postgres, Redis, Fernet keys, Razorpay).

## Architecture

### Frontend (`frontend/src`)
- React 19 + Vite + TypeScript (strict, `noUnusedLocals`) + **Tailwind CSS v4 via `@tailwindcss/vite`** — there is no `tailwind.config`; design tokens (colors `paper`/`ink`/`accent`/`line`/…, fonts `display`/`sans`/`mono`) are defined in the `@theme` block of `src/index.css` and used as utilities (`bg-paper`, `font-display`).
- `config/site.ts` is the single source for brand name, contact emails, nav links, trial length, GST rate and pricing `plans`. Brand/prices must not be hard-coded in components. (Brand also appears in `index.html` meta tags and `public/*.svg`.)
- `features/landing/LandingPage.tsx` composes one component per page section from `features/landing/sections/`, in page order. Sections use `components/ui/` primitives (`Container`, `SectionHeader` with numbered eyebrow, `Button` rendered as `<a>`, accessible `Tabs` and `Accordion`).
- `features/landing/mockups/` are product-UI illustrations built in HTML/CSS (inbox, campaign, templates, signup flow). They are decorative — wrapped with `aria-hidden` via `Window` — so put any meaningful text for screen readers outside them (see `UseCases.tsx`).
- `features/dashboard/` is reserved for the future app UI.
- Fonts are self-hosted via Fontsource imports in `main.tsx` (no CDN): Schibsted Grotesk (`font-display`, used semibold with negative tracking), IBM Plex Sans (body), IBM Plex Mono (labels/code). The user rejected Instrument Serif + Geist as looking AI-generated — avoid common template pairings (Inter, Geist, Instrument Serif, Fraunces).
- Motion: scroll reveals use `components/ui/Reveal` (IntersectionObserver via `lib/useInView`, CSS in `.reveal`); keyframe classes (`chat-pop`, `fade-up`, `grow-x`, `typing-dot`, `caret`, `pulse-ring`) live in `index.css`. A `prefers-reduced-motion` block disables all animation — JS-driven motion (`useCountUp`, the hero chat sequence in `InboxMockup`) must check `lib/motion.ts` and jump to the final state. Don't put hover `transition-*` utilities on the same element as `Reveal` — the unlayered `.reveal` transition overrides them; wrap an inner element instead.

Design intent for marketing pages: restrained and product-led (no gradients, fake logos/testimonials/stats); copy about Meta rules must stay accurate and hedged ("under Meta's current pricing", "limits set by Meta").

### Backend (`backend/`)
Django 6 + DRF, PostgreSQL, Redis, Celery (+ Beat, DB scheduler) for bulk/scheduled sends, Django Channels for the live inbox, JWT auth (simplejwt with blacklist). `config/` is the project package; `apps/` holds one app per domain (accounts, tenants, whatsapp, message_templates, contacts, campaigns, inbox, automations, webhooks, billing, analytics, developer_api) — all are registered and mounted in `config/urls.py` already. Billing via Razorpay.

- **Tenancy**: shared schema. Tenant rows extend `common.models.TenantScopedModel` (UUID pk, `workspace` FK). API views use `common.tenancy.WorkspaceScopedMixin`/`WorkspaceScopedViewSet`: the workspace comes from the `X-Workspace-ID` header, roles are owner > admin > agent > viewer (`read_role`, `write_role`, `action_roles`), querysets are filtered to the workspace, and non-members get 404.
- **Errors**: every API error is `{"error": {"code", "message", "details"}}` (`common/exceptions.py`). Pagination is cursor-based on `created_at`.
- **Secrets**: Meta tokens and PINs use `common.fields.EncryptedTextField` (MultiFernet, `TOKEN_ENCRYPTION_KEYS`); never serialize or log them.
- **Meta Graph API**: only through `apps.whatsapp.client.get_client(token)`, which returns a `GraphClient` (the Protocol in `client/base.py`; errors map Meta codes to classes with `retryable` in `client/errors.py`). Tests use the `fake_graph` fixture (`FakeGraphClient`); never hit the network.
- **Cross-app events**: the webhooks app parses Meta payloads into the dataclasses in `common/events.py` and sends them with `emit()`. Apps react in `receivers.py` (auto-imported by `common.apps.BaseAppConfig`) and must be idempotent — webhook retries re-emit every event of a delivery, so key on `wamid`/template id. Apps don't import each other beyond the wave-0 modules; cross-app flows (signed webhook → receivers) are tested in `backend/tests/`.
- **Celery in tests** runs eagerly with propagation, so `self.retry()` raises `Retry`; exercise retry paths with `task.apply(throw=False)`.
- **Per-app conventions**: Celery tasks use explicit names (`"<app>.<verb_noun>"`); beat entries go in the app's `schedules.py` (collected by `config/celery.py`); WebSocket routes in `routing.py`; spectacular enum name fixes in `schema_enums.py`; model factories in `factories.py`. Shared test fixtures (`api_client`, `user`, `workspace`, `other_workspace`, `auth_client(role)`, `fake_graph`) live in `backend/conftest.py`; `common/testing.py` has `make_api_client` and `assert_tenant_isolated`.
- **Parallel-agent ownership**: an app branch edits only `backend/apps/<app>/**`. `pyproject.toml`/`uv.lock`, `config/`, `common/`, `backend/conftest.py`, infra and CI are lead-owned — request dependency/setting/contract changes instead of making them.

WhatsApp constraints the backend must respect: business-initiated messages require approved templates outside the 24-hour customer service window; contacts need recorded opt-in (and STOP opt-out handling); sending is capped by Meta messaging-limit tiers and number quality rating.
