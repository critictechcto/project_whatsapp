# Contract: services (bookings) and offer codes

Agents build against this document. Conventions from `docs/contracts/wave-2.md` and `docs/contracts/wave-3-commerce.md` apply (errors, roles, `X-Workspace-ID`, paise, reply-id grammar, idempotent receivers). Adding optional response fields is allowed; renaming, removing or retyping needs a lead request.

## Summary

- A catalog item is a **product** (delivered) or a **service** (booked). One store can list both.
- A bot cart holds products **or** services, never both, so an order is a **delivery** or a **booking**.
- Booking checkout has no address step: the buyer picks a **day**, then a **time window**, then pays online now or **at the shop** (after the service). The order becomes a **booking request**; the seller confirms the exact time. The buyer gets a confirmation and a reminder.
- **Offer codes**: a seller creates a code (e.g. `DIWALI`). A buyer who sends exactly the code gets the offer reply and a **claim** is recorded (with the Click-to-WhatsApp ad source when present). The buyer's next checkout applies the discount. Staff can **redeem** a claim at the counter, which also counts walk-ins who never ordered on WhatsApp.

## Ownership

| Owner | Scope |
|---|---|
| `apps.catalog` | `Product.kind`, `Product.duration_minutes`, services skipping stock and native sync |
| `apps.shop` | cart kind rule, service wording in cards, skipping offer-code messages |
| `apps.orders` | booking fields, statuses, checkout day/window/payment steps, pay at shop, discount on totals, booking notifications and reminders, store booking settings, `apply_offer_to_active_checkout` |
| `apps.offers` (new) | `OfferCode`, `OfferClaim`, inbound code matching and reply, discount maths, claim lifecycle, offers API and stats |
| `apps.seller_alerts` | `new_booking` alert and its *Accept* / *Cancel* actions |
| Dashboard | `catalog/`, `store/`, `orders/` (services and bookings); new area `offers/` |

New allowed cross-app imports: `apps.orders` and `apps.shop` may import `apps.offers.services`; `apps.offers` may import `apps.orders.services`/`models`, `apps.catalog.models`, `apps.contacts.models`/`services`, `apps.inbox.models`/`sending`/`interactive`, `common.commerce`. `apps.seller_alerts` keeps using `apps.orders.services`.

## Enums (register in each app's `schema_enums.py`)

| Component | Values |
|---|---|
| `ProductKindEnum` | `product`, `service` |
| `OrderKindEnum` | `delivery`, `booking` |
| `OrderStatusEnum` (extended) | adds `awaiting_time`, `requested`, `completed`, `no_show` |
| `PaymentMethodEnum` (extended) | adds `pay_at_shop` |
| `OrderEventTypeEnum` (extended) | adds `time_requested`, `appointment_set`, `reminder_sent`, `offer_applied`, `offer_removed` |
| `AlertEventEnum` (extended) | adds `new_booking` |
| `OfferDiscountTypeEnum` | `none`, `percent`, `amount` |
| `OfferAppliesToEnum` | `all`, `products`, `services` |
| `OfferClaimStatusEnum` | `claimed`, `applied`, `redeemed`, `expired` |

Stages: `checkout` adds `awaiting_time`; `open` adds `requested`; `closed` adds `completed` and `no_show`.

## Catalog

`Product` gains:

| Field | Type | Rules |
|---|---|---|
| `kind` | `ProductKindEnum`, default `product` | writable |
| `duration_minutes` | int or null | services only (5–600); must be null for products |

Services: `stock_qty` must be null (400 `validation_error` on `stock_qty` otherwise) and are always available (`price_items` never drops them for stock; `reserve_stock`/`release_stock` skip them). Native catalog sync skips services and removes a product from Meta when it becomes a service. `price_items` results expose `line.product.kind`.

## Orders

### `Order` fields (all in the `Order` serializer, read-only)

| Field | Type |
|---|---|
| `kind` | `OrderKindEnum` (set at checkout from the items) |
| `requested_date` | date or null |
| `requested_window` | `{label, start, end}` (`HH:MM`) or null |
| `appointment_at` | datetime or null (set when the seller confirms) |
| `reminder_sent_at` | datetime or null |
| `discount_paise` | int, default 0 |
| `offer_code` | string, "" when none (snapshot of the code text) |
| `offer_claim_id` | uuid or null |

Totals: `total_paise = subtotal_paise − discount_paise + shipping_paise (+ cod_fee_paise for COD)`. Bookings have no shipping and no COD fee. `address` is null for bookings.

### Transitions

