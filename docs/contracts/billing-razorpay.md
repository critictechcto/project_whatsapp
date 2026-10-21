# Billing through Razorpay (auto-pay and pay once)

UpChatz's own plan billing runs on Razorpay (`BILLING_PROVIDER=razorpay`, the default). The owner chooses at checkout:

- **Auto-pay** (`payment_mode=autopay`): a Razorpay subscription (UPI AutoPay or card mandate) that Razorpay charges each month or year. This is the existing subscription flow, unchanged.
- **Pay once** (`payment_mode=one_time`): a Razorpay order for one month or one year. Nothing is charged automatically; the plan is prepaid like the dormant Cashfree flow ([billing-cashfree.md](billing-cashfree.md)), and the same renewal, reminder and expiry rules apply.

Cashfree stays in the code and works when `BILLING_PROVIDER=cashfree` (pay once only). Sellers' own payment links for orders (`apps.payments`) are unrelated.

## Data model (`apps.billing`)

- `Subscription.prepaid` (bool, default false): true for a pay-once plan of either gateway. A data migration sets it on existing Cashfree plans. `activate()` (Razorpay subscription) sets it false; `fulfil_order` sets it true.
- `BillingOrder.provider` is `razorpay` or `cashfree`; `cf_payment_id` is renamed `payment_id`. `payment_session_id` is Cashfree-only.
- Everything that was keyed on "a Cashfree plan" is keyed on `prepaid`: the renewal check in `fulfil_order`, `billing.expire_prepaid`, `billing.send_renewal_reminders` and cancellation (a prepaid plan has nothing to cancel at the gateway).

## API

- **`CheckoutRequest`** adds optional `payment_mode`: `autopay` | `one_time`. Default `autopay` on Razorpay and `one_time` on Cashfree; `autopay` on Cashfree is 400 `invalid`.
- **`CheckoutSession`** adds `payment_mode`. A Razorpay pay-once session has `provider: "razorpay"`, `key_id`, `order_id` (Razorpay `order_…`), `amount_paise` (what is charged, GST-inclusive when GST is on) and `subscription_id: null`.
- **`CheckoutVerifyRequest`** accepts a third form: `razorpay_payment_id`, `razorpay_order_id`, `razorpay_signature`. The other two forms are unchanged; anything else is 400 `invalid`.
- **`Subscription`** adds `payment_mode`: `autopay` | `one_time` | null (null without a paid plan). `auto_renews` is false for prepaid plans.
- **Switching:** an active auto-pay plan can't check out pay once (409 `subscription_active`). An active pay-once plan can check out pay once again to renew or change plan, but not auto-pay (409 `subscription_active`, "You can switch to auto-pay when your paid period ends.").

## Pay-once flow

1. **Checkout** (owner): the billing profile must be complete (no phone needed). The server creates a Razorpay order (`POST /v1/orders`: `amount` in paise from `checkout_total_paise`, `currency` INR, `receipt` `upc_<32 hex>`, `notes` with `workspace_id`, `plan`, `interval`), stores a `BillingOrder` and returns the session. The subscription is not changed at checkout.
2. **Pay:** the dashboard opens Razorpay Checkout with `order_id` and `amount`.
3. **Verify** (owner): the server checks the Checkout signature (HMAC-SHA256 of `order_id|payment_id` with `RAZORPAY_KEY_SECRET`) and that the order belongs to the workspace (else 400 `payment_verification_failed`), then fetches the order. `paid` fulfils it with the captured payment id; any other status is 409 `payment_not_completed`; Razorpay unreachable is 503 `upstream_unavailable`.
4. **Webhook** (`/webhooks/razorpay/`, existing signature check and `RazorpayEvent` idempotency): `order.paid` for a known Razorpay `BillingOrder` whose amount matches fulfils it; unknown orders are ignored. `payment.failed` is logged.
5. **Fulfil:** as in the Cashfree contract, step 5. The invoice's `payment_provider` is the order's provider.

Razorpay's payment capture setting must be **automatic** so a paid order reaches `paid` without a manual capture.

## Dashboard

- **Plans page:** with `checkout_provider === "razorpay"`, an **Auto-pay / Pay once** choice next to Monthly/Annual, Auto-pay selected by default, with copy for each mode.
- **Subscription card and cancel dialog:** they follow `payment_mode`. A pay-once plan shows "Paid until {date}" and Renew (pay once, same plan and interval).
- **Billing profile:** the phone is required only for Cashfree.
- **Mock mode:** `checkout_provider` is `razorpay` and both modes work.

## Prices come from Razorpay plans

Razorpay is the only source of plan prices. UpChatz stores no price of its own: each `Plan` names a Razorpay plan per interval, and the amount is read from Razorpay. A Razorpay plan can't change after it is created, so a fetched copy (keyed by the Razorpay plan id) can never go stale.

### Data model (`apps.billing`)

