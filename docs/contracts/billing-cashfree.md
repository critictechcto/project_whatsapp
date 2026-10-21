# Billing through Cashfree (prepaid plans)

> **Dormant.** Plan billing moved to Razorpay (auto-pay and pay once): see [billing-razorpay.md](billing-razorpay.md). This flow still works when `BILLING_PROVIDER=cashfree`. Where this document says a rule applies to a "Cashfree plan", it now applies to every prepaid (`one_time`) plan.

UpChatz's own subscription billing can run on **Cashfree Payment Gateway orders** (prepaid, no auto-debit) or on the existing **Razorpay subscriptions**. `BILLING_PROVIDER` (`cashfree` | `razorpay`, default `cashfree`) picks the gateway for **new checkouts**. Existing Razorpay subscriptions keep working through `/webhooks/razorpay/` whatever the setting. Sellers' own Razorpay/Cashfree payment links for orders (`apps.payments`) are unrelated and unchanged.

## Settings (`config/settings/base.py`)

| Setting | Env | Notes |
|---|---|---|
| `BILLING_PROVIDER` | `BILLING_PROVIDER`, default `cashfree` | `cashfree` or `razorpay`; anything else raises `ImproperlyConfigured` |
| `CASHFREE_ENV` | `CASHFREE_ENV`, default `sandbox` | `sandbox` or `production`; anything else raises `ImproperlyConfigured` |
| `BILLING_CASHFREE_APP_ID`, `BILLING_CASHFREE_SECRET` | sandbox: `TEST_CASHFREE_API_APP_ID`, `TEST_CASHFREE_API_SECRET`; production: `CASHFREE_API_APP_ID`, `CASHFREE_API_SECRET` | chosen by `CASHFREE_ENV` |
| `CASHFREE_TIMEOUT` | `CASHFREE_TIMEOUT`, default `20` | seconds |
| `BILLING_GST_ENABLED` | `BILLING_GST_ENABLED`, default `false` | Off while UpChatz isn't GST-registered: the rate is 0, so the order amount and invoice total are the plan price and the checkout description has no "+ GST". On: `BILLING_GST_RATE_PERCENT` applies. |

Use the **sandbox (test) keys until the owner says otherwise**. Missing keys never stop settings from loading; checkout returns 503 `upstream_unavailable` instead.

## Shared Cashfree helpers (`common/cashfree.py`)

- `API_VERSION = "2026-01-01"`; base URLs `sandbox` → `https://sandbox.cashfree.com/pg`, `production` → `https://api.cashfree.com/pg`.
- `CashfreeError(message, *, status_code=None, retryable=False)`.
- `CashfreeTransport(client_id, client_secret, mode, timeout=None, transport=None)`, an httpx client with `.request(method, path, json=None, params=None, headers=None)`. It sends `x-client-id`, `x-client-secret` and `x-api-version`, and maps HTTP errors to `CashfreeError`, retryable on 429/5xx/network errors. Never log the secret.
- `webhook_signature_is_valid(raw_body: bytes, timestamp: str | None, signature: str | None, secret: str) -> bool`, which checks base64(HMAC-SHA256(secret, timestamp + raw body)) with `hmac.compare_digest`. False when any part is missing.

## Flow

1. **Checkout** (`POST /api/v1/billing/subscription/checkout/`, owner):
   - Validate the plan. The billing profile must be complete **and have a phone**, otherwise 409 `billing_profile_required`, with a message that mentions the phone.
   - Create a Cashfree order (`POST /orders`):
     - `order_id` is `upc_<32 hex>`, also sent as `x-idempotency-key`.
     - `order_amount`: rupees with 2 decimals, the **GST-inclusive total** from `invoices.compute_gst` for the buyer's state. This is exactly what the invoice says.
     - `order_currency` is `INR`.
     - `customer_details`: `customer_id` = workspace UUID hex, `customer_phone` (10 digits for +91 numbers), `customer_email`, `customer_name` = legal name.
     - `order_meta.return_url` = `{FRONTEND_URL}/app/w/{workspace_id}/billing?cf_order_id={order_id}`.
     - `order_meta.notify_url` = `{PUBLIC_API_BASE_URL}/webhooks/cashfree/billing/`.
     - `order_expiry_time`: now + 1 hour, ISO 8601 in IST.
     - `order_note`: the checkout description.
     - `order_tags`: `workspace_id`, `plan`, `interval`.
   - Store a `BillingOrder`. The subscription's status is **not** changed at checkout.
   - **While active:** checkout is allowed for a Cashfree-paid subscription. That is how a prepaid plan is renewed or changed. It stays 409 `subscription_active` for an active Razorpay subscription.