- Delivery orders: unchanged.
- Booking checkout: `awaiting_confirmation` (price changed) → `awaiting_time` → `awaiting_payment_method` → `pending_payment` (online) → `requested`; choosing *Pay at the shop* goes straight to `requested` with `payment_method=pay_at_shop`, `payment_status=cod_pending`. Online payment confirmed → `requested` with `payment_status=paid`.
- Booking open/closed (merchant): `requested → confirmed | cancelled`; `confirmed → completed | no_show | cancelled`. `needs_attention → requested | cancelled` for bookings. `packed`/`shipped`/`delivered` are not allowed for bookings, `requested`/`completed`/`no_show` not for deliveries.
- `confirmed` for a booking requires `appointment_at` (see confirm action).
- Expiry of checkouts includes `awaiting_time`.

### Merchant API (in `OrderViewSet`, write role agent, same as other order actions)

- `POST /api/v1/orders/{id}/confirm-booking/` body `{appointment_at}` (datetime, required): sets `appointment_at`, clears `reminder_sent_at`, moves `requested → confirmed`, or on an already `confirmed` booking changes the time (event `appointment_set`). Buyer notified each time. 409 `invalid_transition` otherwise.
- `POST /api/v1/orders/{id}/transition/` accepts `completed` and `no_show` for bookings.
- `POST /api/v1/orders/{id}/mark-cod-collected/` also works for `pay_at_shop` bookings in `confirmed` or `completed` ("Mark paid at shop").
- Orders list filter `kind=delivery|booking`.
- `orders.services.confirm_booking(order, *, appointment_at, actor, user=None)` is the shared implementation (seller alerts *Accept* uses it with `appointment_at` = the window start on `requested_date` in the workspace time zone).

### Checkout (WhatsApp)

New `chk` actions (existing scope, no grammar change):