- `Plan` drops `monthly_price_paise` and `annual_price_paise` and gains `razorpay_plan_id_monthly` and `razorpay_plan_id_annual` (blank allowed). `Plan.razorpay_plan_id(interval)` is the field, else `RAZORPAY_PLAN_IDS[slug][interval]` (kept as a fallback), else `""`. `DEFAULT_PLANS`/`ensure_default_plans` carry no prices.
- New `RazorpayPlan` (a read-only snapshot): `id` (the Razorpay `plan_…` id, primary key), `plan` (FK `Plan`, null, `SET_NULL`), `interval` (`monthly`|`annual`), `period` and `period_interval` (Razorpay's), `amount_paise` (what Razorpay charges per cycle, GST-inclusive when GST is on), `currency`, `item_name`, `fetched_at`.
- `apps/billing/prices.py`:
  - `razorpay_plan(plan, interval)`: the snapshot for the plan's current id. On a miss it fetches `GET /v1/plans/{id}` and saves it.
    - It checks that the currency is INR and the period matches: monthly needs `monthly`×1; annual needs `yearly`×1 or `monthly`×12.
    - It raises `PlanPriceNotConfigured` when there is no id or the plan doesn't match, and `RazorpayError` when Razorpay can't be reached.
    - A failed fetch is remembered in the Django cache for 60 s, so anonymous traffic can't hammer Razorpay.
  - `price_paise(plan, interval) -> int | None`: the price before GST, worked back from `amount_paise` at the current GST rate. It returns the base whose `invoices.compute_gst(...)` total equals the amount; with GST off it is the amount itself. It returns None when the plan is unavailable and never raises.
  - `Plan.price_paise(interval)` delegates to it and returns `int | None`.
- `plan_for_razorpay_plan_id(id)`, used by the webhooks, looks in this order: a `Plan` field, then a `RazorpayPlan` snapshot (`plan`, `interval`), then `RAZORPAY_PLAN_IDS`. This way, subscriptions on an older Razorpay plan still map to the right plan.
- **Invoices** are worked out from the amount actually charged when it is known: the Razorpay subscription payment's amount, or the `BillingOrder` amount. Only otherwise do they use the plan's current price. Subscribers on an older Razorpay plan get invoices for what they paid.

### Admin

- **Plan form:** name, both Razorpay plan ids, limits, features, active and sort order. There are no price fields.
- **On save**, each non-empty id is fetched and validated. A form error is shown when:
  - the plan isn't found, for example a test id with live keys;
  - the period is wrong;
  - the currency isn't INR;
  - Razorpay can't be reached ("try again").
- **Read-only columns** show the fetched monthly and annual amounts and the Razorpay plan names, plus a hint when an id comes from `RAZORPAY_PLAN_IDS`.
- `RazorpayPlan` is listed read-only.

### API

- **`Plan.monthly_price_paise` and `annual_price_paise`** become nullable: the price before GST, or null when that interval can't be bought, either because no Razorpay plan is set or because Razorpay couldn't be reached and nothing is cached.
- **Checkout** of an interval without a price:
  - 409 `plan_unavailable` ("This plan can't be bought right now.") when it is not configured;
  - 503 `upstream_unavailable` when Razorpay is unreachable.

  This applies to both payment modes. Pay once charges `compute_gst(price)`, the same amount as the Razorpay plan.
- **New public endpoint `GET /api/v1/billing/public-plans/`** (operation id `billing_public_plans_list`):
  - No authentication and no workspace header. `AllowAny`, throttled per IP with scope `public_plans` (60/min).
  - Returns `{"gst_rate_percent": int, "plans": Plan[]}` for active plans in `sort_order`.
  - Headers: `Access-Control-Allow-Origin: *` (never with credentials) and `Cache-Control: public, max-age=300`.

### Website and dashboard

- **`config/site.ts`** keeps the marketing copy per plan (blurb, limits text, feature list, recommended) but no prices. `ANNUAL_MONTHS_CHARGED` is removed.
- **Landing pricing:** after hydration, the section fetches `public-plans` from `VITE_PRICING_API_URL`. When that is unset in live mode it uses `VITE_API_URL`; in mock mode without it there is no fetch and the placeholder shows.
  - Until prices arrive, or if the fetch fails, each card shows a placeholder instead of a number, with a note that prices are shown after sign-up.
  - The annual toggle's "N months free" is computed from the fetched prices and left out when they're unknown.
  - The server and the first client render are identical (no fetch during render).
- **CSP:** `scripts/csp.mjs` adds the pricing origin to `connect-src`. The Pages workflow sets `VITE_PRICING_API_URL=https://app.upchatz.com`.
- **Terms page:** no longer lists prices. It points to the pricing page and the dashboard.
- **Dashboard Plans page:** an interval without a price shows "Not available" and can't be checked out. "N months free" is computed per plan from its two prices.
