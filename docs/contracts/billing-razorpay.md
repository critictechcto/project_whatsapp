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
