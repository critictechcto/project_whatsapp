# Deploying UpChatz on DigitalOcean

**Short answer:** yes, the whole stack can run on DigitalOcean. That covers the Django API with WebSockets, the Celery worker and beat, PostgreSQL, Redis-compatible cache, media storage, and the React landing page and dashboard. Everything can sit in the **Bangalore (BLR1)** region.

**Recommendation:** use **Option B** below: App Platform plus Managed PostgreSQL, Managed Valkey and Spaces in BLR1. It costs about **$64/month (≈ ₹5,650)** before GST.

Prices were checked on DigitalOcean's pricing pages on 2026-09-14 and are in USD. INR figures use **₹88 = $1**. Confirm prices in the control panel before buying, because they change.

---

## What UpChatz needs to run

| Piece | What it does | DigitalOcean product |
|---|---|---|
| API + WebSockets | Django ASGI (Daphne): REST API, Meta and Razorpay webhooks, live inbox sockets | App Platform **service** (supports `wss://`) |
| Celery worker | Sends messages, runs campaigns, downloads media, syncs templates | App Platform **worker** |
| Celery beat | Scheduled campaigns, periodic jobs (DB scheduler). **Run exactly one.** | App Platform **worker** (smallest size) |
| Migrations | `manage.py migrate` before each release | App Platform **pre-deploy job** |
| PostgreSQL | All tenant data | **Managed PostgreSQL** |
| Redis | Celery broker, Channels layer, cache, WebSocket tickets, send rate limiter | **Managed Valkey** (Redis-compatible) |
| File storage | WhatsApp media, CSV imports, invoices | **Spaces** (S3-compatible, built-in CDN) |
| Frontend | Landing page + `/app` dashboard (static Vite build) | App Platform **static site** (no charge inside a paid app) |
| DNS | `upchatz.com`, `api.upchatz.com` | DigitalOcean DNS (free) or your registrar |

Why BLR1:
- Your customers and their end-users are in India, so the dashboard and live inbox respond faster.
- You can tell customers their data is stored in India.
- Every product above is available in BLR1.

---

## Option A: single Droplet (cheapest; staging or very early MVP)

Everything runs in Docker Compose on one server: Daphne, Celery worker and beat, Postgres, Redis, and Caddy/nginx for HTTPS.

| Item | Size | $/month |
|---|---|---|
| Basic Droplet | 2 vCPU / 4 GB / 80 GB SSD / 4 TB transfer | 24.00 |
| Droplet weekly backups | 20 % of Droplet price | 4.80 |
| Spaces | 250 GiB storage + 1 TiB transfer | 5.00 |
| **Total** | | **$33.80 ≈ ₹2,975** |
| With 18 % GST | | $39.88 ≈ ₹3,510 |

**Why not for production:**
- You manage Postgres yourself: upgrades, backups, disk space, failover.
- One server is a single point of failure.
- Scaling means migrating later.

It is fine for a staging environment.

## Option B: App Platform + managed data (recommended for launch)

| Item | Size | $/month |
|---|---|---|
| Web service (Daphne: API, webhooks, WebSockets) | 1 vCPU / 1 GiB shared, 150 GiB transfer | 12.00 |
| Celery worker | 1 vCPU / 1 GiB shared | 12.00 |
| Celery beat | 1 vCPU / 512 MiB shared | 5.00 |
| Pre-deploy `migrate` job | Billed only for seconds it runs | ~0.00 |
| Static site (landing + dashboard) | Inside the paid app | 0.00 |
| Managed PostgreSQL | 1 GiB / 1 vCPU / 10 GiB, single node | 15.15 |
| Managed Valkey | 1 GiB / 1 vCPU | 15.00 |
| Spaces | 250 GiB storage + 1 TiB transfer, CDN included | 5.00 |
| **Total** | | **$64.15 ≈ ₹5,645** |
| With 18 % GST | | $75.70 ≈ ₹6,662 |

**Why this one:**
- **No servers to patch.** Deploys run automatically from GitHub `main`, with zero-downtime rollouts and rollbacks.
- **Managed PostgreSQL** comes with automated backups, point-in-time restore, a built-in PgBouncer connection pool, trusted-source firewalling, and a one-click upgrade to a standby node. Confirm backup retention in the control panel.
- **Valkey** is a drop-in replacement for Redis. It persists data, so queued Celery tasks and WebSocket tickets survive restarts.
- **Scaling is a setting.** You raise instance size or count per component without re-architecting. WebSockets work across several web instances because Channels routes messages through Valkey, so no sticky sessions are needed.
- **Predictable bill.** Each component has a fixed monthly price, and always-on workers and sockets don't raise it the way usage-based billing would.

