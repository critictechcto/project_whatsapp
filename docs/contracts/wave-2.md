# Wave 2 contract

Every wave-2 agent (backend and frontend) builds against this document. Backend agents implement it; frontend agents consume it through the generated OpenAPI types (`backend/openapi.yml` → `frontend/src/api/schema.d.ts`). Changing a name, removing a field or changing a type needs a lead request. Adding optional response fields is allowed.

## Conventions (unchanged from waves 0–1)

- Base path `/api/v1/`. JWT `Authorization: Bearer <access>`. Login (`auth/token/`) and register return only `access`; the refresh token is an HttpOnly cookie `upchatz_refresh` (`SameSite=Strict`, `Path=/api/v1/auth/`, `Secure` in production). `auth/token/refresh/` (rotates the cookie, returns `access`) and `auth/logout/` (blacklists, clears the cookie, 204) take no body, need `X-UpChatz-Auth: 1` and answer 403 for an `Origin` outside the CORS origins / `FRONTEND_URL`; a missing or invalid cookie is 401 and clears it. Browsers send auth calls with `credentials: 'include'`. Tenant endpoints require `X-Workspace-ID`; non-members get 404, too-low roles get 403 `insufficient_role`.
- Roles: owner > admin > agent > viewer. "viewer" below means any member.
- Errors: `{"error": {"code": str, "message": str, "details": object|null}}`. Validation errors use code `invalid` with field errors in `details`.
- Lists use cursor pagination: `{"next": url|null, "previous": url|null, "results": [...]}`, `page_size` ≤ 200.
- No PUT; partial updates use PATCH. Timestamps are ISO 8601 UTC. Ids are UUIDs.
- Money: billing amounts are integer **paise** (`*_paise`); estimates are decimal strings in INR.
- Idempotent POSTs accept an `Idempotency-Key` header (already allowed by CORS).
- Serializer class `FooSerializer` produces component `Foo`; names below are the component names and must match.

## Enum component names (register in each app's `schema_enums.py`)

| Component | Values |
|---|---|
| `ConversationStatusEnum` | `open`, `pending`, `closed` |
| `MessageDirectionEnum` | `inbound`, `outbound` |
| `MessageTypeEnum` | `text`, `image`, `video`, `audio`, `document`, `sticker`, `location`, `contacts`, `interactive`, `button`, `reaction`, `template`, `unsupported` |
| `MessageStatusEnum` | `queued`, `sending`, `sent`, `delivered`, `read`, `failed`, `received` |
| `MessageSourceEnum` | `inbound`, `inbox`, `campaign`, `automation`, `api` |
| `SendMessageTypeEnum` | `text`, `template`, `media` |
| `CampaignStatusEnum` | `draft`, `scheduled`, `running`, `paused`, `completed`, `cancelled`, `failed` |
| `RecipientStatusEnum` | `pending`, `skipped`, `queued`, `sent`, `delivered`, `read`, `failed` |
| `VariableSourceTypeEnum` | `contact_field`, `attribute`, `static` |
| `AudienceMatchEnum` | `any`, `all` |
| `AutomationTriggerEnum` | `keyword`, `first_inbound`, `new_contact`, `outside_business_hours` |
| `KeywordMatchEnum` | `exact`, `contains` |
| `AutomationActionTypeEnum` | `send_text`, `send_template`, `add_tags`, `assign`, `close_conversation` |
| `AutomationRunStatusEnum` | `succeeded`, `skipped`, `failed` |
| `SubscriptionStatusEnum` | `trialing`, `pending`, `active`, `halted`, `cancelled`, `expired` |
| `BillingIntervalEnum` | `monthly`, `annual` |
| `InvoiceStatusEnum` | `issued`, `paid`, `void` |

## Inbox — `/api/v1/inbox/`

