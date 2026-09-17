# Deploying UpChatz to DigitalOcean App Platform

This guide sets up the product at **`https://app.upchatz.com`**: the API, webhooks, WebSockets and dashboard. The marketing site stays on GitHub Pages at `upchatz.com`. For the choice of platform and the cost breakdown, see [digitalocean.md](digitalocean.md) (Option B).

The spec is [`.do/app.yaml`](../../.do/app.yaml). It describes one app in region `blr`:

| Component | Type | Runs | Size |
|---|---|---|---|
| `api` | Web service | `daphne` (Django ASGI) on port 8080 | `apps-s-1vcpu-1gb` |
| `worker` | Worker | `celery -A config worker --concurrency 2` | `apps-s-1vcpu-1gb` |
| `scheduler` | Worker | `celery -A config beat`, **always exactly 1 instance** | `apps-s-1vcpu-0.5gb` |
| `migrate` | Pre-deploy job | `python manage.py migrate --noinput` | `apps-s-1vcpu-0.5gb` |
| `dashboard` | Static site | `npm ci && npm run build` in `frontend/` (live API mode) | free |

Requests on `app.upchatz.com` are routed by path:
- `/api`, `/webhooks`, `/ws`, `/admin`, `/static`, `/pay`, `/healthz` and `/readyz` go to `api`.
- Everything else goes to `dashboard`, which serves `shell.html` (the page without the prerendered landing markup) for deep links like `/app/login`.

The dashboard calls the API on its own origin, so there are no CORS or cross-site cookie problems.

The backend is built by the Python buildpack from `backend/requirements.txt`. The buildpack uses `requirements.txt` rather than `uv.lock`, so regenerate it whenever dependencies change. CI (`deploy-config.yml`) fails if it is stale:

```bash
cd backend
uv export --frozen --no-dev --no-hashes -o requirements.txt
```

It is exported without hashes: in hash-checking mode pip refuses any package without a hash, which is brittle when the buildpack installs its own tools. Versions are still pinned exactly by the lock file.

---

## 1. Create the data services (BLR1)

Create all three in **Bangalore (BLR1)**, in the same VPC as the app.

1. **Managed PostgreSQL**
   - Engine and size: PostgreSQL 17, 1 GiB, single node. Name the cluster `upchatz-pg`.
   - *Users & Databases:* add the database `upchatz` and the user `upchatz`.
   - *Connection Pools:* add the pool `upchatz-pool` with database `upchatz`, user `upchatz`, mode **Transaction** and size 20.
   - The app connects through this pool (`${db.upchatz-pool.DATABASE_URL}`), which is why the spec sets `DATABASE_DISABLE_SERVER_SIDE_CURSORS=true` and `DATABASE_CONN_MAX_AGE=0`.
2. **Managed Valkey**
   - Size: 1 GiB. Name the cluster `upchatz-valkey`.
   - It only accepts TLS (`rediss://`).
3. **Spaces bucket**
   - Create a bucket (for example `upchatz-media`) in BLR1 and enable the CDN.
   - Under *API → Spaces Keys*, create an access key limited to this bucket.

If you use other names, change `cluster_name`, `db_name`, `db_user` and the pool name in `.do/app.yaml` to match before you import it.

## 2. Create the app from the spec

Use either option:
- **Control panel:** Apps → Create App → pick the GitHub repo `critictechcto/project_whatsapp_landing_page`, branch `main`. Then *Edit App Spec* and paste `.do/app.yaml`.
- **CLI:**
  ```bash
  doctl auth init
  doctl apps create --spec .do/app.yaml
  ```

Before either option works, authorise the DigitalOcean GitHub app for the repo.

The first deployment will fail until the secrets are filled in. That is expected.

**Trusted sources:** attaching the databases in the spec should add the app as a trusted source. Check this under each cluster's *Settings → Trusted sources*, and add the app if it is missing.

## 3. Fill in the secrets