| Reply id | Meaning |
|---|---|
| `upc:chk:day:<order_id>:<yyyymmdd>` | day picked (list message of the next `booking_days_ahead` open days, today included while a window is still ahead) |
| `upc:chk:win:<order_id>:<index>` | window picked (index into `booking_windows`; today's past windows are not offered) |

A stale or no-longer-valid day/window resends the day list (or the stale text when the order left `awaiting_time`). Payment choice for bookings: *Pay online* (when online payments are ready), *Pay at the shop* (when `pay_at_shop_enabled`), *Cancel*. If neither is available the store cannot take bookings: `start_checkout` rejects with the existing `CheckoutRejected` reason `payment_unavailable`.

### `StoreSettings` additions (store settings API, admin)

| Field | Type | Default |
|---|---|---|
| `pay_at_shop_enabled` | bool | true |
| `booking_days` | list of ints 0–6 (Mon=0) | `[0,1,2,3,4,5,6]` |
| `booking_windows` | list of `{label (≤24), start, end}` `HH:MM`, 1–10, start < end | Morning 09:00–12:00, Afternoon 12:00–16:00, Evening 16:00–20:00 |
| `booking_days_ahead` | int 1–30 | 7 |
| `booking_reminder_hours` | int 0–48 (0 = off) | 3 |
| `booking_confirmed_template_id`, `booking_cancelled_template_id`, `booking_reminder_template_id` | uuid or null | null |

Starter templates (`starter-templates` endpoint): `upc_booking_confirmed`, `upc_booking_cancelled`, `upc_booking_reminder` (utility). Checklist: a `booking_templates` step appears only when the workspace has an active service.

### Buyer notifications

Bookings notify on `confirmed` (with the appointment time), time changed, `cancelled`, and a reminder `booking_reminder_hours` before `appointment_at` (beat task `orders.send_booking_reminders` every 10 min, once per appointment via `reminder_sent_at`). Session message inside the window, otherwise the mapped template; skipped (event `notification_failed`) when no template is mapped.

### Offers hook in checkout

- `start_checkout` calls `offers.apply_to_checkout(order)` after items and subtotal are set; it stores the returned discount on the order and shows "`<CODE>` −₹X" in the summary/payment prompt. Event `offer_applied`.
- `orders.services.apply_offer_to_active_checkout(conversation_id) -> bool`: offers calls it after recording a new claim. If the contact has a checkout in `awaiting_confirmation`, `awaiting_address`, `awaiting_time` or `awaiting_payment_method`, it applies the offer, saves totals and (only in `awaiting_payment_method`) resends the payment choice with the new total. Returns whether it applied.
- Text that `offers.match_code(...)` recognises is never treated as a typed address or quantity (shop and checkout skip it).

## Offers (`apps.offers`, plan feature `commerce`)

### Models

`OfferCode` (TenantScopedModel): `code` (2–20 chars `[A-Za-z0-9_-]`, stored upper-case, unique per workspace), `title` (≤60), `reply_text` (≤900), `discount_type`, `discount_value` (percent 1–90, or paise ≥100; 0 for `none`), `max_discount_paise` (null = no cap, percent only), `min_order_paise` (default 0), `applies_to`, `starts_at`/`ends_at` (nullable), `max_uses` (null = unlimited; counts `applied` + `redeemed` claims), `max_uses_per_contact` (default 1), `is_active`.

`OfferClaim` (TenantScopedModel): `offer` FK, `contact` FK, `conversation` FK (null for counter-only), `message` FK to `inbox.Message` (null for counter-only), `wamid` (unique with offer when set; makes webhook retries no-ops), `status`, `order` FK (null), `discount_paise`, `bill_paise` (null; entered at the counter), `ad_source_id`, `ad_source_url`, `ad_headline`, `ctwa_clid` (from `Message.payload["referral"]`, "" when absent), `redeemed_at`, `redeemed_by` FK user (null).

### Services (`apps.offers.services`, the import surface)

```python
def match_code(workspace_id, text: str | None) -> OfferCode | None
    # whole-message match after normalisation (trim, casefold, strip edge punctuation), active and within dates
def apply_to_checkout(order) -> AppliedOffer | None
    # latest claimed (or already applied to this order) claim of order.contact; checks dates, applies_to vs
    # order.kind, min_order on subtotal, max_uses; marks it applied to the order; returns
    # AppliedOffer(claim_id, code, discount_paise). Never raises for an invalid offer: returns None.
def release_for_order(order) -> None   # also driven by OrderStatusChanged; claim back to claimed
@dataclass(frozen=True) class AppliedOffer: claim_id: UUID; code: str; discount_paise: int
```

Discount: percent → `floor(subtotal × pct / 100)`, capped at `max_discount_paise`; amount → `min(value, subtotal − 100)` (never below ₹1 to pay).

### Inbound

A registered commerce claimer (`common.commerce.register_message_claimer`) claims inbound text that `match_code` recognises, so automations skip it. The receiver (on `MessageRecorded`, inbound, queued task) records the claim once per wamid, enforces `max_uses_per_contact` (a repeat send just re-sends the reply), and replies with `apps.inbox.sending` (source `commerce`, `source_ref` `offer:<code_id>`): `reply_text` plus, when the store is enabled and has shoppable items, reply buttons *Book now*/*Shop now* (`upc:shop:browse`) and *Menu* (`upc:shop:menu`). Then it calls `orders.services.apply_offer_to_active_checkout`. Codes must not equal a shop menu keyword, a consent keyword or a locked opt-out keyword (400 `validation_error` on `code`).

### Claim lifecycle (receiver on `OrderStatusChanged`)

- order `cancelled`/`expired` (or offer removed) → claim back to `claimed`, order cleared.
- order `delivered` with `paid`/`cod_collected`, or booking `completed` → `redeemed` (`redeemed_at` now, `bill_paise` = order total).
- claims of an offer past `ends_at` that were never applied are shown as `expired` (computed nightly by beat `offers.expire_claims`).

### API (`/api/v1/offers/`, read viewer, write admin, redeem agent)

| Endpoint | Notes |
|---|---|
| `GET/POST codes/`, `GET/PATCH/DELETE codes/{id}/` | `OfferCode` + read-only counters `claims_count`, `redeemed_count` |
| `GET codes/{id}/stats/` | `{claims, from_ads, applied, redeemed, discount_paise, revenue_paise, daily: [{date, claims, redeemed}]}`; `revenue_paise` = sum of redeemed `bill_paise` |
| `GET claims/` | filters `offer`, `status`, `phone` (contains); cursor pagination; includes contact summary, order id/number |
| `POST claims/{id}/redeem/` | body `{bill_paise?}`; claimed/applied → redeemed; 409 `invalid_transition` if already redeemed |
| `POST redeem/` | body `{code, phone, bill_paise?}`: finds the contact's open claim for that code, else creates a counter claim (contact created via `contacts.services` if new), then redeems; 409 `offer_unavailable` when inactive/out of dates/limits reached |

Deleting a code with claims is 409 `offer_in_use` (deactivate instead).

## Seller alerts

`new_booking` fires when a booking reaches `requested` from a checkout status. Platform template `upc_new_booking` (order number, buyer, services, requested day and window, payment) with buttons *Accept* (`upc:alerts:accept:<order_id>`) → `orders.services.confirm_booking` at the window start, and *Cancel* (existing cancel flow). `new_order` no longer fires for bookings. `sync_platform_templates` creates the template.
