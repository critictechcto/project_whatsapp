# Feature inventory for pricing

Every feature UpChatz has today, so each one can be placed on a plan. Status as of 2026-10-22, checked against the code.

This is the source list for deciding tiers. For how features work, see [features.md](features.md). For the API, see `docs/contracts/`.

**Status**

| Label | Meaning |
|---|---|
| **Built** | In the backend and on a dashboard screen |
| **Partly built** | Backend only, or some of it is missing |
| **Not built** | Claimed on the site or planned, no code |

**Gate today** is what the code checks now:
- a feature key (`has_feature`);
- a quota (`check_quota`);
- or *none*, meaning every plan gets it.

**Plan (to decide)** is left blank on purpose; we fill it in when we set the tiers.

---

## 1. Plans today

From `backend/apps/billing/plans.py` and `entitlements.py`. Prices come only from Razorpay plans (`docs/contracts/billing-razorpay.md`).

| | Starter | Growth | Pro |
|---|---|---|---|
| WhatsApp numbers (`whatsapp_numbers`) | 1 | 2 | 5 |
| Team members incl. pending invites (`members`) | 2 | 5 | 15 |
| Contacts (`contacts`) | 5,000 | 25,000 | 1,00,000 |
| `commerce` | yes | yes | yes |
| `scheduled_campaigns` | – | yes | yes |
| `keyword_automations` | – | yes | yes |
| `analytics` | – | yes | yes |
| `api_access` | – | yes | yes (checked nowhere, see section 4) |

- **Trial:** 14 days on Growth (`TRIAL_PLAN_SLUG`, `TRIAL_DAYS`).
- **Same features:** Growth and Pro have the same feature keys; they differ only in limits.
- **When a subscription is halted, cancelled or expired:** every feature is off, and each limit is frozen at current usage. Nothing is deleted, but nothing new can be added.
- **Only these exist:** three quota metrics and five feature keys. Anything else is not metered (see section 5).

---

## 2. Feature inventory by area

### 2.1 Account, workspace and team

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Sign-up and login | Email and password; access token in memory, refresh token in an HttpOnly cookie | Built | none | |
| Email verification | Link by email; dashboard banner until verified, nothing blocked | Built | none | |
| Password change and reset | Reset by email signs out every session | Built | none | |
| Workspaces | Several businesses per login; name, time zone, business goals | Built | none | |
| Fixed roles | Owner, admin, agent, viewer (`common/roles.py`) | Built | none | |
| Team invitations | Invite by email with a role, resend, revoke, change role | Built | `members` | |
| Onboarding | Goal picker, guided tour, setup checklist ordered by goal | Built | none | |

### 2.2 WhatsApp connection

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Embedded Signup | Connect a number in a few clicks the official way | Built | `whatsapp_numbers` | |
| Coexistence | Keep using the WhatsApp Business app on the same number | Built | `whatsapp_numbers` | |
| Several numbers / accounts | More than one WABA and number per workspace, default number | Built | `whatsapp_numbers` | |
| Number health | Quality rating, messaging-limit tier, display-name status, nightly refresh | Built | none | |
| Safety auto-pause | Campaigns pause on quality drop, template change or account restriction | Built | none | |

### 2.3 Message templates

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Template builder | Marketing, utility, authentication; text/image/video/document/location header; quick reply, URL, phone, copy-code, OTP buttons; live preview | Built | none | |
| Submit, sync, duplicate | Submit to Meta, hourly sync, rejection reasons, duplicate, delete on Meta | Built | none | |
| Template quality | Meta's quality score and status shown | Built | none | |

### 2.4 Contacts and consent

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Contacts | Add, edit, search, delete, custom attributes; a customer who writes in is always saved and counts towards the limit | Built | `contacts` (manual create and import only) | |
| Tags | Coloured tags, bulk add/remove | Built | none | |
| CSV import | Column mapping, dedupe by phone, tag on import, opt-in with source, failed-rows download | Built | `contacts` (rows over limit skipped) | |
| Opt-in / opt-out | Record consent with evidence, full consent history | Built | none | |
| Consent keywords | Per-workspace opt-in and opt-out words; STOP, UNSUBSCRIBE, STOP PROMOTIONS and STOP ALL always apply | Built | none | |
| Opt-in button | Automation action that asks for opt-in with Yes/No buttons | Built | none | |

### 2.5 Team inbox

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Shared inbox | Open, Mine, Unassigned, Closed views; filter by number, unread, search | Built | none | |
| Assignment | Assign to me or a teammate | Built | none | |
| Internal notes | Notes on a conversation, not sent to the customer | Built | none | |
| Media | Send and receive images, video, audio, documents; receive location, contacts, reactions, stickers | Built | none | |
| 24-hour window | Free text inside the window, template outside it | Built | none | |
| Start a conversation | New conversation from a contact | Built | none | |
| Read receipts and live updates | Blue ticks to the customer; realtime socket in the dashboard | Built | none | |

