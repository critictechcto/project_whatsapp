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

Stage filter: `checkout` covers `draft` through `pending_payment`; `open` covers `confirmed`, `packed`, `shipped` and `needs_attention`; `closed` covers `delivered`, `cancelled` and `expired`.

## Error codes (all 409 unless noted)

| Code | When |
|---|---|
| `commerce_not_enabled` | The store is disabled (`StoreSettings.enabled` false), or the plan lacks the `commerce` feature |
| `catalog_not_connected` | A native-catalog action runs without a connected `MetaCatalog`, or `shop_mode=native_catalog` is chosen without one |
| `catalog_permissions_missing` | The seller's token lacks `catalog_management`/`business_management`; `details.reconnect_url` is null and the UI tells the seller to reconnect WhatsApp |
| `payment_account_missing` | Online payment or verification is attempted without gateway keys |
| `payment_account_invalid` | The gateway rejected the keys (on verify) |
| `invalid_order_transition` | `details: {from_status, to_status, allowed: [..]}` |
| `out_of_stock` | `details: {items: [{sku, name, requested, available}]}` |
| `alert_number_unverified` | The action needs a verified alert recipient |
| `platform_alerts_unavailable` | `PLATFORM_WA_*` is not configured |
| `alert_recipient_limit` | More than 3 recipients per workspace |
| `verification_recently_sent` | A verification was re-sent within 5 minutes |
| `sku_taken` (400 `invalid` field error on `sku`) | Duplicate SKU in the workspace |

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
  - `image_url`: absolute public URL | null, read-only
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
- `ReorderRequest`: `ids: uuid[]` (the full ordering; positions are rewritten 0..n).
- `ProductImportResult`: `created_count`, `updated_count`, `skipped_count`, `errors: ProductImportRowError[]` (`row`, `sku`, `reason`).
  - CSV columns: `sku` (required), `name`, `description`, `price` (rupees, "249" or "249.50"), `sale_price`, `collection` (by name; created when missing), `stock_qty`, `max_qty_per_order`, `availability` (`in_stock`/`out_of_stock`), `is_active` (`true`/`false`).
  - Limits: ≤ 5,000 rows, ≤ 2 MB. Images are not imported.
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
- `CommerceSettingsRequest`: `phone_number_id` (uuid), `is_cart_enabled?`, `is_catalog_visible?`.

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `products/` / POST | viewer / admin | filters `collection` (uuid or `none`), `is_active`, `availability`, `meta_review_status`, `search` (name/sku); ordered by `position`, `name` |
| GET / PATCH / DELETE `products/{id}/` | viewer / admin | DELETE is soft in Meta terms: it queues a catalog DELETE; past order items keep their snapshots |
| POST / DELETE `products/{id}/image/` | admin | multipart `file` (JPEG/PNG, ≤ 8 MB, ≥ 500×500 px) → `Product`; DELETE → `Product` |
| POST `products/import/` | admin | multipart `file` → `ProductImportResult` |
| POST `products/reorder/` | admin | `ReorderRequest` → 204 |
| GET `collections/` / POST | viewer / admin | ordered by `position` |
| GET / PATCH / DELETE `collections/{id}/` | viewer / admin | DELETE sets its products' collection to null |
| POST `collections/reorder/` | admin | `ReorderRequest` → 204 |
| GET `meta-catalogs/` / POST | viewer / admin | POST `MetaCatalogConnectRequest` → 201 `MetaCatalog` (409 `catalog_permissions_missing`) |
| GET `meta-catalogs/available/?waba_id=<uuid>` | admin | unpaginated `AvailableCatalog[]` owned by the seller's business |
| GET / DELETE `meta-catalogs/{id}/` | viewer / admin | DELETE disconnects locally (the store falls back to bot mode) |
| POST `meta-catalogs/{id}/sync/` | admin | full resync → 202 `MetaCatalog` |
| PATCH `meta-catalogs/{id}/commerce-settings/` | admin | `CommerceSettingsRequest` → `MetaCatalog` |

