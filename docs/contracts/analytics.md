# Analytics contract

The backend `apps.analytics` agent implements this document; the dashboard `features/dashboard/analytics` agent consumes it. Conventions from `docs/contracts/wave-2.md` apply (errors, roles, `X-Workspace-ID`, money in integer paise). Changing a name, removing a field or changing a type needs a lead request; adding optional response fields is allowed. Serializer `FooSerializer` produces component `Foo`, and component names below must match.

## Access and plans

- Every endpoint is `GET`, readable by any member (viewer and up).
- New plan feature **`analytics`** (`apps.billing.entitlements.ANALYTICS`), included in **Growth and Pro**, not Starter (matches "Delivery, read & reply analytics" in `frontend/src/config/site.ts`). A billing migration adds it to existing `growth` and `pro` plan rows. Without it every endpoint returns 409 `feature_not_available` with `details: {"feature": "analytics"}`.
- The `commerce` report additionally requires the `commerce` feature (409 `feature_not_available`, `details.feature = "commerce"`).
- Trial workspaces are on Growth, so they see analytics.

## Date range (every endpoint)

Query params `from` and `to`, dates `YYYY-MM-DD`, **inclusive**, interpreted in the workspace's `time_zone` (default `Asia/Kolkata`). Defaults: `to` = today, `from` = `to` − 29 days. `to` may not be after today (in the workspace time zone); `from` ≤ `to`; at most **92 days**. Violations return 400 `invalid` with field errors in `details`.

Every response includes `range`:

| Component `AnalyticsRange` | Type |
|---|---|
| `from` | date |
| `to` | date |
| `time_zone` | string |
| `previous_from` | date — the same-length period immediately before `from` |
| `previous_to` | date |

A message counts on the day of its `created_at` (in the workspace time zone). Status counts use the message's current status: `sent` counts outbound messages whose status is `sent`, `delivered` or `read`; `delivered` counts `delivered` or `read`; `read` counts `read`; `failed` counts `failed`. Outbound messages still `queued`/`sending` count in none of those. `received` counts inbound messages. Rates are decimals 0–1 rounded to 4 places, or `null` when the denominator is 0: `delivery_rate = delivered / sent`, `read_rate = read / delivered`.

## Endpoints — `/api/v1/analytics/`

### `GET overview/` → `AnalyticsOverview`

| Field | Type |
|---|---|
| `range` | `AnalyticsRange` |
| `current` | `AnalyticsTotals` |
| `previous` | `AnalyticsTotals` (same metrics for the previous period) |

`AnalyticsTotals`:

| Field | Type | Meaning |
|---|---|---|
| `messages_sent` | int | outbound sent (definition above) |
| `messages_delivered` | int | |
| `messages_read` | int | |
| `messages_failed` | int | |
| `messages_received` | int | inbound |
| `delivery_rate` | decimal string \| null | |
| `read_rate` | decimal string \| null | |
| `conversations_started` | int | conversations created in range |
| `contacts_added` | int | contacts created in range |
| `contacts_opted_in` | int | contacts with `opted_in_at` in range |
| `contacts_opted_out` | int | contacts with `opted_out_at` in range |
| `campaigns_sent` | int | campaigns with `started_at` in range |
| `automation_runs` | int | automation runs with status `succeeded` created in range |
| `orders` | int \| null | orders created in range, excluding `draft`; `null` without the `commerce` feature |
| `revenue_paise` | int \| null | sum of `total_paise` of orders created in range with payment status `paid` or `cod_collected`; `null` without `commerce` |

### `GET messages/` → `AnalyticsMessages`

| Field | Type |
|---|---|
| `range` | `AnalyticsRange` |
| `series` | `AnalyticsMessagePoint[]` — one point per day in range, oldest first, zero-filled |
| `by_source` | `AnalyticsSourceRow[]` — outbound sources with at least one message, ordered by `sent` desc |
| `by_category` | `AnalyticsCategoryRow[]` — outbound template messages grouped by `template_category` (`marketing`, `utility`, `authentication`, or `""` for non-template), ordered by `sent` desc |
| `failure_reasons` | `AnalyticsFailureRow[]` — top 10 `error_code` values of failed outbound messages, ordered by `count` desc |

- `AnalyticsMessagePoint`: `date` (date), `sent`, `delivered`, `read`, `failed`, `received` (ints).
- `AnalyticsSourceRow`: `source` (`MessageSourceEnum` minus `inbound`; values `inbox`, `campaign`, `automation`, `api`, `commerce`), `sent`, `delivered`, `read`, `failed` (ints), `delivery_rate`, `read_rate`.
- `AnalyticsCategoryRow`: `category` (string), `sent`, `delivered`, `read`, `failed` (ints).
- `AnalyticsFailureRow`: `error_code` (string, `""` when unknown), `count` (int).

### `GET templates/` → `AnalyticsTemplates`

`range` plus `results`: `AnalyticsTemplateRow[]`, outbound `type = template` messages in range grouped by `template_name` + `template_language`, ordered by `sent` desc, at most 50 rows.

`AnalyticsTemplateRow`: `template_id` (uuid \| null — the `message_templates` row if it still exists), `name`, `language`, `category` (strings), `sent`, `delivered`, `read`, `failed` (ints), `delivery_rate`, `read_rate`.

### `GET campaigns/` → `AnalyticsCampaigns`

`range` plus `results`: `AnalyticsCampaignRow[]` — campaigns with `started_at` in range, newest first, at most 50. Uses the campaign's stored counters (lifetime of that campaign, not clipped to the range).