### Components
- `Conversation`: `id`, `contact` (`ConversationContact`: `id`, `name`, `phone_e164`, `marketing_opt_in_status`), `phone_number` (`ConversationPhoneNumber`: `id`, `display_phone_number`, `verified_name`), `status`, `assignee` (`UserSummary`: `id`, `full_name`, `email` | null), `unread_count`, `last_message_at`, `last_inbound_at`, `service_window_expires_at`, `window_open` (bool), `last_message` (`MessagePreview`: `direction`, `type`, `text`, `status`, `created_at` | null), `created_at`, `updated_at`.
- `Message`: `id`, `conversation_id`, `direction`, `type`, `text`, `status`, `source`, `error_code` (str, "" when none), `error_message`, `template` (`MessageTemplateRef`: `id`|null, `name`, `language` | null), `media` (`MessageMedia`: `mime_type`, `file_name`, `size`, `download_url` | null), `reply_to_message_id` (null), `sent_by` (`UserSummary` | null), `wamid`, `created_at`, `sent_at`, `delivered_at`, `read_at`, `failed_at`.
- `SendMessageRequest`: `type` (`SendMessageTypeEnum`); text → `text`, `preview_url?`; template → `template_id`, `body_params?: str[]`, `header_param?: str`, `button_params?: {index: str}`; media → `media_id` (from upload), `caption?`; always optional `reply_to_message_id`.
- `StartConversationRequest`: `contact_id`, `phone_number_id?` (default number when omitted).
- `AssignConversationRequest`: `assignee_id` (uuid | null).
- `ConversationNote`: `id`, `body`, `author` (`UserSummary`), `created_at`. Request `ConversationNoteRequest`: `body`.
- `MediaAsset`: `id`, `mime_type`, `file_name`, `size`, `created_at`.
- `WsTicket`: `ticket`, `expires_in` (seconds), `path` (`/ws/v1/`).

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `conversations/` | viewer | filters `status`, `assignee` (uuid, `me`, `none`), `phone_number`, `unread` (bool), `search` (contact name/phone); ordered by `-last_message_at` |
| POST `conversations/` | agent | `StartConversationRequest` → 200/201 `Conversation` (get-or-create) |
| GET `conversations/{id}/` | viewer | |
| POST `conversations/{id}/assign/` | agent | `AssignConversationRequest` → `Conversation`; assignee must be a member |
| POST `conversations/{id}/close/`, `reopen/` | agent | → `Conversation` |
| POST `conversations/{id}/read/` | agent | resets `unread_count`, sends Meta read receipt for the latest inbound → `Conversation` |
| GET `conversations/{id}/messages/` | viewer | cursor, newest first |
| POST `conversations/{id}/messages/` | agent | `SendMessageRequest` + optional `Idempotency-Key` → 201 `Message` (`queued`) |
| GET `conversations/{id}/notes/`, POST | viewer / agent | `ConversationNote` |
| POST `media/` | agent | multipart `file` → 201 `MediaAsset` (≤ Meta size limits per type) |
| GET `messages/{id}/media/` | viewer | streams the stored file |
| POST `ws-ticket/` | viewer | → `WsTicket` |

Error codes: `whatsapp_not_connected`, `phone_number_not_registered`, `outside_service_window`, `contact_opted_out`, `marketing_opt_in_required`, `template_not_approved`, `quota_exceeded` (all 409), `invalid` (400).

## Campaigns — `/api/v1/campaigns/`