Go to App → *Settings* → *App-Level Environment Variables* and replace every `CHANGE_ME`. Keep the variables marked **Encrypt** (type `SECRET`) encrypted.

> **Never paste secrets into chat, issues, commits or `.do/app.yaml`.** Generate them on your own machine and paste them straight into the control panel.

Generate the keys on your machine, from `backend/`:

```bash
# DJANGO_SECRET_KEY
uv run python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
# TOKEN_ENCRYPTION_KEYS (one Fernet key; to rotate, prepend a new key and keep the old ones)
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# META_WEBHOOK_VERIFY_TOKEN
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Store `TOKEN_ENCRYPTION_KEYS` in your password manager too. If you lose it, every stored Meta token becomes unreadable.

The other variables:

| Variables | Where the values come from |
|---|---|
| `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | The Spaces bucket and key from step 1 |
| `PUBLIC_MEDIA_BASE_URL` | The bucket's CDN URL, for example `https://upchatz-media.blr1.cdn.digitaloceanspaces.com` |
| `META_APP_ID`, `META_APP_SECRET` | Meta App Dashboard → App settings → Basic |
| `META_EMBEDDED_SIGNUP_CONFIG_ID` | Facebook Login for Business → Configurations |
| `PLATFORM_WA_*` | UpChatz's own alerts number (WABA ID, phone number ID, display number, system-user token). Leave these empty to turn seller alerts off. |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_PLAN_IDS` | Razorpay Dashboard (live mode) |
| `BILLING_SELLER_*` | UpChatz's legal name, GSTIN, state code and address, as printed on invoices |
| `EMAIL_*` | Your SMTP provider (for example ZeptoMail or SES) |
| `SENTRY_DSN` | Optional; leave it empty to turn Sentry off |

**Updating the spec later:** App Platform does not read `.do/app.yaml` on push. It keeps its own copy. To change the spec:

```bash
doctl apps spec get <app-id> > live.yaml   # secrets come back as encrypted EV[...] values
# edit live.yaml, then
doctl apps update <app-id> --spec live.yaml
```

Never run `doctl apps update --spec .do/app.yaml` against the live app, because it would overwrite the real secrets with `CHANGE_ME`. Copy structural changes into the repo file as well, and delete `live.yaml` afterwards.

## 4. DNS for `app.upchatz.com`

1. In the app, open *Settings → Domains*. `app.upchatz.com` is already listed from the spec, and the panel shows a CNAME target like `upchatz-xxxxx.ondigitalocean.app`.
2. At the DNS host for `upchatz.com`, add `CNAME app → <that target>`. Leave the apex and `www` records for GitHub Pages as they are.
3. Wait for the domain to show *Active*. App Platform issues the TLS certificate itself.

Before DNS is live, the default `*.ondigitalocean.app` URL returns 400, because `DJANGO_ALLOWED_HOSTS` only lists `app.upchatz.com`. To test on that URL anyway, temporarily add its host to `DJANGO_ALLOWED_HOSTS`, and its origin to the `CSRF`, `CORS` and `WS` origin lists. Remove them afterwards.

## 5. Meta and Razorpay settings

**Meta App Dashboard → WhatsApp → Configuration**
- Callback URL: `https://app.upchatz.com/webhooks/meta/`
- Verify token: the value of `META_WEBHOOK_VERIFY_TOKEN`
- Subscribe to these webhook fields:
  - `messages`
  - `message_template_status_update`
  - `message_template_quality_update`
  - `template_category_update`
  - `phone_number_quality_update`
  - `account_update`

**Embedded Signup (Facebook Login for Business)**
- Add `https://app.upchatz.com` to *Allowed Domains for the JavaScript SDK* and to *Valid OAuth Redirect URIs*.
- Add `upchatz.com` to *App Domains* under App settings → Basic.

**Razorpay (UpChatz subscriptions)**
- Webhook URL: `https://app.upchatz.com/webhooks/razorpay/`
- Secret: the value of `RAZORPAY_WEBHOOK_SECRET`

