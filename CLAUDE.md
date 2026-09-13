# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

project_whatsapp — a multi-tenant WhatsApp SaaS for Indian businesses. Businesses connect their own number via **Meta Embedded Signup** and send/schedule/automate messages through the **official WhatsApp Business Platform (Cloud API)**. Unofficial WhatsApp Web automation (whatsapp-web.js, Baileys, QR-code tools) is out of scope — never suggest it.

Current state: only the marketing landing page (`frontend/`) is built. `backend/` is an empty uv project skeleton — don't scaffold Django or add backend code until the user explicitly asks.

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
There is no linter or test suite yet; `npm run build` is the correctness check (CI runs the same). Deployment: `.github/workflows/deploy-pages.yml` publishes `frontend/dist` to GitHub Pages on push to `main`; `vite.config.ts` uses `base: './'` so assets resolve under a project subpath — keep asset URLs relative (no leading `/` in code).

Backend (Python 3.12, **uv only** — never pip/venv/poetry; run from `backend/`):
```bash
uv add <package>
uv run <command>          # e.g. uv run python manage.py runserver (once Django exists)
```

Copy `.env.example` to `.env` for secrets (Meta app, Postgres, Redis, Fernet token key, Razorpay).

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

### Backend (planned, `backend/`)
Django + DRF, PostgreSQL, Redis, Celery (+ Beat) for bulk/scheduled sends, Django Channels for the live inbox. `config/` will be the Django project package; `apps/` holds one Django app per domain (accounts, tenants, whatsapp, message_templates, contacts, campaigns, inbox, automations, webhooks, billing, analytics, developer_api); `common/` for shared base models, token encryption and utilities. Multi-tenancy is a shared schema with a tenant FK. Customer Meta access tokens are stored Fernet-encrypted; Meta webhooks must verify the `X-Hub-Signature-256` signature. Billing via Razorpay.

WhatsApp constraints the backend must respect: business-initiated messages require approved templates outside the 24-hour customer service window; contacts need recorded opt-in (and STOP opt-out handling); sending is capped by Meta messaging-limit tiers and number quality rating.