## Option C: growth (more tenants, high availability)

Move to this once you have paying customers who can't tolerate downtime.

| Item | Size | $/month |
|---|---|---|
| Web service × 2 | 1 vCPU / 2 GiB each | 50.00 |
| Celery worker × 2 | 1 vCPU / 2 GiB each | 50.00 |
| Celery beat × 1 | 512 MiB | 5.00 |
| Managed PostgreSQL, HA | 2 GiB primary + 1 standby | 60.90 |
| Managed Valkey | 2 GiB | 30.00 |
| Spaces | Base; overage $0.02/GiB storage, $0.01/GiB transfer | 5.00 |
| **Total** | | **$200.90 ≈ ₹17,680** |
| With 18 % GST | | $237.06 ≈ ₹20,860 |

Beyond this, the next steps are dedicated-CPU App Platform instances with autoscaling, read-only Postgres nodes (from $15/month each), or DigitalOcean Kubernetes.

## Summary

| | Option A: Droplet | Option B: App Platform (recommended) | Option C: Growth |
|---|---|---|---|
| Monthly, before tax | $33.80 (≈ ₹2,975) | **$64.15 (≈ ₹5,645)** | $200.90 (≈ ₹17,680) |
| Monthly, with 18 % GST | $39.88 (≈ ₹3,510) | **$75.70 (≈ ₹6,662)** | $237.06 (≈ ₹20,860) |
| Ops effort | High | Low | Low |
| Database | Self-managed | Managed | Managed + standby |
| Best for | Staging | Launch → first ~100 workspaces | Paying customers at scale |

**GST:** DigitalOcean charges 18 % GST to accounts in India. If you add UpChatz's GSTIN to the DigitalOcean team, invoices come without GST and you pay it under reverse charge (RCM). You can then claim input tax credit.

## Other monthly costs (not DigitalOcean)

| Item | Estimate | Notes |
|---|---|---|
| Domain `upchatz.com` | ~₹85/month (≈ ₹1,000/year) | Registrar renewal |
| Transactional email (invites, password reset, invoices) | ₹0 to a few hundred | E.g. Zoho ZeptoMail pay-as-you-go (10,000 emails per credit, first credit free) or Amazon SES. DigitalOcean doesn't send email. |
| Error tracking | $0 | Sentry free tier (`SENTRY_DSN` is already supported) |
| Uptime monitoring | $0 | DigitalOcean uptime checks or a free external monitor |
| Razorpay | Per transaction, no monthly fee | A percentage fee plus GST on each subscription payment |
| WhatsApp message charges | Not a platform cost | Under Meta's current model, each business connected through Embedded Signup pays Meta for its own messages through its own WhatsApp Business Account |

**Realistic launch budget (Option B):** about **₹6,700–7,000/month** including GST, domain and email.

---

## DigitalOcean vs Railway

Railway is a strong developer experience, but for UpChatz's production DigitalOcean is the better fit.

| | DigitalOcean (Option B) | Railway |
|---|---|---|
| Nearest region | **Bangalore (BLR1), in India** | Singapore (no India region) |
| PostgreSQL | **Managed**: automated backups, point-in-time restore, standby failover, connection pooling | **Unmanaged** template on a volume. You run backups (volume snapshots) and must set up HA yourself (Patroni guide). |
| Redis | Managed Valkey | Container on a volume (unmanaged) |
| Pricing model | Fixed per component | Per-second usage: ~$20/vCPU-month, ~$10/GB-RAM-month, $0.15/GB volume, $0.05/GB egress; Hobby $5 or Pro $20 includes the same amount of usage |
| Estimated cost for this stack | $64.15/month + GST | ~$30–45/month usage (web, worker, beat, Postgres, Redis always on); rises with traffic and egress |
| WebSockets / workers | Yes / yes | Yes / yes |
| Developer experience | Good: GitHub auto-deploy, app spec in the repo | **Excellent**: instant deploys, PR preview environments, simple UI |
| Egress | 150 GiB per web instance included, then $0.02/GiB | $0.05/GiB from the first GB |
| India GST invoice | Yes; GSTIN supported (RCM) | Check before buying |
| Growth path | Bigger instances → dedicated CPU → Kubernetes/Droplets, same account | Bigger replicas; enterprise plan |