### Components
- `VariableSource`: `source` (`VariableSourceTypeEnum`), `value` (contact field name `name`/`phone_e164`/`email`, attribute key, or static text), `fallback` (str, "").
- `VariableMapping`: `body: VariableSource[]`, `header: VariableSource | null`, `buttons: {index: VariableSource}`.
- `CampaignAudience`: `tag_ids: uuid[]`, `match` (`AudienceMatchEnum`), `contact_ids: uuid[]`.
- `CampaignStats`: `total`, `skipped`, `queued`, `sent`, `delivered`, `read`, `failed`, `replied`.
- `CostEstimate`: `currency` (`INR`), `amount` (decimal string), `note` (hedged text, "under Meta's current pricing").
- `Campaign`: `id`, `name`, `status`, `template` (`CampaignTemplate`: `id`, `name`, `language`, `category`), `phone_number` (`ConversationPhoneNumber`), `audience`, `variable_mapping`, `scheduled_at`, `started_at`, `completed_at`, `consent_attested`, `stats`, `estimated_cost` (`CostEstimate` | null), `last_error`, `created_by` (`UserSummary`), `created_at`, `updated_at`.
- `CampaignWriteRequest` (create/PATCH): `name`, `template_id`, `phone_number_id?`, `audience`, `variable_mapping`, `scheduled_at?`.
- `AudiencePreview`: `total`, `eligible`, `skipped` (`AudienceSkipped`: `opted_out`, `not_opted_in`, `invalid`).
- `LaunchCampaignRequest`: `consent_attested` (must be true), `scheduled_at?` (null = now).
- `CampaignRecipient`: `id`, `contact` (`ConversationContact`), `status` (`RecipientStatusEnum`), `skip_reason`, `error_code`, `message_id` (null), `updated_at`.

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `` / POST `` | viewer / admin | list filter `status`; create makes `draft` |
| GET / PATCH / DELETE `{id}/` | viewer / admin / admin | PATCH only in `draft`/`scheduled` else 409 `campaign_not_editable`; DELETE only `draft` |
| POST `{id}/audience-preview/` | viewer | → `AudiencePreview` |
| POST `{id}/launch/` | admin | `LaunchCampaignRequest` → `Campaign` (`scheduled` or `running`) |
| POST `{id}/pause/`, `resume/`, `cancel/` | admin | → `Campaign`; invalid transition 409 `invalid_campaign_transition` |
| GET `{id}/recipients/` | viewer | filter `status` |

Error codes: `campaign_not_editable`, `invalid_campaign_transition`, `template_not_approved`, `whatsapp_not_connected`, `feature_not_available` (scheduling a campaign when the plan lacks `scheduled_campaigns`) (all 409), `invalid` (400).

Rules: `OPTED_OUT` contacts are always skipped; MARKETING templates also require `OPTED_IN`; consent is snapshotted at materialisation and re-checked at dispatch. Template must be APPROVED at launch (409 `template_not_approved`).

## Automations — `/api/v1/automations/`

### Components
- `AutomationAction`: `type` (`AutomationActionTypeEnum`), `config` (object): `send_text {text}`, `send_template {template_id, body_params: VariableSource[]}`, `add_tags {tag_ids}`, `assign {user_id}`, `close_conversation {}`.
- `AutomationRule`: `id`, `name`, `is_active`, `trigger` (`AutomationTriggerEnum`), `keywords: str[]`, `keyword_match` (`KeywordMatchEnum`), `phone_number_id` (null = all numbers), `actions: AutomationAction[]` (1–5), `cooldown_minutes`, `priority`, `stop_processing`, `run_count`, `last_triggered_at`, `created_at`, `updated_at`.
- `BusinessHours`: `enabled`, `time_zone` (read-only, from workspace), `schedule: BusinessHoursSlot[]` (`day` 0=Mon…6, `start` "HH:MM", `end` "HH:MM"; `end < start` means overnight).
- `AutomationRun`: `id`, `rule` (`AutomationRuleRef`: `id`, `name`), `conversation_id`, `message_id`, `status` (`AutomationRunStatusEnum`), `detail`, `created_at`.

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `rules/` / POST | viewer / admin | filter `trigger`, `is_active` |
| GET / PATCH / DELETE `rules/{id}/` | viewer / admin | |
| GET / PATCH `business-hours/` | viewer / admin | singleton per workspace |
| GET `runs/` | viewer | filter `rule`, `status` |

Error codes: `feature_not_available` (409, activating a keyword rule when the plan lacks `keyword_automations`), `invalid` (400).

## Billing — `/api/v1/billing/` and `/webhooks/razorpay/`