Sellers' own payment webhooks are shown to them in the dashboard. Those URLs are built from `PUBLIC_API_BASE_URL`.

## 6. First-deploy checklist

1. **Build logs:** requirements install, `collectstatic` runs in the `api` build, and `npm run build` succeeds for `dashboard`.
2. **`migrate` job log** (Activity → the deployment → `migrate`): the migrations are applied with no errors. If the job fails, the deployment stops and the previous version keeps running.
3. `curl https://app.upchatz.com/healthz/` returns `{"status": "ok"}`.
4. `curl https://app.upchatz.com/readyz/` returns `{"status": "ok"}`. A 503 means the database is not reachable; check the trusted sources and the pool.
5. **Create the first admin.** Open App → *Console* → component `api` and run:
   ```bash
   python manage.py createsuperuser
   ```
6. **Sync the alerts templates** if `PLATFORM_WA_*` is set, in the same console:
   ```bash
   python manage.py sync_platform_templates
   ```
7. **Dashboard:** open `https://app.upchatz.com/app/register`, create an account, and log in. The inbox should show as connected, meaning the WebSocket to `wss://app.upchatz.com/ws/v1/` opened.
8. **Worker and scheduler logs:** the worker shows `celery@... ready` and beat shows `DatabaseScheduler` starting.
9. **Meta webhook:** verifying the callback in the Meta dashboard succeeds, and a test message shows up in the inbox.

## 7. Deploying safely

The spec sets `deploy_on_push: true`, so every push to `main` deploys, even when CI is red. A safer setup is to deploy only after CI passes:

1. Set `deploy_on_push: false` on every component (in the live spec, as described in step 3).
2. Create a DigitalOcean API token with write access to apps.
3. Add it to GitHub as the secret `DIGITALOCEAN_ACCESS_TOKEN`, and the app ID as the variable `DO_APP_ID`.
4. Add a workflow like this:

```yaml
on:
  workflow_run:
    workflows: [Backend CI]
    types: [completed]
    branches: [main]
jobs:
  deploy:
    if: github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest
    steps:
      - uses: digitalocean/action-doctl@v2
        with:
          token: ${{ secrets.DIGITALOCEAN_ACCESS_TOKEN }}
      - run: doctl apps create-deployment ${{ vars.DO_APP_ID }} --wait
```

Backend CI only runs when `backend/**` changes. Add a `workflow_dispatch` trigger, or a similar gate on the frontend checks, if dashboard-only changes should deploy too.

## 8. Rollback

- **Code:** App → *Activity* → pick an earlier successful deployment → **Rollback**.
- **Migrations are not reversed by a rollback.** Keep migrations backwards compatible: add columns before the code that uses them, and remove them one release later.
- **Bad data:** Managed PostgreSQL → *Backups* → restore to a point in time. This restores into a new cluster. Point `DATABASE_URL` at it, or swap the clusters.

## 9. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Build fails in `collectstatic` with `ImproperlyConfigured` | The buildpack's own collectstatic ran with `config.settings.prod`. Check that the app-level `DISABLE_COLLECTSTATIC=1` (BUILD_TIME) is set and the `api` build command still uses `config.settings.build`. |
| Health check fails, logs show `DisallowedHost` | The request's host is not in `DJANGO_ALLOWED_HOSTS` |
| WebSocket closes straight away | `WS_ALLOWED_ORIGINS` must be `https://app.upchatz.com` |
| Worker cannot connect to the broker | Valkey needs `rediss://` with TLS options; check `REDIS_URL` and `CELERY_BROKER_URL` |
| Scheduled campaigns fire twice | `scheduler` has more than 1 instance; set it back to 1 |

## Cost

About **$64/month before GST** (≈ ₹5,650) for this layout. The breakdown and GST notes are in [digitalocean.md](digitalocean.md#option-b-app-platform--managed-data-recommended-for-launch).