**Verdict:**
- **Production:** DigitalOcean, Option B in BLR1. Reasons: India region, a truly managed database for tenant data and encrypted Meta tokens, predictable INR budgeting, and GST invoices.
- **Railway** is a good choice for a **staging or preview** environment. It's cheap when idle and has per-PR previews. It's not recommended as the home of production customer data while its Postgres is unmanaged and its nearest region is Singapore.

---

## What must change in the code before deploying

These are not done yet. Each is a small, separate task.

1. **Container image.**
   - Add `backend/Dockerfile`: Python 3.12 slim, `uv sync --frozen --no-dev`, `collectstatic`.
   - The command is `daphne config.asgi:application`.
   - Worker: `celery -A config worker -l info`. On Linux, use the default prefork pool, not `--pool=solo`.
   - Beat: `celery -A config beat -l info`.
2. **App spec.**
   - Add `.do/app.yaml` with the web service, worker, beat (1 instance), pre-deploy job (`migrate`), static site (`frontend`, `npm run build`, output `dist`) and environment variables.
   - Region `blr`.
3. **Media on Spaces.**
   - `config/settings/prod.py` still uses `FileSystemStorage`, but App Platform disks are ephemeral.
   - Switch the default storage to `django-storages` S3 backend pointed at Spaces (`AWS_S3_ENDPOINT_URL=https://blr1.digitaloceanspaces.com`, private bucket, signed URLs).
4. **TLS Redis URLs.** Valkey uses `rediss://`. Set `REDIS_URL`/`CELERY_BROKER_URL` accordingly, and make sure the Channels layer and Celery accept TLS.
5. **Postgres connections.**
   - Connect through the DigitalOcean connection pool (PgBouncer, transaction mode).
   - Set `DISABLE_SERVER_SIDE_CURSORS=True` and a low `CONN_MAX_AGE`.
   - Add the app as a trusted source.
6. **Production environment variables.**
   - `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DJANGO_SECRET_KEY`, `TOKEN_ENCRYPTION_KEYS`
   - `DJANGO_ALLOWED_HOSTS=api.upchatz.com`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS=https://upchatz.com`, `WS_ALLOWED_ORIGINS`
   - Meta app secrets, Razorpay keys and webhook secret, email SMTP, `SENTRY_DSN`
   - Store them as encrypted App Platform variables, never in the repo.
7. **Domains and webhooks.**
   - `upchatz.com` → static site; `api.upchatz.com` → web service.
   - Meta webhook callback: `https://api.upchatz.com/webhooks/meta/`. Razorpay webhook: `https://api.upchatz.com/webhooks/razorpay/`.
8. **Frontend build variables.** `VITE_BASE=/`, `VITE_API_URL=https://api.upchatz.com`, `VITE_WS_URL=wss://api.upchatz.com`, `VITE_API_MODE=live`.
9. **Health checks.** Point App Platform's HTTP health check at `/healthz/`, which is already exempt from the SSL redirect.
10. **CI/CD.** Keep `backend-ci.yml` as the gate. Enable App Platform auto-deploy on `main` only after CI passes, or deploy with `doctl apps create-deployment` from a workflow.

## Sources
- [DigitalOcean App Platform pricing](https://www.digitalocean.com/pricing/app-platform)
- [DigitalOcean Managed Databases pricing](https://www.digitalocean.com/pricing/managed-databases) and [PostgreSQL pricing details](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/)
- [DigitalOcean Droplet pricing](https://www.digitalocean.com/pricing/droplets)
- [DigitalOcean Spaces pricing](https://www.digitalocean.com/pricing/spaces-object-storage)
- [DigitalOcean regional availability](https://docs.digitalocean.com/platform/regional-availability/)
- [App Platform limits](https://docs.digitalocean.com/products/app-platform/details/limits/) and [WebSockets on App Platform](https://docs.digitalocean.com/developer-center/deploy-an-app-using-websockets-to-app-platform/)
- [DigitalOcean India tax information](https://docs.digitalocean.com/platform/billing/taxes/ind/)
- [Railway pricing](https://railway.com/pricing), [regions](https://docs.railway.com/reference/regions), [PostgreSQL guide](https://docs.railway.com/guides/postgresql), [backups](https://docs.railway.com/reference/backups)
- [Zoho ZeptoMail pricing](https://www.zoho.com/zeptomail/pricing.html)