### Components
- `PlanLimits`: `whatsapp_numbers`, `members`, `contacts` (int | null = unlimited).
- `Plan`: `id` (slug `starter`/`growth`/`pro`), `name`, `monthly_price_paise`, `annual_price_paise`, `limits`, `features: str[]`.
- `Subscription`: `plan` (`Plan`), `status`, `interval`, `trial_ends_at`, `current_period_start`, `current_period_end`, `cancel_at_period_end`.
- `CheckoutRequest`: `plan_id`, `interval`. `CheckoutSession`: `key_id`, `subscription_id`, `name`, `description`, `prefill` (`CheckoutPrefill`: `name`, `email`).
- `CheckoutVerifyRequest`: `razorpay_payment_id`, `razorpay_subscription_id`, `razorpay_signature`.
- `CancelSubscriptionRequest`: `at_period_end` (bool, default true).
- `BillingProfile`: `legal_name`, `gstin` ("" allowed), `email`, `address_line1`, `address_line2`, `city`, `state_code` (2-digit GST state code), `postal_code`.
- `Invoice`: `id`, `number`, `status`, `issued_at`, `period_start`, `period_end`, `subtotal_paise`, `cgst_paise`, `sgst_paise`, `igst_paise`, `total_paise`, `download_url` (null).
- `UsageMetric`: `key`, `used`, `limit` (null). `Usage`: `metrics: UsageMetric[]`.

### Endpoints
| Method + path | Role | Notes |
|---|---|---|
| GET `plans/` | viewer | |
| GET `subscription/` | viewer | |
| POST `subscription/checkout/` | owner | → `CheckoutSession` |
| POST `subscription/verify/` | owner | verifies signature → `Subscription` (may stay `pending` until the webhook) |
| POST `subscription/cancel/` | owner | → `Subscription` |
| GET / PATCH `billing-profile/` | admin / owner | |
| GET `invoices/` | admin | |
| GET `usage/` | viewer | |
| POST `/webhooks/razorpay/` | public | HMAC of raw body with `RAZORPAY_WEBHOOK_SECRET`; idempotent on `x-razorpay-event-id` |

Error codes: `quota_exceeded` (409), `billing_profile_required` (409), `payment_verification_failed` (400).

### Entitlements (`apps/billing/entitlements.py`, signatures frozen)
- Metrics: `whatsapp_numbers`, `members`, `contacts`. Features: `scheduled_campaigns`, `keyword_automations`, `api_access`.
- `has_feature(workspace, feature) -> bool`, `remaining_quota(workspace, metric) -> int | None`, `check_quota(workspace, metric, amount=1) -> None` (raises `QuotaExceeded`, 409 `quota_exceeded`), `record_usage(workspace, metric, amount, *, key) -> None` (idempotent on `key`).

## WebSocket — `/ws/v1/?ticket=<ticket>`

- Get a ticket from `POST /api/v1/inbox/ws-ticket/` (single use, 30 s). The server re-checks membership on connect and joins `ws.<workspace_id>` and `user.<user_id>`.
- Server → client frames: `{"v": 1, "type": str, "workspace_id": uuid, "data": object}`. Payloads are thin; clients refetch via the REST API.

| type | data |
|---|---|
| `message.created` | `conversation_id`, `message_id`, `direction` |
| `message.status` | `conversation_id`, `message_id`, `status` |
| `conversation.updated` | `conversation_id` |
| `campaign.progress` | `campaign_id`, `status`, `stats` (`CampaignStats`) |
| `session.revoked` | `reason` (sent to the user group; client disconnects and refreshes memberships) |
| `pong` | `{}` — reply to a client `{"type": "ping"}`; every other client message is ignored |

Close codes: `4401` unauthenticated or bad ticket, `4403` not a member, `4001` after `session.revoked`.

## Python contracts (backend)

### Sending — `apps/inbox/sending.py`
```python
send_message(*, workspace, contact, content, conversation=None, phone_number=None,
             reply_to_wamid=None, source, source_ref="", sent_by=None,
             idempotency_key=None, dispatch=True) -> Message
enqueue(message_ids: Iterable[UUID]) -> None
window_open(contact, phone_number) -> bool
# content: TextContent(body, preview_url=False) | TemplateContent(template, body_params=(),
#          header_param=None, button_params=None) | MediaContent(asset, caption="")
```
- `phone_number=None` → the conversation's number, else the workspace default number.
- Policy errors (subclasses of `common.exceptions.Conflict`, codes as listed under Inbox) are raised synchronously. The window is per `(contact, phone_number)` via `Conversation.service_window_expires_at`.
- Same `idempotency_key` in a workspace returns the existing `Message` and never raises.
- Key formats: `inbox:<client key>`, `campaign:<campaign_id>:recipient:<recipient_id>`, `automation:<rule_id>:<inbound_wamid>:<action_index>`.
- `inbox.dispatch_message` claims `queued → sending` atomically; a `NetworkError` after the Graph call marks the message `failed` with `error_code="network_unknown"` and is not retried automatically.

