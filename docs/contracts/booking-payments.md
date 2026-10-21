# Booking payments: advance or full payment per service

Extends [services-and-offers.md](services-and-offers.md). Today a booking is paid online in full or at the shop, and "pay at the shop" is a store-wide switch. Sellers can now require, per service, an **advance** (part now, the balance at the shop) or **full payment** online. Money still goes to the seller's own Razorpay or Cashfree account through the existing payment links. UpChatz never holds it, and refunds are the seller's.

## Catalog (`apps.catalog`)

`Product` gains three fields, used only when `kind = service`:

| Field | Type | Notes |
|---|---|---|
| `booking_payment` | `store_default` \| `advance` \| `full`, default `store_default` | Products are always `store_default`. |
| `advance_type` | `amount` \| `percent` \| blank | Required with `advance`, blank otherwise. |
| `advance_value` | positive int, null | Required with `advance`. `amount` is in paise (at least 100, and less than the effective price). `percent` runs 1–99. Null otherwise. |

- Validation errors go through `kind_field_errors()`, so the API, writes and CSV import share them; there is a DB check constraint as well. Products sent with anything other than `store_default` get 400 `invalid`.
- The fields appear on `ProductSerializer` and `ProductWriteSerializer`, with enums `BookingPaymentEnum` and `AdvanceTypeEnum`.
- **Advance per line:** `amount` gives `advance_value × quantity`. `percent` gives `ceil(line_total × advance_value / 100)`.

## Store settings (`apps.orders.StoreSettings`)

- `booking_cancellation_policy`: text, at most 300 characters, blank by default, editable through `PATCH /api/v1/store/settings/` (`SIMPLE_FIELDS`).
- When set, the booking payment prompt shows it as "Cancellation policy: …".

## Order (`apps.orders.Order`)

- **New fields:**
  - `advance_paise`: int, default 0. The advance a booking must pay, fixed at the payment step.
  - `amount_paid_paise`: int, default 0. The total received online so far.
- **Read-only property** `balance_due_paise = max(total_paise − amount_paid_paise, 0)`, and 0 once the order is `paid`, `cod_collected` or `refunded_manual`.
- `mark-refunded` also accepts `advance_paid`. Analytics revenue counts a booking only once it is fully paid (`paid` or `cod_collected`).
- All three appear on the order serializers (list item and detail).
- `PaymentStatus` gains `advance_paid` ("Advance paid").
- **Existing paid flows:** a full online payment sets `amount_paid_paise = total_paise`. Collecting a pay-at-shop booking or a COD order doesn't touch `amount_paid_paise`, because that field counts online money only.

## Checkout (booking payment step)

**The requirement for a booking cart is the strictest across its lines:** `full`, then `advance`, then `store_default`.
- **Advance amount:** the sum of the line advances, capped at `total_paise − 100`.
- **Advance at or above the total:** if the line advances reach `total_paise` or more, the requirement becomes `full`.
- **When it is decided:** in `start_checkout`, and recomputed whenever totals change (for example when an offer is applied). It is stored in `advance_paise`, which is 0 unless the requirement is `advance`.

**What each requirement offers:**

| Requirement | Buttons (reply ids) | Without online payments |
|---|---|---|
| `store_default` | Unchanged: *Pay online* (`upc:chk:pay:<id>:online`), *Pay at the shop* (`…:shop`, when `pay_at_shop_enabled`), *Cancel* | As today |
| `advance` | *Pay ₹A advance* (`upc:chk:pay:<id>:advance`), *Pay ₹T in full* (`…:online`), *Cancel*. Body: summary + "Pay ₹A now to book. The rest, ₹B, is paid at the shop." | `start_checkout` rejects with `payment_unavailable` |
| `full` | *Pay online* (`…:online`), *Cancel*. Body: summary + "Full payment is needed to book." | `start_checkout` rejects with `payment_unavailable` |