`AnalyticsCampaignRow`: `id` (uuid), `name`, `status` (`CampaignStatusEnum`), `started_at` (datetime), `total_count`, `sent_count`, `delivered_count`, `read_count`, `failed_count`, `replied_count` (ints), `delivery_rate`, `read_rate`, `reply_rate` (`replied / delivered`) decimals or null.

### `GET team/` → `AnalyticsTeam`

`range` plus `results`: `AnalyticsTeamRow[]` — one row per current workspace member, ordered by `messages_sent` desc then name.

`AnalyticsTeamRow`: `user_id` (uuid), `name` (string), `email` (string), `role` (string), `messages_sent` (int — outbound `source = inbox` messages with `sent_by` = the user, created in range), `conversations_assigned` (int — conversations currently assigned to the user whose `last_message_at` is in range), `conversations_closed` (int — of those, status `closed`).

### `GET commerce/` → `AnalyticsCommerce` (also needs `commerce`)

| Field | Type |
|---|---|
| `range` | `AnalyticsRange` |
| `series` | `AnalyticsCommercePoint[]` — daily, zero-filled: `date`, `orders` (int), `revenue_paise` (int) |
| `orders` | int (excluding `draft`) |
| `paid_orders` | int (payment status `paid` or `cod_collected`) |
| `revenue_paise` | int |
| `average_order_paise` | int \| null (`revenue_paise / paid_orders`, rounded down) |
| `by_status` | `AnalyticsOrderStatusRow[]` `{status: OrderStatusEnum, count: int}[]`, ordered by count desc |
| `by_payment_method` | `AnalyticsPaymentMethodRow[]` `{payment_method: "online" \| "cod" \| "", orders: int, revenue_paise: int}[]` |
| `top_products` | `AnalyticsProductRow[]` `{product_id: uuid \| null, name: string, quantity: int, revenue_paise: int}[]` — top 10 by revenue from paid orders' items |

Name the payment-method field enum `AnalyticsPaymentMethodEnum` (`online`, `cod`, blank allowed) in `schema_enums.py`. Use the existing enum component for order status from the orders app schema (do not register a duplicate).

### `GET export/?report=messages|templates|campaigns|team|commerce` → `text/csv`

Same range params and the same feature checks as the matching report. Response `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="upchatz-<report>-<from>-<to>.csv"`. Rows: `messages` = the daily series; the others = their `results` (commerce = daily series). Money columns in rupees with two decimals (`revenue_inr`). Cells starting with `=`, `+`, `-`, `@` are prefixed with `'` (CSV injection). Missing or unknown `report` → 400 `invalid`.

## Implementation rules (backend)

- Read-only aggregate queries (`values().annotate()`, `Count`/`Sum` with `filter=`, `TruncDate(..., tzinfo=workspace zone)`) — never loop over rows in Python. Every query filters on the workspace first.
- `apps.analytics` may import these models **read-only** for reporting: `apps.inbox.models`, `apps.campaigns.models`, `apps.contacts.models`, `apps.automations.models`, `apps.orders.models`, `apps.message_templates.models`, `apps.tenants.models`. It never writes to them.
- Cache each report response for 60 s keyed by workspace, report and range (Django cache). Ranges ending before today may be cached for 10 minutes.
- Indexes: add `inbox.Message` index `(workspace, created_at)` named `inbox_msg_ws_created_idx` in a new inbox migration (the one allowed edit outside the analytics and billing paths). Contacts/campaigns indexes only if a query plan needs them — ask the lead first.
- Tests: tenant isolation (`assert_tenant_isolated`), plan gating (Starter 409, Growth 200), commerce gating, range validation (defaults, 92-day cap, future `to`, `from > to`), time-zone day boundaries (a message at 23:30 IST lands on that IST date), status counting definitions, zero-filled series, previous-period totals, CSV headers, filename and injection escaping, query count bounded (no N+1: `django_assert_max_num_queries`).

## Dashboard

Area `features/dashboard/analytics/` (`routes.tsx`, `nav.ts`, `mocks.ts`) at `/app/w/:workspaceId/analytics`, nav label **Analytics**, visible to every role.

- Range control: Last 7 days / Last 30 days (default) / Last 90 days / Custom (two date inputs, max 92 days), stored in the URL query (`?from=&to=`) so links are shareable.
- KPI cards from `overview/` with the change vs the previous period (arrow + percent; no percent when previous is 0). Orders and revenue cards only when not null.
- Messages: stacked/line trend of sent/delivered/read/failed/received from `messages/` using `components/app/charts/LazyTrendChart`; by-source table; by-category table; failure reasons with plain-language labels for common Meta codes (131026 undeliverable, 131047 re-engagement / 24-hour window, 131048 spam rate limit, 131049 per-user marketing limit, 131050 user stopped marketing, 131056 pair rate limit, 130472 experiment) and the raw code otherwise.
- Templates, Campaigns (row links to the campaign detail), Team, Commerce (hidden when the commerce report returns 409) sections or tabs.
- Export CSV button per report (downloads through the authenticated client, not a bare link).
- 409 `feature_not_available` for `analytics` → an upgrade panel linking to billing, no broken charts. Loading skeletons, empty states ("No messages in this period"), error states with retry.
- Rates as percentages with one decimal; money with `formatPaise` from `lib/money.ts`; numbers in Indian grouping (`en-IN`).
- Mocks: seeded realistic Indian demo data for 90 days, consistent across reports; MSW handlers honour `from`/`to`.
- Phone width works (tables scroll or become cards). Tests with `renderDashboard`.
