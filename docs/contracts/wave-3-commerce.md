# Wave 3 contract: Sell on WhatsApp

Every wave-3 agent builds against this document; the product flow and rules are in the wave-3 plan summary below. Backend agents implement it. Frontend agents consume it through the generated OpenAPI types (`backend/openapi.yml` → `frontend/src/api/schema.d.ts`). A lead request is needed to rename something, remove a field or change a type; adding optional response fields is allowed. Conventions from `docs/contracts/wave-2.md` still apply (errors, cursor pagination, roles, no PUT, UUID ids, `Idempotency-Key`).

## Summary

A seller's buyers browse, order, pay and track orders inside WhatsApp on the seller's own connected number (Cloud API). There are two ways to shop, and both lead to the same checkout:

- **Bot mode** (every seller): menus, collection lists and product cards made of interactive messages. The cart is kept on the server.
- **Native catalog mode**: the seller connects a Meta catalog that we sync from our products. Buyers use WhatsApp's own cart, which arrives as an `order` message.

Checkout: re-price from the database → confirm when the price changed → address (`address_message`, or text as a fallback) → payment choice. Buyers pay online through a payment link created on the **seller's own** payment gateway account (Razorpay or Cashfree: the seller pastes API keys and sets up nothing else), or choose cash on delivery (COD). UpChatz never holds buyer money. The seller moves orders forward by hand (packed, shipped with courier and AWB, delivered); each change notifies the buyer.

Sellers get alerts on their personal WhatsApp from the **UpChatz alerts number** (`PLATFORM_WA_*`) and can act from there: *Mark packed*, *Mark shipped* (then send the courier and AWB), *Cancel*, and the commands `ORDERS` and `HELP`.

Money is integer **paise**, prices include GST, and the currency is `INR`.

## New apps and ownership

| App | Owns |
|---|---|
| `apps.catalog` | `Product`, `Collection`, `MetaCatalog`, image upload, CSV import, Meta catalog sync, commerce settings |
| `apps.shop` | Buyer bot: `BotSession` (per conversation: state, cart lines, paging, expiry), menus, native `order` intake, "My orders" entry |
| `apps.orders` | `Order`, `OrderItem`, `OrderEvent`, `ShopperAddress`, `OrderCounter`, `StoreSettings`; checkout, transitions, buyer notifications, expiry, merchant and store API |
| `apps.payments` | `PaymentAccount` (per workspace, encrypted secrets), `PaymentLink` (outbox), provider interface with Razorpay and Cashfree, payment confirmation (buyer return + polling, optional per-seller webhook) |
| `apps.seller_alerts` | `AlertRecipient`, the platform number client, platform templates, alerts, seller commands |

All five are registered in `LOCAL_APPS` and mounted in `config/urls.py` (lead). `apps.shop` has no REST API.

## Enum component names (register in each app's `schema_enums.py`)

| Component | Values |
|---|---|
| `ProductAvailabilityEnum` | `in_stock`, `out_of_stock` |
| `CatalogSyncStatusEnum` | `not_synced`, `pending`, `synced`, `failed` |
| `MetaReviewStatusEnum` | `none`, `pending`, `approved`, `rejected`, `outdated` |
| `MetaCatalogStatusEnum` | `connected`, `permissions_missing`, `error` |
| `ShopModeEnum` | `bot`, `native_catalog` |
| `OrderStatusEnum` | `draft`, `awaiting_confirmation`, `awaiting_address`, `awaiting_payment_method`, `pending_payment`, `confirmed`, `packed`, `shipped`, `delivered`, `cancelled`, `expired`, `needs_attention` |
| `OrderStageEnum` | `checkout`, `open`, `closed` |
| `PaymentStatusEnum` | `unpaid`, `paid`, `cod_pending`, `cod_collected`, `refunded_manual` |
| `PaymentMethodEnum` | `online`, `cod` |
| `OrderSourceEnum` | `bot`, `native_cart` |
| `OrderEventTypeEnum` | `created`, `status_changed`, `price_changed`, `address_received`, `payment_link_created`, `payment_received`, `payment_link_expired`, `cod_collected`, `refunded_manual`, `stock_released`, `notification_sent`, `notification_failed`, `note` |
| `OrderEventActorEnum` | `buyer`, `dashboard`, `seller_whatsapp`, `system` |
| `PaymentProviderEnum` | `razorpay`, `cashfree` |
| `PaymentModeEnum` | `test`, `live` |
| `PaymentAccountStatusEnum` | `not_configured`, `unverified`, `verified`, `invalid` |
| `PaymentLinkStatusEnum` | `creating`, `created`, `paid`, `expired`, `cancelled`, `failed` |
| `AlertRecipientStatusEnum` | `pending`, `verified`, `opted_out` |
| `AlertEventEnum` | `new_order`, `needs_attention`, `order_cancelled` |
| `MessageTypeEnum` (inbox, extended) | adds `order` |
| `MessageSourceEnum` (inbox, extended) | adds `commerce`: shop messages use `source_ref` `shop`, order messages `order:<order_id>`; commerce automation actions keep `automation` |

Stage filter: `checkout` covers `draft` through `pending_payment`; `open` covers `confirmed`, `packed`, `shipped` and `needs_attention`; `closed` covers `delivered`, `cancelled` and `expired`.

## Error codes (all 409 unless noted)

| Code | When |
|---|---|
| `commerce_not_enabled` | The store is disabled (`StoreSettings.enabled` false), or the plan lacks the `commerce` feature (`CommerceNotEnabled`, a `FeatureNotAvailable` subclass). Catalog writes need the feature; disconnecting a Meta catalog doesn't |
| `catalog_not_connected` | A native-catalog action runs without a connected `MetaCatalog`, or `shop_mode=native_catalog` is chosen without one |
| `catalog_permissions_missing` | The seller's token lacks `catalog_management`/`business_management`; `details.reconnect_url` is null and the UI tells the seller to reconnect WhatsApp |
| `payment_account_missing` | Online payment or verification is attempted without gateway keys |
| `payment_account_invalid` | The gateway rejected the keys (on verify) |
| `invalid_order_transition` | `details: {from_status, to_status, allowed: [..]}`; also mark-COD-collected and mark-refunded on an order that isn't eligible |
| `out_of_stock` | `details: {items: [{sku, name, requested, available}]}` |
| `alert_number_unverified` | The action needs a verified alert recipient |
| `platform_alerts_unavailable` | `PLATFORM_WA_*` is not configured, or Meta refused the verification template (other than an unreachable number or a transient error) |
| `alert_recipient_limit` | More than 3 recipients per workspace |
| `verification_recently_sent` | A verification was re-sent within 5 minutes |
| 400 field error on `sku` (no separate error code) | Duplicate SKU in the workspace |
| `upstream_unavailable` (503, wave 2) | Payment verify can't reach the gateway; resending a verification hits a transient Meta error |

