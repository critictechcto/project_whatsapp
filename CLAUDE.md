# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

UpChatz ([upchatz.com](https://upchatz.com)) — a multi-tenant WhatsApp SaaS for Indian businesses. Businesses connect their own number via **Meta Embedded Signup** and send/schedule/automate messages through the **official WhatsApp Business Platform (Cloud API)**. Unofficial WhatsApp Web automation (whatsapp-web.js, Baileys, QR-code tools) is out of scope — never suggest it.

Current state: the marketing landing page (`frontend/`) is built. The backend is built in waves: wave 0 (foundation) and wave 1 (whatsapp onboarding, webhooks, message_templates, contacts) are merged. Wave 2 builds backend and dashboard together against the frozen contract in `docs/contracts/wave-2.md`: the inbox messaging core, API stubs for inbox/campaigns/automations/billing, realtime and the dashboard foundation are merged (tag `wave-2-foundation`), and the wave-2 backend (inbox, campaigns, automations, billing and their integration) is merged; dashboard screens are in progress. Only build what the user has approved.

## Workflow

The user's preferred way of working: split a task into independent pieces and run **many agents in parallel, each in its own git worktree** (Agent tool with `isolation: "worktree"`, all launched in one message). Give each agent a self-contained brief with clear file ownership so branches merge cleanly, then review and merge the results. Worktrees require git — run `git init` and an initial commit first if the repo doesn't exist yet.

## Commands

Frontend (npm — run from `frontend/`):
```bash
npm install
npm run dev       # Vite dev server, http://localhost:5173
npm run build     # tsc --noEmit (type-check) + vite build → dist/
npm run preview   # serve the production build
npm run lint      # eslint (flat config)
npm test          # vitest (jsdom + MSW node server); npx vitest run src/api/errors.test.ts for one file
npm run api:types # regenerate src/api/schema.d.ts from backend/openapi.yml (commit the result)
VITE_API_MODE=mock npm run dev   # dashboard at /app with seeded MSW data; demo login demo@upchatz.com / demo12345
```
The correctness check is `npm run lint && npm test && npm run build` (the Pages workflow runs all three). Env: `VITE_BASE` (absolute deploy base, default `/`; router basename and public assets follow `import.meta.env.BASE_URL`), `VITE_API_URL`, `VITE_WS_URL`, `VITE_API_MODE` (`mock`|`live`). Deployment: `.github/workflows/deploy-pages.yml` builds in mock mode with `VITE_BASE=/` for the custom domain `upchatz.com` (`public/CNAME`) and copies `index.html` to `404.html` for deep links; import assets from code or prefix `BASE_URL` — never hard-code `/` or `./` paths.

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
DJANGO_SETTINGS_MODULE=config.settings.test uv run python manage.py spectacular --validate --fail-on-warn --file openapi.yml
uv run python manage.py seed_demo                        # DEBUG only; demo workspace, safe to re-run
```
After API changes, regenerate and commit `backend/openapi.yml` with the spectacular command above (LF line endings; CI fails if it is stale), then run `npm run api:types` in `frontend/`.
`.github/workflows/backend-ci.yml` runs these checks (ruff, migrations, schema, pytest) on changes to `backend/**`. Set `UV_LINK_MODE=copy` on this machine (uv cache on C:, repo on D:). Settings default to `config.settings.dev`; tests use `config.settings.test`, which needs no `.env` and gives each git worktree its own test database. A native PostgreSQL service also runs on 5432 here, which is why Docker Postgres is on 5433.

Copy `.env.example` to `.env` (repo root) for secrets (Meta app, Postgres, Redis, Fernet keys, Razorpay).

## Architecture

### Frontend (`frontend/src`)
- React 19 + Vite + TypeScript (strict, `noUnusedLocals`) + **Tailwind CSS v4 via `@tailwindcss/vite`** — there is no `tailwind.config`; design tokens (colors `paper`/`ink`/`accent`/`line`/…, fonts `display`/`sans`/`mono`) are defined in the `@theme` block of `src/index.css` and used as utilities (`bg-paper`, `font-display`).
- `config/site.ts` is the single source for brand name, contact emails, nav links, trial length, GST rate and pricing `plans`. Brand/prices must not be hard-coded in components. (Brand also appears in `index.html` meta tags and `public/*.svg`.)
- `features/landing/LandingPage.tsx` composes one component per page section from `features/landing/sections/`, in page order. Sections use `components/ui/` primitives (`Container`, `SectionHeader` with numbered eyebrow, `Button` rendered as `<a>`, accessible `Tabs` and `Accordion`).
- `features/landing/mockups/` are product-UI illustrations built in HTML/CSS (inbox, campaign, templates, signup flow). They are decorative — wrapped with `aria-hidden` via `Window` — so put any meaningful text for screen readers outside them (see `UseCases.tsx`).
- The dashboard is a lazy chunk under `/app` (`App.tsx` switches on the path, so the landing bundle never loads router, react-query, MSW or charts). Routes: `/app/login`, `/app/register`, `/app/invitations/accept`, `/app/w/:workspaceId/*` inside `shell/AppShell`.
  - Each area (`features/dashboard/<area>/` — home, inbox, contacts, templates, campaigns, automations, whatsapp, team, billing, settings) exports `routes.tsx` (lazy, relative to `/app/w/:workspaceId/`), `nav.ts` and `mocks.ts`; `registry/` aggregates them, so feature work never edits shared files.
  - Data: `api/` (`api` openapi-fetch client + `unwrap`, `applyApiErrorToForm`, `workspaceKeys` — query keys always include the workspace id, `useCursorQuery`, `idempotencyHeaders`). Auth in `lib/auth` (access token in memory, refresh in localStorage, single-flight refresh across tabs). Realtime in `lib/realtime` (`useRealtimeEvent(type, handler)`; ticket via `POST /api/v1/inbox/ws-ticket/`). Mocks in `mocks/` (typed `openapi-msw` handlers, seeded Indian demo data, `mockRealtime.emit`).
  - UI kit in `components/app` (real `<button>` Button, form controls, Dialog/Drawer/Table/Toast…, `whatsapp/` preview + TemplatePicker); landing keeps `components/ui`. Forms use zod + react-hook-form. Tests render with `renderDashboard(path)` from `src/test/render.tsx`.
- Fonts are self-hosted via Fontsource imports in `main.tsx` (no CDN): Schibsted Grotesk (`font-display`, used semibold with negative tracking), IBM Plex Sans (body), IBM Plex Mono (labels/code). The user rejected Instrument Serif + Geist as looking AI-generated — avoid common template pairings (Inter, Geist, Instrument Serif, Fraunces).
- Motion: scroll reveals use `components/ui/Reveal` (IntersectionObserver via `lib/useInView`, CSS in `.reveal`); keyframe classes (`chat-pop`, `fade-up`, `grow-x`, `typing-dot`, `caret`, `pulse-ring`) live in `index.css`. A `prefers-reduced-motion` block disables all animation — JS-driven motion (`useCountUp`, the shared hero chat sequence in `features/landing/lib/useChatSequence.ts`) must check `lib/motion.ts` and jump to the final state. Depth effects use CSS 3D only (no WebGL): `features/landing/scenes/` (layered `HeroScene`, `MessageJourney`) and the `components/ui` primitives `TiltCard`/`usePointerTilt` (fine pointer only) and `ScrollDepth` (`animation-timeline: view()` with a Reveal fallback); loops pause offscreen via `features/landing/lib/useOnScreen`. Don't put hover `transition-*` utilities on the same element as `Reveal` — the unlayered `.reveal` transition overrides them; wrap an inner element instead.

Design intent for marketing pages: restrained and product-led (no gradients, fake logos/testimonials/stats); copy about Meta rules must stay accurate and hedged ("under Meta's current pricing", "limits set by Meta").

### Backend (`backend/`)
Django 6 + DRF, PostgreSQL, Redis, Celery (+ Beat, DB scheduler) for bulk/scheduled sends, Django Channels for the live inbox, JWT auth (simplejwt with blacklist). `config/` is the project package; `apps/` holds one app per domain (accounts, tenants, whatsapp, message_templates, contacts, campaigns, inbox, automations, webhooks, billing, analytics, developer_api) — all are registered and mounted in `config/urls.py` already. Billing via Razorpay.

- **Tenancy**: shared schema. Tenant rows extend `common.models.TenantScopedModel` (UUID pk, `workspace` FK). API views use `common.tenancy.WorkspaceScopedMixin`/`WorkspaceScopedViewSet`: the workspace comes from the `X-Workspace-ID` header, roles are owner > admin > agent > viewer (`read_role`, `write_role`, `action_roles`), querysets are filtered to the workspace, and non-members get 404.
- **Errors**: every API error is `{"error": {"code", "message", "details"}}` (`common/exceptions.py`). Pagination is cursor-based on `created_at`.
- **Secrets**: Meta tokens and PINs use `common.fields.EncryptedTextField` (MultiFernet, `TOKEN_ENCRYPTION_KEYS`); never serialize or log them.
- **Meta Graph API**: only through `apps.whatsapp.client.get_client(token)`, which returns a `GraphClient` (the Protocol in `client/base.py`; errors map Meta codes to classes with `retryable` in `client/errors.py`). Tests use the `fake_graph` fixture (`FakeGraphClient`); never hit the network.
- **Cross-app events**: the webhooks app parses Meta payloads into the dataclasses in `common/events.py` and sends them with `emit()`. Apps react in `receivers.py` (auto-imported by `common.apps.BaseAppConfig`) and must be idempotent — webhook retries re-emit every event of a delivery, so key on `wamid`/template id. Cross-app flows (signed Meta/Razorpay webhooks → receivers, the realtime socket) are tested in `backend/tests/`.
  - Other events: the inbox emits `MessageRecorded`/`MessageDeliveryUpdated`; `apps.tenants.services` emits `WorkspaceCreated(workspace_id, owner_id)`, `MembershipRoleChanged(workspace_id, user_id, old_role, new_role)` and `MembershipRemoved(workspace_id, user_id)` (removal or leaving). All are sent with `transaction.on_commit`; billing starts the trial and the inbox revokes sockets from them.
  - Allowed cross-app imports (besides wave 0–1 modules and events): `apps.inbox.sending`, `apps.inbox.services`, `apps.inbox.models`, the summary serializers in `apps.inbox.serializers`, `apps.message_templates.services`, `apps.contacts.services`, `apps.billing.entitlements`. Everything else goes through events.
- **Realtime**: `common.realtime.broadcast(workspace_id, type, data)` / `broadcast_user(user_id, type, data, workspace_id=...)` send frames on commit. Clients get a single-use ticket from `POST /api/v1/inbox/ws-ticket/` (`common/ws_auth.py`) and connect to `/ws/v1/?ticket=…`; frames and close codes are in `docs/contracts/wave-2.md`.
- **Plans**: `apps.billing.entitlements` — `has_feature`, `remaining_quota`, `check_quota` (raises `QuotaExceeded`, 409 `quota_exceeded`, details `{metric, limit, used}`). A missing plan feature raises `common.exceptions.FeatureNotAvailable` (409 `feature_not_available`). Quota guards: invitations (members + open invitations), accepting invitations, contact create and CSV import (overflow rows skipped with reason `quota_exceeded`), and new numbers at Embedded Signup.
- **Demo data**: apps may add `apps/<app>/demo.py` with `seed(workspace)`; `manage.py seed_demo` (DEBUG only) runs them in `INSTALLED_APPS` order and must stay re-runnable.
- **Celery in tests** runs eagerly with propagation, so `self.retry()` raises `Retry`; exercise retry paths with `task.apply(throw=False)`.
- **Per-app conventions**: Celery tasks use explicit names (`"<app>.<verb_noun>"`); beat entries go in the app's `schedules.py` (collected by `config/celery.py`); WebSocket routes in `routing.py`; spectacular enum name fixes in `schema_enums.py`; model factories in `factories.py`. Shared test fixtures (`api_client`, `user`, `workspace`, `other_workspace`, `auth_client(role)`, `fake_graph`) live in `backend/conftest.py`; `common/testing.py` has `make_api_client` and `assert_tenant_isolated`.
- **Parallel-agent ownership**: an app branch edits only `backend/apps/<app>/**`. `pyproject.toml`/`uv.lock`, `config/`, `common/`, `backend/conftest.py`, infra and CI are lead-owned — request dependency/setting/contract changes instead of making them.

WhatsApp constraints the backend must respect: business-initiated messages require approved templates outside the 24-hour customer service window; contacts need recorded opt-in (and STOP opt-out handling); sending is capped by Meta messaging-limit tiers and number quality rating.