- **`payment_unavailable` copy** for `advance` and `full`: "This service needs online payment to book, and the store can't take online payments right now. Please contact the store."
- **Reply validation:** stale or no-longer-allowed choices (`shop` when the requirement isn't `store_default`, `advance` when it isn't `advance`) get the existing stale text.
- **Cancellation policy:** the policy line is appended to the payment prompt body whenever it is set.

**Choosing advance:**
- It is like *Pay online*, but the payment link amount is `advance_paise`.
- `payment_method` is `online`.
- `PAYMENT_LINK_CREATED` records the amount. The link button reads "Pay ₹A".
- *Try again* after a failed or expired link keeps the chosen kind (advance or full). Store the kind on the order, e.g. `pay_advance: bool`.

**When the link is paid** (`on_payment_link_paid`):
1. Add the event's `amount_paise` to `amount_paid_paise`.
2. If `amount_paid_paise >= total_paise`, set `paid`; otherwise set `advance_paid`.
3. Then the existing transitions apply: the checkout becomes `requested`, with the existing revive, flag and idempotency rules.

A paid amount below the link amount never reaches here; the payments app already rejects it.

## Balance at the shop

- **Endpoint:** `POST /api/v1/orders/{id}/mark-balance-paid/` (`orders.services.mark_balance_paid(order, *, actor, user=None)`), with the same roles as `mark-cod-collected`.
- **Allowed** when `payment_status = advance_paid` and the status is `confirmed` or `completed`; otherwise 409 `invalid_order_transition`.
- **Effect:** sets `paid` and `cod_collected_at = now`, records event `BALANCE_COLLECTED` ("Balance ₹B paid at the shop."), then calls `payment_changed()`.
- `amount_paid_paise` stays the online total.

## Messages

**Buyer labels** (`orders/buyer.py`): `advance_paid` reads "Advance ₹A paid, ₹B at the shop".

**`booking_payment_note`** (reminders, template param and session text):

| Booking | Note |
|---|---|
| Pay at the shop, `cod_pending` | "Pay at the shop after your service: ₹X." (unchanged) |
| `advance_paid` | "Advance ₹A paid. Pay the rest, ₹B, at the shop." |
| `paid` or `cod_collected` | "Your booking is paid." |
| anything else | "Payment pending." (This fixes unpaid bookings being told they are paid.) |

**Cancelled booking with `advance_paid`:** "The store will contact you about your advance." Paid bookings keep "The store will refund your payment."

**Seller alerts** (`seller_alerts/content.py` `payment_label`): `advance_paid` reads "Advance ₹A paid, ₹B at the shop". No new Meta templates are needed.

## Dashboard

**Catalog service form** (`ProductEditorPage`):
- **Payment at booking:**
  - Choices: "Use store setting" (default), "Advance payment", "Full payment".
  - Advance has a ₹ amount / % toggle and a value field.
  - Hint: "Buyers pay this online when they book; the rest at the shop."
  - When online payments aren't connected, a warning links to Store → Payments: "Buyers can't book this service until online payments are set up."
- **Wording for services:**
  - *Availability* becomes **Bookings: Open / Paused** (the same `in_stock` / `out_of_stock` values).
  - *Max quantity per order* becomes **Max people per booking** (hint "For example 2 lets a buyer book for two people.").
  - Products are unchanged.
- **Service cards** in the catalog list show "Advance ₹200", "Advance 20%" or "Full payment" when set.

**Store → Bookings:** a "Cancellation policy" textarea (300 chars), with the hint "Shown to buyers before they pay."

**Orders:**
- **Badges:** `PaymentBadge` handles `advance_paid` ("Advance paid").
- **Payment card:** shows "Paid online ₹A" and "Balance due ₹B".
- **New action:** "Mark balance paid" (confirm dialog "Mark the ₹B balance as paid at the shop?"), offered when `advance_paid` and `confirmed`/`completed`.
- **Elsewhere:** filters and labels include the new status; the realtime event types too.

**Mocks:** seeded services include one with a 20% advance and one with full payment; mock checkout and the orders handlers support `mark-balance-paid`.