### Inbox services — `apps/inbox/services.py`
`assign(conversation, user_or_none, *, actor)`, `close(conversation, *, actor)`, `reopen(conversation, *, actor)`, `add_note(conversation, body, *, author)`, `mark_read(conversation, *, actor)`.

### Events added to `common/events.py`
- `MessageRecorded(workspace_id, message_id, conversation_id, contact_id, phone_number_id, direction, source, source_ref, type, text, reply_id, wamid, is_first_inbound, contact_created, created_at)`
- `MessageDeliveryUpdated(workspace_id, message_id, conversation_id, source, source_ref, status, error_code, occurred_at)`
- Both emitted with `transaction.on_commit`. Automations react to `MessageRecorded` with `direction == "inbound"`; campaigns match `MessageDeliveryUpdated.source == "campaign"`.
- Tenant events, emitted on commit by `apps.tenants.services`:
  - `WorkspaceCreated(workspace_id, owner_id)` from `create_workspace`. Billing starts the 14-day Growth trial (`get_subscription` still creates it lazily if the event was missed).
  - `MembershipRoleChanged(workspace_id, user_id, old_role, new_role)` from `change_member_role` (not sent when the role is unchanged).
  - `MembershipRemoved(workspace_id, user_id)` from `remove_member`, both when an admin removes someone and when a member leaves.
  - The inbox sends `session.revoked` to the user's sockets with `reason` `role_changed` or `membership_removed`.
- `common.events.EVENT_SIGNALS` maps every event dataclass to its signal.

### Plan errors — `common/exceptions.py`, `apps/billing/entitlements.py`
- `FeatureNotAvailable` (409 `feature_not_available`): the plan lacks a feature. Pass a message naming it.
- `QuotaExceeded` (409 `quota_exceeded`, `details` `{metric, limit, used}`): raised by `check_quota`. Guards:
  - Members: creating an invitation needs members + open unexpired invitations to other emails + 1 within the limit (re-inviting the same email doesn't take another seat). Accepting re-checks members + 1.
  - Contacts: `POST /contacts/` is checked; updates are not. CSV imports create new contacts only up to `remaining_quota`; the rest are skipped (`skipped_count`) with an `errors` entry whose `reason` is `quota_exceeded`, and existing contacts still update. Contacts created by inbound messages are never blocked.
  - WhatsApp numbers: Embedded Signup counts numbers new to the workspace (or deregistered) before storing anything; reconnecting already-connected numbers is not blocked.
  - Halted, cancelled or expired subscriptions leave no quota (`limit == used`).

### Realtime — `common/realtime.py`
`broadcast(workspace_id, type, data)` and `broadcast_user(user_id, type, data)`; both send on commit.

### Contacts helpers — `apps/contacts/services.py`
`add_tags(contact, tags)` and `remove_tags(contact, tags)` (tags from the same workspace).

## Allowed cross-app imports in wave 2
Wave 0–1 modules, plus `apps.inbox.sending`, `apps.inbox.services`, `apps.inbox.models` (read, FKs), the summary serializers in `apps.inbox.serializers`, `apps.message_templates.services`, `apps.contacts.services`, `apps.billing.entitlements`. Everything else goes through `common/events.py` signals.

## Demo data
Each app may add `apps/<app>/demo.py` with `seed(workspace) -> None`; `manage.py seed_demo` runs them in `INSTALLED_APPS` order.

## Out of scope for wave 2
Recurring campaigns, audit log, per-number access, analytics app, developer API/API keys, outbound customer webhooks.