### 2.6 Campaigns

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Broadcast | One approved template to tags (any/all) or picked contacts, from one chosen number | Built | none | |
| Personalisation | Variables from contact field, attribute or fixed text, with fallback; media header | Built | none | |
| Consent rules | Opted-out skipped; marketing needs opt-in; per-user marketing limit handled | Built | none | |
| Cost estimate | Estimated Meta charge in INR before sending | Built | none | |
| Send now | Launch immediately | Built | none | |
| Schedule | One date and time | Built | `scheduled_campaigns` (checked when scheduling and again when due) | |
| Pause, resume, cancel | Control a running campaign | Built | none | |
| Report | Delivery funnel (sent, delivered, read, replied, failed), recipients table, live progress | Built | none | |
| Pacing | Batched sends within Meta's throughput | Built | none | |

### 2.7 Automations

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Welcome / first message rule | Trigger on first inbound message or new contact | Built | none | |
| Away message | Trigger outside business hours; weekly business-hours editor | Built | none | |
| Keyword rules | Exact or contains match | Built | `keyword_automations` (on activate and at run time) | |
| Actions | Up to 5 per rule: send text, send template, add tags, assign, close, send shop menu, send catalog, send collection, ask to opt in | Built | none (commerce actions skip without a store) | |
| Rule options | Priority, stop processing, cooldown, limit to one number; max 10 automated sends per conversation per hour | Built | none | |
| Run log | History of every run with outcome | Built | none | |

### 2.8 Analytics

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Overview | KPI cards compared with the previous period | Built | `analytics` | |
| Reports | Messages, templates, campaigns, team (per member) | Built | `analytics` | |
| Commerce report | Orders, revenue, top products | Built | `analytics` + `commerce` | |
| CSV export | Each report as CSV | Built | `analytics` | |
| Date range | Up to 92 days | Built | `analytics` | |

### 2.9 Sell on WhatsApp

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Catalog: products | Price, sale price, SKU, images, stock, max per order, availability | Built | `commerce` (writes) | |
| Catalog: services | Duration, bookings, advance or full payment | Built | `commerce` (writes) | |
| Collections | Group and order products | Built | `commerce` (writes) | |
| Catalog CSV import | Upsert by SKU, up to 5,000 rows | Built | `commerce` (writes) | |
| Meta native catalog | Connect or create a Meta catalog, sync products, cart and catalog switches per number (needs Meta App Review) | Built | `commerce` (writes) | |
| Shop bot | Menu → collections → product cards → cart in chat, "My orders", talk to a human | Built | `commerce` | |
| Native WhatsApp cart | Accepts carts from Meta catalog | Built | `commerce` | |
| Store settings | Store on/off, shop mode, welcome menu, store link | Built | `commerce` (to turn on) | |
| Delivery checkout | Saved/WhatsApp/typed address, 6-digit pincode, serviceable-pincode list, min order, shipping fee, free shipping above | Built | `commerce` | |
| Cash on delivery | On/off, COD fee, COD order cap, mark collected | Built | `commerce` | |
| Online payments | Seller's own Razorpay or Cashfree; payment links; confirmed by return page and polling, optional webhook | Built | `commerce` | |
| Orders | List, filters, timeline, notes; confirm, packed, shipped (courier/AWB), delivered, cancel, refund mark | Built | `commerce` | |
| Buyer notifications | Order and booking updates, session message or template outside the window; starter templates; one payment reminder per unpaid link | Built | `commerce` | |
| Bookings | Day and time window, reminders (hours before + evening before), confirm/reschedule/cancel buttons, no-show, completed | Built | `commerce` | |
| Booking payments | Advance or full online payment, pay at shop, balance paid later | Built | `commerce` | |
| Offer codes | Percent (with cap) or amount, on all/products/services/items, min order, dates, total and per-customer limits | Built | `commerce` (writes) | |
| Counter redemption | Redeem a code by phone at the shop | Built | `commerce`, `contacts` | |
| Ad attribution | Click-to-WhatsApp ad source saved on offer claims | Built (data only, no report) | `commerce` | |
| Seller alerts | New order/booking, needs attention, cancelled, to up to 3 personal numbers from UpChatz's number; accept, pack, ship, cancel buttons; ORDERS and HELP commands | Built (needs the platform alerts number set up) | none | |
| Stock reservation | Held at checkout, released on cancel or expiry | Built | `commerce` | |

### 2.10 UpChatz's own billing

| Feature | What it does | Status | Gate today | Plan (to decide) |
|---|---|---|---|---|
| Plans and checkout | Monthly or annual; auto-pay subscription or pay once (Razorpay) | Built | n/a | |
| Usage meters | Numbers, members, contacts against the plan | Built | n/a | |
| GST invoices | Invoice numbering per financial year, PDF download, billing profile with GSTIN | Built | n/a | |
| Renewal reminders | Email before a prepaid period ends | Built | n/a | |

