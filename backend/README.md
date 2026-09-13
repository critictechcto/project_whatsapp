# backend

Django + DRF API, managed with **uv** (Python 3.12). Not built yet — folders are placeholders.

- `config/` — Django project package (settings, urls, asgi/wsgi, celery)
- `apps/` — one Django app per domain: accounts, tenants, whatsapp, message_templates, contacts, campaigns, inbox, automations, webhooks, billing, analytics, developer_api
- `common/` — shared base models, token encryption, utilities
- `tests/` — test suite

Add packages with `uv add <package>`, run commands with `uv run <command>`.