Sync rules:
- Saving, deleting or changing the image of a product queues a debounced `catalog.sync_products` for connected catalogs; `catalog.poll_sync_status` updates the product fields.
- Meta needs a public `image_link`, so products without an image stay `not_synced`.
- `link` is the store link (`wa.me`).

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
- `OrderEvent`: `id`, `type`, `from_status` (""), `to_status` (""), `actor`, `user` (`UserSummary` | null), `detail`, `message_id` (null), `created_at`.
- `OrderTransitionRequest`: `to_status` (`packed` | `shipped` | `delivered` | `confirmed`, the last only from `needs_attention`), `courier_name?`, `awb_number?`, `tracking_url?` (https URL), `notify_buyer` (default true). `shipped` requires `courier_name` and `awb_number`.
- `CancelOrderRequest`: `reason` (≤ 200), `restock` (default true), `notify_buyer` (default true).
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
| POST `{id}/mark-cod-collected/` | agent | only COD at `shipped`/`delivered` → `Order` |
| POST `{id}/mark-refunded/` | admin | only `paid` orders that are `cancelled`/`needs_attention` → `Order` (`refunded_manual`; the refund happens in the seller's payment gateway) |
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
  - `phone_number_id` (uuid | null: the store number, default the workspace default number)
  - `store_link` (read-only `https://wa.me/<digits>?text=Hi` | null)
  - `notification_templates` (`OrderNotificationTemplates`: `confirmed`, `packed`, `shipped`, `delivered`, `cancelled`, `payment_reminder`, each a `MessageTemplate` uuid | null)
  - `updated_at`
- `StoreChecklist`: `items: StoreChecklistItem[]` (`key`, `done`, `detail`), with keys in order:
  1. `whatsapp_connected`
  2. `products_added`
  3. `payments_configured` (a verified account, or COD enabled)
  4. `order_templates_ready`
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

**Starter templates** (body parameters in order):
- `upc_order_confirmed`: name, order number, total (₹ formatted), payment ("Paid online" / "Cash on delivery")
- `upc_order_packed`: name, order number
- `upc_order_shipped`: name, order number, courier, AWB, tracking URL or "—"
- `upc_order_delivered`: name, order number
- `upc_order_cancelled`: name, order number, reason
- `upc_payment_reminder`: name, order number, total, payment link

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
LinkState(provider_link_id, short_url, status, amount_paid_paise, provider_payment_id, paid_at, raw)
WebhookLinkUpdate(event_id, event_type, provider_link_id, state: LinkState | None)
get_provider(account: PaymentAccount, *, transport=None) -> PaymentProvider
```
Errors are `PaymentProviderError(message, provider, status_code, retryable)` in `apps.payments.exceptions`. Our code uses integer paise everywhere; rupee conversion happens only inside a provider.

- **Razorpay:** `common.razorpay.RazorpayTransport` with the seller's key id and secret. Payment Links API: `reference_id` ≤ 40, `expire_by` ≥ 15 minutes ahead, `callback_url` = the return URL with `callback_method=get`, SMS and email notifications off, `notes`. Mode comes from the `rzp_test_`/`rzp_live_` key prefix and must match. Optional webhook: HMAC-SHA256 of the raw body with the account's `webhook_secret` (`X-Razorpay-Signature`), deduped on `x-razorpay-event-id`.
- **Cashfree:** PG API, sandbox for `test` and production for `live`, with `x-client-id`, `x-client-secret` and a pinned `x-api-version`. Payment Links API: `link_id` = `reference_id`, amount in rupees with 2 decimals, link expiry time, `link_meta.return_url`, Cashfree's own notifications off. The optional webhook is signed with the secret key (no separate webhook secret) and deduped on its event id, or a hash of the body when there is none.
- The payments agent checks exact field names, status values, signature formats and the verify call against the official Razorpay and Cashfree docs, and reports any deviation.

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
| GET / PATCH / DELETE `account/` | admin / admin / owner | secrets are never returned |
| POST `account/verify/` | admin | one authenticated read call on the gateway → `PaymentAccount` (409 `payment_account_missing` / `payment_account_invalid`) |
| POST `account/rotate-webhook/` | admin | new webhook token → `PaymentAccount` (only matters if the seller set up the optional webhook) |
| GET `links/` | viewer | filter `order`, `status` |
| GET `/pay/return/{payment_link_id}/` | public | Where the gateway sends the buyer after paying. It never trusts query parameters: it refreshes the link from the gateway, then renders a small HTML page ("Payment received for order SS-1001, you can go back to WhatsApp" or "We're confirming your payment") with a `wa.me` button for the store number. 404 for an unknown link; throttled per IP. Not in the OpenAPI schema. |
| POST `/webhooks/payments/merchants/{token}/` | public | Optional. 404 for an unknown token; the provider verifies the signature (400 when invalid); idempotent per workspace on the event id (`PaymentWebhookEvent`); always 200 after a valid signature. Not in the OpenAPI schema. |

**Confirmation.** The return page, polling and the webhook all end in the same `LinkState` handling:
- `payments.poll_open_links` (beat every minute) refreshes `created` links whose `next_poll_at` has passed. Polls run 2, 4, 6, 10, 15, 20, 25 and 30 minutes after creation, then once more at `expires_at` + 2 minutes. After that an unpaid link is `expired`.
- A link becomes `paid` only when the fetched state is paid and the amount and currency match. `PaymentLinkPaid` is emitted exactly once (row lock on the link). Partial payments are logged and never confirm an order.
- Expiry or cancellation on the gateway side emits `PaymentLinkExpired` / `PaymentLinkCancelled`.

**Link rules:**
- `reference_id` = `<order number>-<attempt>` (≤ 40 characters, unique per workspace).
- `expire_by` = now + `PAYMENT_LINK_EXPIRY_MINUTES`.
- `notes` = `{workspace_id, order_id}`.
- `customer` = contact name and phone; the gateway's own SMS and email are off.
- The return URL is `services.return_url(payment_link)`.

## Seller alerts: `/api/v1/seller-alerts/`

### Components
- `AlertRecipient`: `id`, `name` (≤ 60), `phone_e164`, `status`, `events: AlertEventEnum[]` (default all), `verified_at`, `last_sent_at`, `created_at`. Request `AlertRecipientRequest`: `name`, `phone_e164` (create only), `events?`.
- `PlatformAlertsInfo`: `available` (bool), `display_phone_number` ("" when unavailable).

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `platform/` | viewer | `PlatformAlertsInfo` |
| GET `recipients/` / POST | viewer / admin | POST sends the `upc_seller_verify` template from the platform number → 201 (409 `platform_alerts_unavailable`, `alert_recipient_limit`) |
| PATCH / DELETE `recipients/{id}/` | admin | |
| POST `recipients/{id}/resend-verification/` | admin | 409 `verification_recently_sent` |

**Platform templates** (UpChatz WABA, UTILITY, `en`, synced by `manage.py sync_platform_templates`):
- `upc_seller_verify`: body params store name. Button *Confirm*, payload `upc:alerts:verify:<recipient_id>`.
- `upc_new_order`: body params store name, order number, item summary (≤ 200 characters), total, payment. Buttons *Mark packed*, *Mark shipped*, *Cancel*, with payloads `upc:alerts:pack|ship|cancel:<order_id>`.
- `upc_order_attention`: body params store name, order number, reason.

Only `verified` recipients receive alerts, and commands are accepted only from a verified recipient's `from_wa_id`. Each order action re-checks that the order belongs to one of that recipient's workspaces. One phone may be a recipient for several workspaces: `ORDERS` lists them all, and a bare "courier AWB" reply applies to the order that asked for it.

Texting `STOP` sets `opted_out`.

## Reply-id grammar (`common/commerce.py`, frozen)

Every commerce reply id has the form `upc:<scope>:<action>[:<arg>...]`. It is at most 200 characters, and each part matches `[A-Za-z0-9_.-]+`. Build ids with `build_reply_id`, parse them with `parse_reply_id`, and re-validate every one against current state under `select_for_update`. A stale id gets a polite "This option is no longer available" plus the menu.

| Scope | Actions (args) | Owner |
|---|---|---|
| `shop` | `menu`, `browse` (no args: collections), `col` (collection_id, offset), `prod` (product_id), `add` (product_id, qty), `qty` (product_id), `cart`, `clear`, `checkout`, `orders`, `talk` | shop |
| `chk` | `confirm` (order_id), `edit` (order_id), `pay` (order_id, `online`/`cod`), `retry` (order_id), `cancel` (order_id) | orders |
| `ord` | `view` (order_id), `list` | orders |
| `nfm` | `address_message` (set by the webhook parser for `nfm_reply`) | orders |
| `alerts` | `verify` (recipient_id), `pack` / `ship` / `cancel` (order_id), `orders` | seller_alerts |

**Claiming:**
- `is_claimed_by_commerce(event)` is true for inbound `order` messages, for any well-formed `upc:` reply id, and for anything a registered claimer accepts.
- The shop registers a claimer for `menu_keywords` when the store is enabled. The orders app registers one for typed address and quantity replies while a checkout or bot session awaits text.
- Automations skip claimed messages. Everything else still reaches automations and the inbox.

## Python contracts (backend)

### Events added to `common/events.py`
- `PlatformInboundMessage(phone_number_id, wamid, from_wa_id, timestamp, type, text, reply_id, profile_name, context_wamid, payload, webhook_event_id)`: the webhooks app routes messages whose `metadata.phone_number_id == PLATFORM_WA_PHONE_NUMBER_ID` here, before workspace resolution. Statuses for that number are dropped with a debug log.
- `PaymentLinkPaid(workspace_id, order_id, payment_link_id, provider, provider_link_id, provider_payment_id, amount_paise, currency, paid_at)`, `PaymentLinkExpired(..., occurred_at)`, `PaymentLinkCancelled(..., occurred_at)`: emitted on commit by payments. Orders reacts idempotently (keyed on `payment_link_id` and the order's state).
- `OrderStatusChanged(workspace_id, order_id, order_number, contact_id, phone_number_id, old_status, new_status, payment_status, payment_method, total_paise, actor, actor_user_id, occurred_at)`: emitted on commit by orders. Seller alerts react to it.

### Webhook parser (`apps/webhooks/parsers.py`)
- `order` messages: the text is a summary such as `"Cart: 3 items, ₹1,450.00"` (computed from `product_items`; display only, never trusted), `reply_id` is None, and the raw `payload` keeps `order.catalog_id` and `order.product_items[]`.
- `interactive.nfm_reply`: the text is `"Address shared"` (or `nfm_reply.body`), and `reply_id` is `upc:nfm:<name>` (e.g. `upc:nfm:address_message`). `response_json` is left raw in the payload.
- The inbox stores `order` as `Message.Type.ORDER` and keeps `Message.payload`. `Message` gains optional response fields:
  - `interactive` (the outbound `interactive` object | null)
  - `order` (`MessageOrder`: `catalog_id`, `items: [{product_retailer_id, quantity, item_price, currency}]` | null)

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
`list_waba_catalogs(waba_id)`, `list_business_catalogs(business_id)`, `create_catalog(business_id, *, name)`, `connect_catalog(waba_id, catalog_id)`, `batch_catalog_items(catalog_id, requests)`, `get_catalog_batch_status(catalog_id, handle)`, `list_catalog_products(catalog_id, *, after=None, limit=100)`, `get_commerce_settings(phone_number_id)`, `update_commerce_settings(phone_number_id, *, is_cart_enabled=None, is_catalog_visible=None)`. `get_waba` also requests `owner_business_info` (for `business_id`).

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
               quoted_total_paise: int | None = None) -> Order     # supersedes the active checkout; sends the next step
handle_checkout_reply(message: Message, reply: ReplyId) -> bool     # chk, ord, nfm scopes
handle_checkout_text(message: Message) -> bool                      # typed address while awaiting it
send_recent_orders(conversation) -> None                             # "My orders" list (≤ 10)
transition(order, to_status, *, actor, user=None, courier_name="", awb_number="", tracking_url="",
           notify_buyer=True) -> Order
cancel_order(order, *, actor, user=None, reason="", restock=True, notify_buyer=True) -> Order
mark_cod_collected(order, *, actor, user=None) -> Order
open_orders_for_workspaces(workspace_ids, *, limit=10) -> list[Order]
```
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
- `BotSession` expires 24 h after the last buyer message.

### Seller alerts (`apps/seller_alerts`)
The platform client is `get_client(settings.PLATFORM_WA_ACCESS_TOKEN)` sending from `PLATFORM_WA_PHONE_NUMBER_ID`. Its outbound log (`AlertMessage`) is platform-level and never appears in a workspace inbox. It reacts to `OrderStatusChanged` (new_status `confirmed` with old in the checkout stage → `new_order`; `needs_attention`; `cancelled` by the buyer or system) and to `PlatformInboundMessage`.

Message cost: the alerts number belongs to UpChatz, so UpChatz pays for templates sent from it. `AlertRecipient` records when that phone last messaged the platform number. While that 24-hour window is open, alerts go out as free-form interactive messages (the same text, buttons and reply ids). The platform template is used only outside the window.

### Entitlements
Feature `commerce` is added to `FEATURES` and enabled on every plan and the trial (data migration). There are no price or limit changes this wave.

### Automations
- Claimed messages are skipped (see Claiming).
- New actions, added to `SEND_ACTIONS`: `send_shop_menu {}`, `send_catalog {}`, `send_collection {collection_id}`.
- They call shop services through an integration hook registered by `apps.shop`.
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
- `apps.catalog.services` and `apps.catalog.models` (read, FKs), used by shop and orders.
- `apps.orders.services` and `apps.orders.models` (read, FKs), used by shop, seller_alerts and payments (FK only).
- `apps.payments.services` and `apps.payments.exceptions`, used by orders.
- `apps.inbox.interactive`.
- `common.commerce` and `common.razorpay`.

Everything else goes through `common/events.py` signals.

## Demo data
`demo.py` in catalog, orders and payments seeds "Sharma Sweets": 3 collections, 12 products, orders in every status and a test-mode Razorpay payment account without secrets.

## Out of scope for wave 3
Pricing/plan changes, Shopify/WooCommerce sync, courier integrations, WhatsApp Pay (`order_details`), Flows, coexistence for sellers, automated refunds, buyer GST invoices, coupons, variants, abandoned-cart recovery, storefront website, AI, gateways other than Razorpay and Cashfree (the provider interface allows them later), gateway partner OAuth, UpChatz-collected payments (marketplace/Route), reselling WhatsApp message credits (a wallet needs Meta Solution Partner status or a multi-partner solution).