### 2.11 Support and services (not software)

What the plan cards promise today (`frontend/src/config/site.ts`).

| Promise | Where | Plan (to decide) |
|---|---|---|
| Email support | Starter | |
| Chat and email support | Growth | |
| Onboarding call and verification help | Pro | |
| Priority phone support | Pro | |
| Custom limits, dedicated onboarding, SLA, invoicing on purchase order, Meta verification help | Enterprise strip on the pricing section | |
| Setup help included | Final call to action on the landing page | |

---

## 3. Meta's message charges

- **How Meta bills:** Meta bills each seller's own WhatsApp Business Account directly, and UpChatz adds no markup (UpChatz is a Tech Provider).
- **What UpChatz shows:** an estimate only, in the campaign wizard, using `WHATSAPP_RATE_CARD_INR` in `config/settings/base.py`.
- **Nothing else:** there is no wallet, credit top-up or re-billing.

---

## 4. Sold but not built

These are claims on the site or the plan cards with no matching feature.

| Claim | Where it's claimed | What exists |
|---|---|---|
| REST API and webhooks, test and live API keys | Growth card, `landing/sections/Developers.tsx`, `Faq.tsx` | Nothing. `api_access` is checked nowhere; `backend/apps/developer_api` has no endpoints |
| Recurring campaigns (daily, weekly, monthly) | Growth card, `Features.tsx` | One-time schedule only |
| Quiet hours; pause or edit an upcoming run | `Features.tsx` | A scheduled campaign can only be cancelled |
| Advanced automation flows | Pro card | Single-step rules with up to 5 actions; no flow builder |
| Custom roles and per-number access | Pro card, `Features.tsx`, `Security.tsx` | Four fixed roles; agents see every number |
| Audit log | Pro card | Consent history only |
| Saved replies | `Features.tsx` (Inbox) | None |
| Auto-distribute conversations | `Features.tsx` (Inbox) | Manual assignment, or the `assign` automation action |
| Contact lists | `Features.tsx` (Contacts) | Tags only |
| Export contacts and message history | `Features.tsx`, `Security.tsx` | Analytics CSV only |
| Meta charges per campaign and per month | `Features.tsx` (Analytics) | Estimate before sending only |
| Number migration from another provider | `GettingConnected.tsx` | Guidance only, no screen |

**Also:** Sell on WhatsApp, the biggest built area, is on every plan (`commerce`), but no plan card mentions it.

---

## 5. Levers for tiering (not metered today)

These could become a plan limit or gate, but the code doesn't count or check them now. This section lists facts only; nothing here is a decision.

| Possible lever | Today |
|---|---|
| Products / services in the catalog | Unlimited |
| Automation rules | Unlimited (5 actions per rule) |
| Campaigns or recipients per month | Unlimited (Meta's tier is the only cap) |
| Orders or bookings per month | Unlimited |
| Seller-alert numbers | Fixed at 3 for everyone |
| Meta native catalog mode vs bot only | Both on every plan with `commerce` |
| Bookings and booking payments | Same gate as products (`commerce`) |
| Offer codes | Same gate as products (`commerce`) |
| Online payments vs COD only | Both on every plan with `commerce` |
| Analytics range / export | 92 days and CSV for everyone with `analytics` |
| Welcome and away rules vs keyword rules | Welcome/away on every plan; keyword gated |
| Extra numbers or members as paid add-ons | Not possible; only plan limits |

---

## 6. Gaps found while listing (resolved 2026-10-22)

- **Plans page showed raw keys.** The dashboard Plans page now names each feature ("Scheduled campaigns", "Sell on WhatsApp"); unknown keys are shown as words (`frontend/src/features/dashboard/billing/plans.ts` `featureLabel`). The mock returns the backend's keys, so tests cover it.
- **Contacts from chats.** Every contact counts towards the `contacts` limit, including ones created when a customer writes in. Those inbound contacts are never blocked, so a customer's message is never dropped; reaching the limit then blocks manual adds and imports. The inbox only starts conversations with existing contacts, so nothing business-initiated creates contacts past the limit.
- **Schedules are re-checked.** When a scheduled campaign is due and the plan no longer has `scheduled_campaigns`, it is paused with the reason and sends nothing; *Resume* sends it now. Resuming into a future time needs the feature.
- **Payment reminder is sent.** `orders.send_payment_reminders` (every 5 minutes) reminds the buyer once per checkout attempt, 15 minutes after the link was sent (`ORDER_PAYMENT_REMINDER_MINUTES`, 0 = off), while the link has more than 5 minutes left.
- **Contract updated.** `docs/contracts/wave-2.md` lists all five feature keys.
- **Old doc updated.** `docs/product/features.md` covers analytics, offers, bookings and booking payments, onboarding, and prices from Razorpay.