2. **Pay:** the dashboard opens Cashfree Checkout (JS SDK v3, `redirectTarget: "_modal"`) with `payment_session_id` and `mode`.
3. **Verify** (`POST /api/v1/billing/subscription/verify/` with `{"order_id"}`, owner):
   - The server fetches `GET /orders/{order_id}`.
   - `PAID` fulfils the order and returns the `Subscription`.
   - `ACTIVE`, `EXPIRED` or `TERMINATED*` return 409 `payment_not_completed` ("The payment wasn't completed. You haven't been charged.").
   - An unknown order, or one from another workspace, returns 400 `payment_verification_failed`.
   - If Cashfree is unreachable: 503 `upstream_unavailable`.
   - **Redirect fallback:** when the browser was sent to the return URL (in-app browsers), the billing page sees `?cf_order_id=` and calls verify once.
4. **Webhook** (`POST /webhooks/cashfree/billing/`, public, not in OpenAPI):
   - Verify `x-webhook-signature` against `x-webhook-timestamp` + the raw body, using `BILLING_CASHFREE_SECRET`. Invalid → 400 `invalid_signature`.
   - `PAYMENT_SUCCESS_WEBHOOK` whose `data.payment.payment_status == "SUCCESS"` for a known `BillingOrder` with matching `data.order.order_amount` fulfils it.
   - `PAYMENT_FAILED_WEBHOOK` and `PAYMENT_USER_DROPPED_WEBHOOK` are only logged.
   - Unknown orders and types return 200 `{"status": "ignored"}`, so Cashfree doesn't retry.
   - The owner also sets this URL in the Cashfree dashboard (Developers → Webhooks).
5. **Fulfil** (idempotent: the `BillingOrder` row is locked and an already-paid order is a no-op):
   - The payment id is the `cf_payment_id` of the SUCCESS payment, from the webhook or from `GET /orders/{order_id}/payments`.
   - **Period:**
     - When the subscription is active, Cashfree-paid, on the **same plan and interval**, and `current_period_end > now`, the new period runs `current_period_end` → +30 days (monthly) or +365 days (annual). `current_period_start` stays.
     - Otherwise the plan starts now: `current_period_start = now`, `current_period_end = now + 30 or 365 days`.
   - Set `plan`, `interval`, `status=active`, `provider=cashfree`, `cancel_at_period_end=False` and `activated_at` (if empty). Clear `checkout_plan` and `checkout_interval`.
   - Issue the GST invoice with `create_paid_invoice`, keyed on the payment id.
   - Mark the order paid (`paid_at`, `cf_payment_id`, `period_start`, `period_end`), then clear the entitlements cache.
6. **Cancel**:
   - A Cashfree subscription has nothing to cancel at the gateway.
   - `at_period_end=true` sets `cancel_at_period_end`.
   - `false` sets `cancelled` now.
   - Trials work as they do today.
7. **Period end** (beat task `billing.expire_prepaid`, hourly):
   - Active Cashfree subscriptions with `current_period_end <= now` become `expired`, or `cancelled` if they were `cancel_at_period_end`.
   - Halted, cancelled or expired leave no quota, the same as today.
8. **Renewal reminders** (beat task `billing.send_renewal_reminders`, daily at 09:00 IST):
   - For active Cashfree subscriptions without `cancel_at_period_end`, email the owner and the billing-profile email **7 days and 1 day** before `current_period_end`.
   - Use template `billing_renewal_reminder` via `common.mail.send_templated_email`, queued on commit.
   - Each reminder is sent once per period: `Subscription.renewal_reminder_key = "<period_end iso>:<days>"`.
   - The email links to `{FRONTEND_URL}/app/w/{id}/billing/plans`.