## Catalog: `/api/v1/catalog/`

### Components
- `Product`:
  - `id`
  - `sku`: Meta `retailer_id`, `^[A-Za-z0-9_-]{1,100}$`, unique per workspace, **read-only after create**
  - `name`: ≤ 200 characters; bot list rows truncate to 24
  - `description`: ≤ 1000
  - `price_paise`: int ≥ 100
  - `sale_price_paise`: int | null, and < `price_paise`
  - `effective_price_paise`: read-only
  - `currency`: `INR`, read-only
  - `image_url`: absolute public URL | null, read-only. The image is a `FileField` stored content-hashed under `catalog/products/<workspace_id>/<aa>/<sha256>.<ext>`; replaced files are kept because order items snapshot the URL
  - `collection`: `CollectionRef` (`id`, `name`) | null
  - `availability`: `ProductAvailabilityEnum`; set by the seller, and a tracked `stock_qty` of 0 makes buyers see it as out of stock
  - `stock_qty`: int ≥ 0 | null, where null means untracked
  - `max_qty_per_order`: 1–99, default 10
  - `position`: int
  - `is_active`: bool
  - `meta_sync_status`: `CatalogSyncStatusEnum`
  - `meta_review_status`: `MetaReviewStatusEnum`
  - `meta_rejection_reasons`: str[]
  - `created_at`, `updated_at`
- `ProductWriteRequest` (create and PATCH): `sku` (create only), `name`, `description?`, `price_paise`, `sale_price_paise?`, `collection_id?` (uuid | null), `availability?`, `stock_qty?`, `max_qty_per_order?`, `position?`, `is_active?`.
- `Collection`: `id`, `name` (≤ 24, a list row title), `description` (≤ 72, a list row description, "" allowed), `position`, `is_active`, `product_count` (read-only), `created_at`, `updated_at`. Request `CollectionWriteRequest`: `name`, `description?`, `position?`, `is_active?`.
- `ReorderRequest`: `ids: uuid[]` (the ordering; positions are rewritten 0..n). Ids left out keep their relative order after the listed ones; a duplicate id or an id from another workspace is 400.
- `ProductImportResult`: `created_count`, `updated_count`, `skipped_count`, `errors: ProductImportRowError[]` (`row`, `sku`, `reason`).
  - CSV columns: `sku` (required), `name`, `description`, `price` (rupees, "249" or "249.50"), `sale_price`, `collection` (by name; created when missing), `stock_qty`, `max_qty_per_order`, `availability` (`in_stock`/`out_of_stock`), `is_active` (`true`/`false`).
  - An empty cell keeps the stored value. New products need `name` and `price`. For a duplicate SKU in the file, the first row wins.
  - Limits: ≤ 5,000 rows (more rejects the whole file), ≤ 2 MB. Images are not imported.
- `MetaCatalog`:
  - `id`
  - `waba` (`MetaCatalogWaba`: `id`, `waba_id`, `name`)
  - `catalog_id`, `catalog_name`
  - `status`: `MetaCatalogStatusEnum`
  - `last_synced_at`
  - `last_sync_error`: ""
  - `product_counts` (`MetaCatalogCounts`: `synced`, `pending`, `failed`, `approved`, `rejected`)
  - `phone_numbers: CommerceSettings[]` (`phone_number_id` uuid, `display_phone_number`, `is_cart_enabled`, `is_catalog_visible`)
  - `created_at`, `updated_at`