## Data model (`apps.billing`)

- **`Subscription`**:
  - `provider` (`razorpay` | `cashfree`, blank by default; set when a paid plan starts; existing rows with a `razorpay_subscription_id` get `razorpay` in a data migration).
  - `renewal_reminder_key` (CharField 64, blank).
- **`BillingOrder(TenantScopedModel)`**:
  - `provider` (`cashfree`), `order_id` (unique), `plan` FK, `interval`, `amount_paise` (GST-inclusive), `status` (`created` | `paid` | `failed` | `expired`).
  - `payment_session_id` (blank after paid), `cf_payment_id`, `paid_at`, `period_start`, `period_end`, `created_at`.
- **`Invoice`**: rename `razorpay_payment_id` → `payment_id` (still unique, nullable) and add `payment_provider` (`razorpay` | `cashfree`). `razorpay_invoice_id` stays.
- **`BillingProfile`**: `phone` (CharField 16, blank). E.164 is stored, and the serializer accepts an Indian 10-digit number or E.164. It is optional in the API but required for a Cashfree checkout.

## API changes (`docs/contracts/wave-2.md` billing section follows this)

- **`Subscription`** adds:
  - `provider`: `razorpay` | `cashfree` | null (null on a trial).
  - `auto_renews`: bool. True for an active Razorpay subscription without `cancel_at_period_end`; always false for Cashfree.
  - `gst_rate_percent`: int, the GST rate added at checkout (0 when `BILLING_GST_ENABLED` is off). The dashboard shows "+ N% GST" only when it is above 0, and hides the invoice tax columns when no listed invoice has tax.
  - `checkout_provider`: `razorpay` | `cashfree`, the current `BILLING_PROVIDER`.
- **`CheckoutSession`** becomes:
  - `provider` (`razorpay` | `cashfree`), `name`, `description`, `prefill`.
  - Razorpay: `key_id`, `subscription_id` (null for Cashfree).
  - Cashfree: `order_id`, `payment_session_id`, `mode` (`sandbox` | `production`) (null for Razorpay).
  - `amount_paise` (GST-inclusive; null for Razorpay).
- **`CheckoutVerifyRequest`**: either `order_id` (Cashfree) or the three `razorpay_*` fields (all optional in the schema). Anything else is 400 `invalid`.
- **`BillingProfile`** adds `phone` (optional, blank allowed).
- **New error codes:** `payment_not_completed` (409).
- **Mock mode (MSW):** `checkout_provider` is `cashfree`. Checkout returns a Cashfree session, the mock Cashfree checkout resolves immediately (no SDK, like the Razorpay mock), and verify marks the plan active with an invoice.

## Dashboard

- **Checkout:** `useCheckout` branches on `session.provider`. `lib/integrations/cashfree.ts` loads `https://sdk.cashfree.com/js/v3/cashfree.js` lazily, calls `Cashfree({ mode }).checkout({ paymentSessionId, redirectTarget: "_modal" })`, then always calls verify, which tells the truth.
  - `payment_not_completed` → toast "Payment not completed".
- **Plans page:** the copy is provider-aware. For Cashfree: "Payments are processed by Cashfree. You pay for a month or a year at a time; nothing is charged automatically. We'll email you before your plan ends."
- **Subscription card:**
  - For Cashfree: "Paid until {date}" with a **Renew** button (checkout for the same plan and interval).
  - A notice in the last 7 days.
  - Changing plan while active warns: "Your new plan starts now. Unused days on the current plan aren't refunded."
  - Razorpay copy stays for Razorpay subscriptions.
- **Billing profile form:** a phone field, required in the form ("Cashfree needs a phone number for payment receipts").
- **CSP (`scripts/csp.mjs`, live builds only):** add Cashfree next to Razorpay — script `https://sdk.cashfree.com`; frame and connect for the Cashfree checkout hosts (check what the SDK loads: `sdk.cashfree.com`, `api.cashfree.com`, `sandbox.cashfree.com`, `payments.cashfree.com`, …). Update `src/csp.test.ts`.