- `AvailableCatalog`: `id` (Meta catalog id), `name`.
- `MetaCatalogConnectRequest`: `waba_id` (uuid of `WhatsAppBusinessAccount`) and exactly one of `catalog_id` (connect an existing catalog) or `create_name` (create one in the seller's business, then connect it).
- `CommerceSettingsRequest` (PATCH, generated as `PatchedCommerceSettingsRequest`): `phone_number_id` (uuid), `is_cart_enabled?`, `is_catalog_visible?`.

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `products/` / POST | viewer / admin | filters `collection` (uuid or `none`), `is_active`, `availability`, `meta_review_status`, `search` (name/sku); ordered by `position`, `name` |
| GET / PATCH / DELETE `products/{id}/` | viewer / admin | DELETE is soft in Meta terms: it queues a catalog DELETE; past order items keep their snapshots |
| POST / DELETE `products/{id}/image/` | admin | multipart `file` (JPEG/PNG, ≤ 8 MB, ≥ 500×500 px) → `Product`; DELETE → 204 |
| POST `products/import/` | admin | multipart `file` → `ProductImportResult` |
| POST `products/reorder/` | admin | `ReorderRequest` → 204 |
| GET `collections/` / POST | viewer / admin | ordered by `position` |
| GET / PATCH / DELETE `collections/{id}/` | viewer / admin | DELETE sets its products' collection to null |
| POST `collections/reorder/` | admin | `ReorderRequest` → 204 |
| GET `meta-catalogs/` / POST | viewer / admin | POST `MetaCatalogConnectRequest` → 201 `MetaCatalog` for a new catalog, 200 when it replaces the WABA's catalog (409 `catalog_permissions_missing`); connecting runs a full sync |
| GET `meta-catalogs/available/?waba_id=<uuid>` | admin | unpaginated `AvailableCatalog[]` owned by the seller's business |
| GET / DELETE `meta-catalogs/{id}/` | viewer / admin | DELETE disconnects locally (the store falls back to bot mode) |
| POST `meta-catalogs/{id}/sync/` | admin | full resync → 202 `MetaCatalog` |
| PATCH `meta-catalogs/{id}/commerce-settings/` | admin | `CommerceSettingsRequest` → `MetaCatalog` |

Writes (everything except GET and the catalog DELETE) need the plan's `commerce` feature: 409 `commerce_not_enabled`.

Sync rules:
- Saving or changing the image of a product queues a debounced `catalog.sync_products` for connected catalogs; deletes are not debounced. `catalog.poll_sync_status` updates the product fields.
- An incremental sync sends products changed since `MetaCatalog.last_synced_at`; a manual resync or a connect runs a full sync.
- `reserve_stock`/`release_stock` queue a sync when a tracked stock crosses zero.
- Meta needs a public `image_link`, so products without an image stay `not_synced`.
- A sync fails with a message in `last_sync_error` when the WABA has no phone number (the `link` needs one).
- `link` is the store link (`wa.me`).
- Known limitation: `meta_sync_status` and `meta_review_status` are per product, not per catalog.

## Orders: `/api/v1/orders/`

### Components
- `OrderListItem`: `id`, `number` (e.g. `SS-1001`), `status`, `payment_status`, `payment_method` (null), `source`, `contact` (`ConversationContact`), `total_paise`, `item_count`, `created_at`, `updated_at`.
- `Order`:
  - Everything in `OrderListItem`
  - `conversation_id` (null)
  - `phone_number` (`ConversationPhoneNumber`)
  - `items: OrderItem[]`
  - `subtotal_paise`, `shipping_paise`, `cod_fee_paise`, `total_paise`, `currency`
  - `address`: `OrderAddress` | null
  - `courier_name`, `awb_number`, `tracking_url` (each "" when unset)
  - `payment_link`: `OrderPaymentLink` (`id`, `short_url`, `status`, `amount_paise`, `expires_at`, `paid_at`) | null
  - `notes` (seller-internal)
  - `cancel_reason`
  - `expires_at` (checkout deadline | null)
  - `confirmed_at`, `packed_at`, `shipped_at`, `delivered_at`, `cancelled_at`
  - `allowed_transitions: OrderStatusEnum[]` (read-only, for the dashboard)
- `OrderItem`: `id`, `product_id` (null once the product is deleted), `sku`, `name`, `image_url` (null), `unit_price_paise`, `quantity`, `line_total_paise`.
- `OrderAddress`: `name`, `phone_e164`, `line1`, `line2`, `landmark`, `city`, `state`, `pincode` (6 digits), `country` (`IN`).
- `OrderEvent`: `id`, `type`, `from_status` (""), `to_status` (""), `actor`, `user` (`UserSummary` | null), `detail`, `message_id` (null), `message_status` (`MessageStatusEnum` | null: the current delivery status of that message, so a `notification_sent` whose message later failed can be shown as a warning), `message_error_code` (the Meta error code when that message failed, else ""), `created_at`.
- `OrderTransitionRequest`: `to_status` (`packed` | `shipped` | `delivered` | `confirmed`, the last only from `needs_attention`), `courier_name?`, `awb_number?`, `tracking_url?` (https URL), `notify_buyer?` (default true). `shipped` requires `courier_name` and `awb_number`.
- `CancelOrderRequest`: `reason?` (≤ 200, default ""), `restock?` (default true), `notify_buyer?` (default true).
- `OrderNotesRequest`: `notes` (≤ 2000).
- `OrderSummary`: `today_count`, `today_revenue_paise` (confirmed-or-later orders created today in the workspace time zone, excluding cancelled and expired), `open_count`, `needs_attention_count`, `awaiting_payment_count`.

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `` | viewer | filters `status` (comma-separated), `stage` (`OrderStageEnum`), `payment_status`, `payment_method`, `contact`, `search` (number, contact name/phone), `created_after`, `created_before`; newest first; `draft` is excluded unless asked for |
| GET / PATCH `{id}/` | viewer / agent | PATCH `OrderNotesRequest` |
| GET `{id}/events/` | viewer | oldest first, paginated |
| POST `{id}/transition/` | agent | `OrderTransitionRequest` → `Order` |
| POST `{id}/cancel/` | agent | `CancelOrderRequest` → `Order`; also cancels an open payment link |
| POST `{id}/mark-cod-collected/` | agent | only COD at `shipped`/`delivered` → `Order`; otherwise 409 `invalid_order_transition` |
| POST `{id}/mark-refunded/` | admin | only `paid` orders that are `cancelled`/`needs_attention` → `Order` (`refunded_manual`; the refund happens in the seller's payment gateway); otherwise 409 `invalid_order_transition` |
| GET `summary/` | viewer | `OrderSummary` |

**Transitions** (anything else is 409 `invalid_order_transition`):

| From | Allowed |
|---|---|
| `draft`, `awaiting_confirmation`, `awaiting_address`, `awaiting_payment_method`, `pending_payment` | `cancelled`; the system may also set `expired` and move the order forward through checkout |
| `confirmed` | `packed`, `shipped`, `cancelled` |
| `packed` | `shipped`, `cancelled` |
| `shipped` | `delivered` |
| `needs_attention` | `confirmed`, `cancelled` |
| `delivered`, `cancelled`, `expired` | none |

Cancelling or expiring releases reserved stock (`restock`). Every change writes an `OrderEvent` and emits `OrderStatusChanged` on commit.

## Store: `/api/v1/store/`

### Components
- `StoreSettings` (one per workspace, created lazily):
  - `enabled`
  - `shop_mode`
  - `store_name` (≤ 60, defaults to the workspace name)
  - `welcome_message` (≤ 1024)
  - `menu_keywords: str[]` (default `["hi", "hello", "menu", "shop", "start"]`, case-insensitive exact match)
  - `order_prefix` (`^[A-Z]{2,5}$`, default from the store name)
  - `min_order_paise`, `shipping_fee_paise`, `free_shipping_above_paise` (null)
  - `cod_enabled`, `cod_fee_paise`, `cod_max_order_paise` (null)
  - `serviceable_pincodes: str[]` (empty = everywhere)
  - `support_message` (the reply to *Talk to us*)
  - `powered_by_footer` (bool, default true)
  - `phone_number_id` (uuid | null: the store number, default the workspace default number). Only the store number runs the buyer bot
  - `store_link` (read-only `https://wa.me/<digits>?text=Hi` | null)
  - `notification_templates` (`OrderNotificationTemplates`: `confirmed`, `packed`, `shipped`, `delivered`, `cancelled`, `payment_reminder`, each a `MessageTemplate` uuid | null)
  - `updated_at`
- `StoreChecklist`: `items: StoreChecklistItem[]` (`key`, `done`, `detail`), with keys in order:
  1. `whatsapp_connected`
  2. `products_added`
  3. `payments_configured` (a verified account, or COD enabled)
  4. `order_templates_ready` (the 5 status templates are mapped and approved; `payment_reminder` is optional)
  5. `alert_number_verified`
  6. `store_enabled`
- `StarterTemplatesResult`: `created: str[]`, `existing: str[]` (template names).

UI gate: the Store area (nav and routes) is admin-only because it's for editing. Any member may read `settings/` and `checklist/`, and the home screen's store checklist card uses that read access for viewers.

WhatsApp message charges: under Meta's current pricing, Meta bills the seller's own WhatsApp Business Account. UpChatz is a Tech Provider and doesn't resell message credits in wave 3. Most shop messages are replies inside the buyer's 24-hour window; the paid ones are mainly templates outside it. The Store setup screen shows a note linking to WhatsApp Manager to add a payment method. It isn't a checklist item because the API can't confirm it.

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET / PATCH `settings/` | viewer / admin | turning on `enabled` needs the `commerce` feature, at least one active product and a connected number (409 `commerce_not_enabled` with a message naming what's missing) |
| GET `checklist/` | viewer | |
| POST `starter-templates/` | admin | creates the missing starter templates below in the store number's WABA (UTILITY, `en`) and maps any unmapped `notification_templates` → `StarterTemplatesResult` |

**Starter templates** (body parameters in order; a mapped template must have exactly this many variables):
| Template | Variables | Body parameters |
|---|---|---|
| `upc_order_confirmed` | 4 | name, order number, total (₹ formatted), payment ("Paid online" / "Cash on delivery") |
| `upc_order_packed` | 2 | name, order number |
| `upc_order_shipped` | 5 | name, order number, courier, AWB, tracking URL or "—" |
| `upc_order_delivered` | 2 | name, order number |
| `upc_order_cancelled` | 3 | name, order number, reason |
| `upc_payment_reminder` | 4 | name, order number, total, payment link |

Buyer notifications use an interactive or text message while the service window is open, and the mapped template otherwise. If no template is mapped outside the window, the `OrderEvent` is `notification_failed`.

## Payments: `/api/v1/payments/`, `/pay/return/{payment_link_id}/` and `/webhooks/payments/merchants/{token}/`

Sellers connect a gateway account they already have. Setup is: choose the provider (and the mode for Cashfree), paste the key id and secret, verify. **No webhook setup is required.** A payment is confirmed when the buyer's browser returns to UpChatz after paying, or by polling the gateway, whichever comes first. A webhook is optional and only makes confirmation faster.

### Providers (`apps/payments/providers/`, owned by payments)
```python
class PaymentProvider(Protocol):            # one implementation per gateway, plus a Fake for tests
    def verify_credentials(self) -> None: ...                       # PaymentAccountInvalid on 401/403
    def create_link(self, request: LinkRequest) -> LinkState: ...    # idempotent on reference_id
    def fetch_link(self, provider_link_id: str) -> LinkState: ...
    def cancel_link(self, provider_link_id: str) -> LinkState: ...   # never cancels a paid link
    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> list[WebhookLinkUpdate]: ...
        # verifies the signature first; raises InvalidWebhookSignature
LinkRequest(reference_id, amount_paise, currency, description, customer_name, customer_phone_e164,
            expire_by, return_url, notes)
LinkState(provider_link_id, short_url, status, amount_paid_paise, provider_payment_id, paid_at, raw,
          amount_paise, currency, expires_at)
WebhookLinkUpdate(event_id, event_type, provider_link_id, state: LinkState | None)
get_provider(account: PaymentAccount, *, transport=None) -> PaymentProvider
```
Errors are `PaymentProviderError(message, provider, status_code, retryable)` in `apps.payments.exceptions`. Our code uses integer paise everywhere; rupee conversion happens only inside a provider.

- **Razorpay:** `common.razorpay.RazorpayTransport` with the seller's key id and secret. Payment Links API: `reference_id` ≤ 40, `expire_by` ≥ 15 minutes ahead, `callback_url` = the return URL with `callback_method=get`, SMS and email notifications off, `notes`. `expire_by` is pushed to at least now + 16 minutes. Mode comes from the `rzp_test_`/`rzp_live_` key prefix and must match. Verify calls `GET /v1/payments?count=1`. Optional webhook: HMAC-SHA256 of the raw body with the account's `webhook_secret` (`X-Razorpay-Signature`), deduped on `x-razorpay-event-id`.
- **Cashfree:** PG API, sandbox for `test` and production for `live`, with `x-client-id`, `x-client-secret` and `x-api-version: 2026-01-01`. Payment Links API: `link_id` = `reference_id`, amount in rupees with 2 decimals, link expiry time, `link_meta.return_url`, Cashfree's own notifications off.
  - Cashfree has no credential-check endpoint, so verify fetches a made-up link id: 404 means the keys are valid, 401/403 invalid.
  - Link status `PAID`, or `COMPLETED`, counts as paid.
  - The payment id comes from the webhook's `order.transaction_id`, or from two extra calls when polling (blank if they fail).
  - The optional webhook is signed with the secret key (no separate webhook secret) and deduped on `x-idempotency-key`, else `sha256:<body hash>`. A body that isn't JSON is ignored, and polling confirms the payment instead.

### Components
- `PaymentAccount`: `provider` (default `razorpay`), `mode` (null until set), `key_id` (""; Razorpay key id or Cashfree App ID), `has_key_secret`, `has_webhook_secret`, `status`, `verified_at`, `last_error`, `webhook_url` (optional; read-only absolute URL built from `PUBLIC_API_BASE_URL`, "" until saved), `webhook_events: str[]` (read-only, for the chosen provider), `updated_at`.
- `PaymentAccountRequest` (PATCH, generated as `PatchedPaymentAccountRequest`): `provider?`, `mode?`, `key_id?`, `key_secret?` (write-only), `webhook_secret?` (write-only, Razorpay only).
  - Changing `provider` clears keys and secrets. Changing a key, secret or mode resets `status` to `unverified`.
  - Razorpay: `key_id` must match `^rzp_(test|live)_[A-Za-z0-9]+$` and sets `mode` (400 on `mode` when a given mode disagrees).
  - Cashfree: `mode` is required before verify (400 on `mode`).
- `PaymentLink`: `id`, `order_id`, `provider`, `provider_link_id` (""), `reference_id`, `short_url` (""), `amount_paise`, `status`, `expires_at`, `paid_at`, `created_at`.

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET / PATCH / DELETE `account/` | admin / admin / owner | secrets are never returned; DELETE with no account → 204 |
| POST `account/verify/` | admin | one authenticated read call on the gateway → `PaymentAccount` (409 `payment_account_missing` / `payment_account_invalid`; 503 `upstream_unavailable` when the gateway can't be reached) |
| POST `account/rotate-webhook/` | admin | new webhook token → `PaymentAccount` (only matters if the seller set up the optional webhook); 409 `payment_account_missing` with no account |
| GET `links/` | viewer | filter `order`, `status` |
| GET `/pay/return/{payment_link_id}/` | public | Where the gateway sends the buyer after paying. It never trusts query parameters: it refreshes the link from the gateway, then renders a small HTML page ("Payment received for order SS-1001, you can go back to WhatsApp", "We're confirming your payment" or "This payment link is no longer active") with a `wa.me` button for the store number. 404 for an unknown link; throttled per IP. Not in the OpenAPI schema. |
| POST `/webhooks/payments/merchants/{token}/` | public | Optional. 404 for an unknown token; the provider verifies the signature (400 when invalid); idempotent per workspace on the event id (`PaymentWebhookEvent`); always 200 after a valid signature. Not in the OpenAPI schema. |

**Confirmation.** The return page, polling and the webhook all end in the same `LinkState` handling:
- `payments.poll_open_links` (beat every minute) refreshes `created` links whose `next_poll_at` has passed. Polls run 2, 4, 6, 10, 15, 20, 25 and 30 minutes after creation, then once more at `expires_at` + 2 minutes. That final poll cancels a still-open link on the gateway, then marks it `expired`. If the final poll keeps failing, the link expires locally after 6 retries 5 minutes apart.
- A link becomes `paid` only when the fetched state is paid and the amount and currency match. `PaymentLinkPaid` is emitted exactly once (row lock on the link). Partial payments are logged and never confirm an order.
- Expiry or cancellation on the gateway side emits `PaymentLinkExpired` / `PaymentLinkCancelled`.
- Tests never call a gateway: use the `fake_payments` fixture (root `conftest.py`) or `override_provider(FakePaymentProvider())`.

**Link rules:**
- `reference_id` = `<order number>-<attempt>` (≤ 40 characters, unique per workspace).
- `expire_by` = now + `PAYMENT_LINK_EXPIRY_MINUTES`.
- `notes` = `{workspace_id, order_id}`.
- `customer` = contact name and phone; the gateway's own SMS and email are off.
- The return URL is `services.return_url(payment_link)`.

## Seller alerts: `/api/v1/seller-alerts/`

### Components
- `AlertRecipient`: `id`, `name` (≤ 60), `phone_e164`, `status`, `events: AlertEventEnum[]` (default all), `verified_at`, `last_sent_at`, `created_at`. Request `AlertRecipientRequest`: `name`, `phone_e164` (create only), `events?`.
- Models beyond the API: `AlertRecipient.wa_id` and `last_inbound_at` (the phone's 24-hour window with the platform number), `AlertMessage` (outbound log; `dedupe_key` `<recipient>:<order>:<event>:<new_status>` so an alert goes out once), `PendingSellerReply` (the courier and AWB question after *Mark shipped*, expires after 30 minutes) and `AlertInboundMessage` (inbound log keyed on `wamid`, with outcome `handled` or `ignored`).
- `PlatformAlertsInfo`: `available` (bool), `display_phone_number` ("" when unavailable).

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `platform/` | viewer | `PlatformAlertsInfo` |
| GET `recipients/` / POST | viewer / admin | POST sends the `upc_seller_verify` template from the platform number → 201 (409 `platform_alerts_unavailable`, `alert_recipient_limit`). An unreachable number (Meta 131026) → 400 on `phone_e164` and the recipient isn't kept; a transient Meta error → 201 without starting the resend cooldown; other Meta errors → 409 `platform_alerts_unavailable` |
| PATCH / DELETE `recipients/{id}/` | admin | |
| POST `recipients/{id}/resend-verification/` | admin | 409 `verification_recently_sent`; 503 `upstream_unavailable` on a transient Meta error |

**Platform templates** (UpChatz WABA, UTILITY, `en`). `manage.py sync_platform_templates` creates missing ones and edits the ones that differ from their definition where Meta allows it (`[created]`, `[unchanged]`, `[updated]`, or `[outdated: <reason>]` for a status Meta can't edit or the edit limit of approved templates):
- `upc_seller_verify`: body params store name. Button *Confirm*, payload `upc:alerts:verify:<recipient_id>`.
- `upc_new_order`: body params store name, order number, item summary (≤ 200 characters), total, payment. Buttons *Mark packed*, *Mark shipped*, *Cancel*, with payloads `upc:alerts:pack|ship|cancel:<order_id>`.
- `upc_order_attention`: body params store name, order number, reason. `order_cancelled` alerts reuse it outside the window with the reason "it was cancelled by the buyer|UpChatz (<cancel reason>)", so there is no cancellation template to approve. Checkout-stage cancellations (a superseded cart, *Edit cart*, the buyer's *Cancel order*) never alert, because the seller had no new-order alert for them.

Only `verified` recipients receive alerts, and commands are accepted only from a verified recipient's `from_wa_id`. Recipients are matched on `wa_id`, the E.164 number without "+". That holds for India; some countries' `wa_id`s differ from the dialled number. *Confirm* is accepted only from the phone the verification was sent to. Each order action re-checks that the order belongs to one of that recipient's workspaces. One phone may be a recipient for several workspaces: `ORDERS` lists them all, and a bare "courier AWB" reply applies to the order that asked for it last (for 30 minutes).

Seller actions:
| Tap | Result |
|---|---|
| *Mark packed* | `transition(order, "packed", actor="seller_whatsapp")` |
| *Mark shipped* | asks for "courier AWB [tracking URL]", then `transition(..., "shipped")` |
| *Cancel* | asks "Cancel order SS-1001? The buyer will be told and items go back to stock." with *Yes, cancel* (`upc:alerts:cancel_yes:<order_id>`) and *Keep order* (`upc:alerts:cancel_no:<order_id>`). The question is a free-form message: the seller's window is open because they just tapped |
| *Yes, cancel* | re-checks the recipient, workspace and order state under a lock, then `cancel_order(order, actor="seller_whatsapp", reason="Cancelled by the seller on WhatsApp")` |
| *Keep order* | "Okay, order SS-1001 is unchanged." |
| `ORDERS` row (`upc:alerts:orders:<order_id>`) | the order's details with the buttons its status allows |

Old or repeated taps (an order already cancelled or shipped, the same `wamid` twice) get a friendly reply and change nothing.

Texting `STOP` sets `opted_out`.

## Reply-id grammar (`common/commerce.py`, frozen)

Every commerce reply id has the form `upc:<scope>:<action>[:<arg>...]`. It is at most 200 characters, and each part matches `[A-Za-z0-9_.-]+`. Build ids with `build_reply_id`, parse them with `parse_reply_id`, and re-validate every one against current state under `select_for_update`. A stale id gets a polite "This option is no longer available" plus the menu.

| Scope | Actions (args) | Owner |
|---|---|---|
| `shop` | `menu`, `browse` (no args: collections), `col` (collection_id, offset; or the pseudo collections `all`, offset when there are no collections, and `other`, offset for products without one), `prod` (product_id), `add` (product_id, qty), `qty` (product_id), `cart`, `clear`, `checkout`, `orders`, `talk` | shop |
| `chk` | `confirm` (order_id), `edit` (order_id), `pay` (order_id, `online`/`cod`), `retry` (order_id), `cancel` (order_id) | orders |
| `ord` | `view` (order_id), `list` | orders |
| `nfm` | `address_message` (set by the webhook parser for `nfm_reply`) | orders |
| `alerts` | `verify` (recipient_id), `pack` / `ship` / `cancel` / `cancel_yes` / `cancel_no` (order_id), `orders` (no args: the open orders list; order_id: one order's actions) | seller_alerts |

**Claiming:**
- `is_claimed_by_commerce(event)` is true for inbound `order` messages, for any well-formed `upc:` reply id, and for anything a registered claimer accepts.
- The shop registers a claimer for `menu_keywords` when the store is enabled. The orders app registers one for typed address and quantity replies while a checkout or bot session awaits text.
- Automations skip claimed messages. Everything else still reaches automations and the inbox.

## Python contracts (backend)

### Events added to `common/events.py`
- `PlatformInboundMessage(phone_number_id, wamid, from_wa_id, timestamp, type, text, reply_id, profile_name, context_wamid, payload, webhook_event_id)`: the webhooks app routes messages whose `metadata.phone_number_id == PLATFORM_WA_PHONE_NUMBER_ID` here, before workspace resolution. Statuses for that number are dropped with a debug log.
- `PaymentLinkPaid(workspace_id, order_id, payment_link_id, provider, provider_link_id, provider_payment_id, amount_paise, currency, paid_at)`, `PaymentLinkExpired(..., occurred_at)`, `PaymentLinkCancelled(..., occurred_at)`: emitted on commit by payments, whichever of the return page, polling or the optional webhook sees the state first. `provider` is `razorpay` or `cashfree`; `provider_payment_id` may be "". Orders reacts idempotently (keyed on `payment_link_id` and the order's state).
- `OrderStatusChanged(workspace_id, order_id, order_number, contact_id, phone_number_id, old_status, new_status, payment_status, payment_method, total_paise, actor, actor_user_id, occurred_at)`: emitted on commit by orders. Seller alerts react to it.

### Webhook parser (`apps/webhooks/parsers.py`)
- `order` messages: the text is a summary such as `"Cart: 3 items, ₹1,450.00"` (computed from `product_items`; display only, never trusted), `reply_id` is None, and the raw `payload` keeps `order.catalog_id` and `order.product_items[]`.
- `interactive.nfm_reply`: the text is `"Address shared"` (or `nfm_reply.body`), and `reply_id` is `upc:nfm:<name>` (e.g. `upc:nfm:address_message`). `response_json` is left raw in the payload.
- The inbox stores `order` as `Message.Type.ORDER` and keeps `Message.payload`. `Message` gains optional response fields:
  - `interactive` (the outbound `interactive` object | null)
  - `order` (`MessageOrder`: `catalog_id`, `items: [{product_retailer_id, name, quantity, item_price, currency}]` | null). `name` is the current name of the workspace product with that SKU, or null; the inbox resolves every cart on a page with one catalog query per workspace
  - `reply` (`MessageReply`: `kind` (`MessageReplyKindEnum`: `button` for a reply button or a template quick-reply button, `list`, `nfm`), `id` (the reply id or button payload; the flow name for `nfm`), `title`, `description` ("" unless a list row has one) | null). Derived from the stored inbound payload; the dashboard never shows `upc:` ids
  - `order_id` (uuid | null): from `source_ref` `order:<order_id>`, or from the first argument of a `chk`/`ord` reply id. When `start_checkout` creates an order with a `source_wamid`, orders sets that inbound message's `source_ref` to `order:<order_id>` (its `source` stays `inbound`), which links native carts and bot checkout taps. The inbox doesn't import orders, so the order number isn't included

### Sending interactive messages (`apps/inbox/sending.py`, `apps/inbox/interactive.py`)
```python
InteractiveContent(interactive: Mapping[str, Any], summary: str)  # raw Cloud API "interactive"
# object; summary is the inbox text. Session-only: outside the window send_message raises
# OutsideServiceWindow. Validation errors raise InvalidInteractiveContent (ValueError).
reply_buttons(body, buttons: Sequence[tuple[str, str]], *, header: str | ImageHeader | None = None,
              footer: str | None = None) -> InteractiveContent          # 1–3 buttons, title ≤ 20
list_message(body, button: str, sections: Sequence[ListSection], *, header: str | None = None,
             footer: str | None = None) -> InteractiveContent           # ≤ 10 rows in total
ListSection(title: str, rows: Sequence[ListRow]); ListRow(id: str, title: str, description: str = "")
cta_url(body, display_text, url, *, header: str | ImageHeader | None = None, footer=None)
product(catalog_id, retailer_id, *, body=None, footer=None)
product_list(catalog_id, header: str, body: str, sections: Sequence[ProductSection], *, footer=None)
ProductSection(title: str, retailer_ids: Sequence[str])                 # ≤ 10 sections, ≤ 30 items
catalog_message(body, *, thumbnail_retailer_id: str | None = None, footer=None)
address_message(body, *, values: Mapping[str, str] | None = None,
                validation_errors: Mapping[str, str] | None = None) -> InteractiveContent
ImageHeader(url: str)
```
Limits (enforced): body ≤ 1024, footer ≤ 60, text header ≤ 60, list button ≤ 20, row title ≤ 24, row description ≤ 72, ids ≤ 200 (rows) / 256 (buttons). Error 1026 on `address_message` (unsupported client) marks the message failed with `error_code="1026"`; orders falls back to asking for the address as text.

### Graph client (`apps/whatsapp/client`, frozen signatures; Http and Fake implemented)
`list_waba_catalogs(waba_id)`, `list_business_catalogs(business_id)`, `create_catalog(business_id, *, name)`, `connect_catalog(waba_id, catalog_id)`, `batch_catalog_items(catalog_id, requests)`, `get_catalog_batch_status(catalog_id, handle)`, `list_catalog_products(catalog_id, *, after=None, limit=100)`, `get_commerce_settings(phone_number_id)`, `update_commerce_settings(phone_number_id, *, is_cart_enabled=None, is_catalog_visible=None)`, `edit_message_template(template_id, *, components, category=None)` (`POST /{template_id}`; Meta allows edits only to `APPROVED`, `REJECTED` or `PAUSED` templates, at most once per 24 hours and 10 times per 30 days for approved ones, and never the category of an approved one). `get_waba` also requests `owner_business_info` (for `business_id`). Template management errors (subcodes 2388xxx) map to `TemplateError`.

### Catalog services (`apps/catalog/services.py`)
```python
@dataclass(frozen=True) class CartLine: quantity: int; product_id: UUID | None = None; sku: str | None = None
@dataclass(frozen=True) class PricedLine: product: Product; quantity: int; unit_price_paise: int; line_total_paise: int
@dataclass(frozen=True) class DroppedLine: sku: str; name: str; reason: str  # unknown | inactive | out_of_stock | quantity_capped
                                          requested: int; available: int | None
@dataclass(frozen=True) class PricedCart: lines: tuple[PricedLine, ...]; dropped: tuple[DroppedLine, ...]; subtotal_paise: int
list_shoppable_collections(workspace) -> list[Collection]            # active, with ≥ 1 shoppable product
list_shoppable_products(workspace, *, collection=None, offset=0, limit=9) -> tuple[list[Product], bool]
get_shoppable_product(workspace, product_id) -> Product | None
price_items(workspace, lines: Iterable[CartLine]) -> PricedCart      # merges duplicate lines; caps at max_qty_per_order and stock
reserve_stock(workspace, lines: Iterable[tuple[UUID, int]]) -> None  # all-or-nothing in the caller's transaction; raises OutOfStock (409 out_of_stock)
release_stock(workspace, lines: Iterable[tuple[UUID, int]]) -> None
public_image_url(product) -> str | None
connected_catalog(workspace, phone_number) -> MetaCatalog | None     # connected and usable for native mode
```

### Orders services (`apps/orders/services.py`)
```python
get_store_settings(workspace) -> StoreSettings
start_checkout(*, workspace, conversation, cart: PricedCart, source: str, source_wamid: str | None = None,
               quoted_total_paise: int | None = None) -> Order     # supersedes the active checkout; sends every buyer message
handle_checkout_reply(message: Message, reply: ReplyId) -> bool     # chk, ord, nfm scopes
handle_checkout_text(message: Message) -> bool                      # False unless a checkout waits for typed text
send_recent_orders(conversation) -> None                             # "My orders" list (≤ 10)
transition(order, to_status, *, actor, user=None, courier_name="", awb_number="", tracking_url="",
           notify_buyer=True) -> Order
cancel_order(order, *, actor, user=None, reason="", restock=True, notify_buyer=True,
             system=False) -> Order                                  # system=True also allows the system-only moves
mark_cod_collected(order, *, actor, user=None) -> Order
open_orders_for_workspaces(workspace_ids, *, limit=10) -> list[Order]
```
- `start_checkout` raises `CheckoutRejected(reason)` (`empty_cart` or `below_minimum`, in `apps.orders.exceptions`, re-exported by services) after telling the buyer why, and `catalog.OutOfStock` when the stock reservation fails.
- *Edit cart* (`chk:edit`) cancels the checkout and sends the shop cart (`upc:shop:cart`); a stale checkout reply sends the shop menu (`upc:shop:menu`).
- Order messages to buyers are recorded with source `commerce` and `source_ref` `order:<order_id>`.

There is one active checkout per (contact, phone number), enforced by a partial unique constraint on non-terminal checkout statuses. Order numbers come from `OrderCounter` (`<order_prefix>-<n>`, starting at 1001).

### Payments services (`apps/payments/services.py`)
```python
get_account(workspace) -> PaymentAccount | None
online_payments_ready(workspace) -> bool          # verified account with key id, secret and mode (no webhook needed)
create_payment_link(*, workspace, order_id, reference_id, amount_paise, description, customer_name,
                    customer_phone_e164, expire_by) -> PaymentLink    # idempotent on reference_id;
# raises PaymentAccountMissing / PaymentAccountInvalid (409) or PaymentProviderError (check .retryable)
cancel_payment_link(payment_link) -> PaymentLink                    # idempotent; never cancels a paid link
refresh_payment_link(payment_link) -> PaymentLink                   # fetch from the gateway and apply; idempotent
return_url(payment_link) -> str
webhook_url(account) -> str
```
Shared Razorpay transport: `common/razorpay.py` (`RazorpayTransport`, `RazorpayError`, `checked_id`, `webhook_signature_is_valid`); the Razorpay provider wraps `RazorpayError` in `PaymentProviderError`. `apps.billing.razorpay` keeps its public names and reuses these. The Cashfree transport lives in `apps/payments/providers/cashfree.py`.

### Shop (`apps/shop`)
- The receiver on `MessageRecorded` (inbound) handles `shop` replies, menu keywords, typed quantities while awaiting one, and `order` messages (native cart → `price_items` with `CartLine(sku=product_retailer_id)` → `start_checkout(source="native_cart", source_wamid=wamid, quoted_total_paise=…)`).
- It forwards `chk`/`ord`/`nfm` replies and awaited text to `orders.services`.
- Only the store number (`StoreSettings.phone_number`, else the workspace default number) runs the bot.
- Collections: with no collections, products are listed under the pseudo collection `col:all:<offset>`; products without a collection appear under `col:other:<offset>`.
- The cart is kept during checkout and cleared when the order moves from the checkout stage to `confirmed`.
- Shop messages are recorded with source `commerce` and `source_ref` `shop`.
- `BotSession` expires 24 h after the last buyer message.
- Claim order follows `LOCAL_APPS` (automations before shop).

### Seller alerts (`apps/seller_alerts`)
The platform client is `get_client(settings.PLATFORM_WA_ACCESS_TOKEN)` sending from `PLATFORM_WA_PHONE_NUMBER_ID`. Its outbound log (`AlertMessage`) is platform-level and never appears in a workspace inbox. It reacts to `OrderStatusChanged` (new_status `confirmed` with old in the checkout stage → `new_order`; `needs_attention`; `cancelled` by the buyer or system) and to `PlatformInboundMessage`.

Message cost: the alerts number belongs to UpChatz, so UpChatz pays for templates sent from it. `AlertRecipient` records when that phone last messaged the platform number. While that 24-hour window is open, alerts go out as free-form interactive messages (the same text, buttons and reply ids). The platform template is used only outside the window.

### Entitlements
Feature `commerce` is added to `FEATURES` and enabled on every plan and the trial (data migration). There are no price or limit changes this wave.

### Automations
- Claimed messages are skipped (see Claiming).
- New actions, added to `SEND_ACTIONS`: `send_shop_menu {}`, `send_catalog {}`, `send_collection {collection_id}`.
- They call shop services through an integration hook registered by `apps.shop` (`apps.automations.hooks`).
- `send_catalog` in bot mode sends the collections list.
- Skip codes: `store_unavailable`, `store_empty`, `collection_empty`. Failure code: `collection_not_found`.
- `AutomationActionTypeEnum` gains those values.

### Settings (lead-owned, in `config/settings/base.py`)
`PUBLIC_API_BASE_URL`, `PUBLIC_MEDIA_BASE_URL`, `PAYMENT_LINK_EXPIRY_MINUTES` (30), `ORDER_CHECKOUT_TTL_MINUTES` (35), `PLATFORM_WA_WABA_ID`, `PLATFORM_WA_PHONE_NUMBER_ID`, `PLATFORM_WA_DISPLAY_PHONE_NUMBER`, `PLATFORM_WA_ACCESS_TOKEN`.

### Celery
Tasks and beat entries:

| Task | Schedule |
|---|---|
| `catalog.sync_products` | debounced |
| `catalog.poll_sync_status` | beat every 2 min while batches are pending |
| `orders.expire_checkouts` | beat every 5 min |
| `orders.send_payment_link` | on demand |
| `payments.create_link` | on demand |
| `payments.poll_open_links` | beat every 1 min |
| `seller_alerts.send_alert` | on demand |

## WebSocket frames (added)
| type | data |
|---|---|
| `order.created` | `order_id`, `number`, `status` |
| `order.updated` | `order_id`, `status`, `payment_status` |
| `catalog.sync` | `meta_catalog_id`, `status` (`CatalogSyncStatusEnum`) |
| `alert_recipient.updated` | `recipient_id`, `status` |

## Allowed cross-app imports in wave 3
- Everything allowed in wave 2.
- `apps.catalog.services` and `apps.catalog.models` (read, FKs), used by shop and orders; `apps.catalog.models` also by the inbox message serializer (cart product names).
- `apps.orders.services` and `apps.orders.models` (read, FKs), used by shop, seller_alerts and payments (FK only).
- `apps.payments.services` and `apps.payments.exceptions`, used by orders.
- `apps.inbox.interactive`.
- `apps.automations.hooks`, used by shop to register the commerce automation actions.
- `common.commerce` and `common.razorpay`.

Everything else goes through `common/events.py` signals.

## Demo data
`demo.py` in catalog, orders and payments seeds "Sharma Sweets": 3 collections, 12 products, orders in every status and a test-mode Razorpay payment account without secrets.

## Out of scope for wave 3
Pricing/plan changes, Shopify/WooCommerce sync, courier integrations, WhatsApp Pay (`order_details`), Flows, coexistence for sellers, automated refunds, buyer GST invoices, coupons, variants, abandoned-cart recovery, storefront website, AI, gateways other than Razorpay and Cashfree (the provider interface allows them later), gateway partner OAuth, UpChatz-collected payments (marketplace/Route), reselling WhatsApp message credits (a wallet needs Meta Solution Partner status or a multi-partner solution).
