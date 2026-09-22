# Setting up Meta (WhatsApp Business Platform) for UpChatz

This guide connects UpChatz to Meta so businesses can link their own WhatsApp numbers through **Embedded Signup** and send through the **Cloud API**. It assumes the app already runs on `https://app.upchatz.com` (see [app-platform.md](app-platform.md)).

UpChatz is a **Tech Provider**: each business connects its own WhatsApp Business Account (WABA) and, under Meta's current pricing, Meta bills message charges to that business's WABA. UpChatz never holds a customer's number.

> **Never paste the App secret, verify token or any access token into chat, issues, commits or `.do/app.yaml`.** Type them straight into Meta and the DigitalOcean App Spec.

**Tick the boxes as you go.** Part 7 is the final "is everything ready" check.

---

## 0. Before you start

- [ ] `https://app.upchatz.com/readyz/` returns `200` (the app is deployed and healthy).
- [ ] You can sign in at `https://app.upchatz.com/app/login` and have a workspace (you are its owner).
- [ ] Email works (Resend). Meta and your customers will email `support@upchatz.com`, so that mailbox must receive mail.
- [ ] The legal details are filled in `frontend/src/config/site.ts` → `site.legal`, so `https://upchatz.com/privacy/` and `/terms/` are final pages with no "draft" note. **Meta's reviewers open these pages.**
- [ ] You have the business documents for verification: GST certificate or company incorporation papers, the registered address, and a phone number that can take a call or SMS.
- [ ] You have a **test phone number** that is **not** registered on WhatsApp or the WhatsApp Business app. A spare SIM works. Delete WhatsApp from it first if needed.

---

## 1. Business portfolio and verification (start first: it takes days)

1. Go to [business.facebook.com](https://business.facebook.com). Create a business portfolio named **UpChatz**, or open the existing one.
2. **Settings → Business info:** fill in the legal name, address, phone and website `https://upchatz.com`. The legal name must match your documents.
3. **Security Center → Start verification.** Upload the documents. Verify by a domain email at `@upchatz.com`, DNS or phone.
4. Wait for **Verified**. This usually takes 1–5 working days.

- [ ] Business portfolio created, and its details match the legal documents.
- [ ] Business verification submitted.
- [ ] Business verification shows **Verified**.

---

## 2. Create the Meta app

1. Go to [developers.facebook.com](https://developers.facebook.com) → **My Apps → Create app**.
2. Use case: **Other** → app type **Business**. Name it **UpChatz** and connect it to the UpChatz business portfolio.
3. On the app dashboard, **Add product → WhatsApp → Set up**. Meta creates a test WABA and a test number for you. Leave them as they are.
4. **App settings → Basic:**
   - **App domains:** `upchatz.com` and `app.upchatz.com`.
   - **Privacy policy URL:** `https://upchatz.com/privacy/`
   - **Terms of Service URL:** `https://upchatz.com/terms/`
   - **User data deletion:** use the instructions URL `https://upchatz.com/privacy/`. The privacy page explains how to ask for deletion.
   - **App icon** (1024×1024), **category** (Business and pages) and **contact email** (`support@upchatz.com`).
   - Copy the **App ID** and the **App secret** (click *Show*). You need both in step 5.

- [ ] Business app created and linked to the portfolio.
- [ ] WhatsApp product added.
- [ ] App domains, privacy, terms, data deletion, icon, category and contact email filled in and saved.

---

## 3. Facebook Login for Business: Embedded Signup configuration

This is the popup a business sees when it clicks **Connect WhatsApp** in the dashboard.

1. **Add product → Facebook Login for Business.**
2. **Facebook Login for Business → Settings:**
   - **Client OAuth login:** On.
   - **Web OAuth login:** On.
   - **Login with the JavaScript SDK:** On.
   - **Valid OAuth redirect URIs:** `https://app.upchatz.com/`
   - **Allowed domains for the JavaScript SDK:** `https://app.upchatz.com`
   - Save.
3. **Facebook Login for Business → Configurations → Create configuration:**
   - Name: `UpChatz Embedded Signup`.
   - Login variation: **General**. Then choose the **WhatsApp Embedded Signup** template (it may be called *"WhatsApp Embedded Signup configuration with 60 expiration token"* or similar).
   - Access token: **System-user access token** if offered; otherwise the default.
   - Assets: **WhatsApp accounts**.
   - Permissions: `whatsapp_business_management` and `whatsapp_business_messaging`. Leave `business_management` and `catalog_management` off for now; they are only for native catalog mode, which comes later.
   - Create it, then copy the **Configuration ID**.

- [ ] Facebook Login for Business added and its settings saved.
- [ ] Embedded Signup configuration created, and the Configuration ID copied.

> The dashboard already sends the right Embedded Signup options: code response and `sessionInfoVersion: 3`. The site's Content Security Policy allows Meta's SDK on live builds. Nothing needs to change in the code.

---

## 4. Make a webhook verify token

Make up a long random string. It only has to match in two places: DigitalOcean (step 5) and Meta (step 6). On your machine, from `backend/`:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep it in your password manager.

- [ ] Verify token generated and stored in your password manager.

---

## 5. Put the Meta values into DigitalOcean (before the webhook step)

DigitalOcean → **App → Settings → App Spec → Edit**, in the top-level `envs:` list:

| Key | Value | Type |
|---|---|---|
| `META_APP_ID` | App ID from step 2 | plain |
| `META_APP_SECRET` | App secret from step 2 | **SECRET** |
| `META_EMBEDDED_SIGNUP_CONFIG_ID` | Configuration ID from step 3 | plain |
| `META_WEBHOOK_VERIFY_TOKEN` | the string from step 4 | **SECRET** |
| `META_GRAPH_API_VERSION` | `v24.0` (keep unless you deliberately upgrade) | plain |
| `WHATSAPP_GRAPH_CLIENT` | `apps.whatsapp.client.graph.HttpGraphClient` (already set; must **not** be the fake client) | plain |

Save, and wait for the redeploy to finish (App → Activity shows **Deployed**).

The App secret does two jobs: it swaps the Embedded Signup code for a token, and it checks the `X-Hub-Signature-256` signature on every webhook Meta sends. With a wrong secret, every webhook is rejected.

Check that the verify token is live. This should print `ok`:

```bash
curl "https://app.upchatz.com/webhooks/meta/?hub.mode=subscribe&hub.verify_token=<your token>&hub.challenge=ok"
```

A wrong token returns `Forbidden`, which is correct.

- [ ] All five `META_*` values set, secrets marked SECRET, and the redeploy finished.
- [ ] The `curl` above prints `ok`.

---

## 6. Webhook subscription

1. App dashboard → **WhatsApp → Configuration → Webhook → Edit**:
   - **Callback URL:** `https://app.upchatz.com/webhooks/meta/`
   - **Verify token:** the string from step 4.
   - Click **Verify and save**. Meta calls the URL and it must answer with the challenge, which step 5 confirmed.
2. **Webhook fields → Manage.** Subscribe to each of these (the backend handles all of them):
   - `messages`: incoming messages and delivery or read statuses.
   - `message_template_status_update`: template approved, rejected or paused.
   - `message_template_quality_update`
   - `template_category_update`
   - `phone_number_quality_update`: quality rating and messaging limit changes.
   - `account_update`: bans, restrictions and business verification changes.

You don't subscribe each customer's WABA yourself. UpChatz does it automatically when a business finishes Embedded Signup, and **Resync** on the dashboard's WhatsApp page repeats it.

- [ ] Callback URL verified and saved.
- [ ] All six webhook fields subscribed.

---

## 7. Test everything in development mode

While the app is in **Development** mode, only people with a role on the app can use Embedded Signup. Add yourself (and any tester) under **App roles → Roles**.

1. Sign in to `https://app.upchatz.com`, open **WhatsApp → Connect WhatsApp**, and finish the Meta popup with your test number (the one from step 0). Create or choose the business and WABA, add the number, and verify it by SMS or call.
2. Back in the dashboard, the number should show as connected. If it says *pending*, click **Resync**.
3. **Templates:** create a simple UTILITY template and submit it. Within minutes to hours its status should change to **Approved** by itself (this proves `message_template_status_update` webhooks arrive).
4. **Contacts:** add your personal WhatsApp number as a contact, with opt-in recorded.
5. **Send:** send the approved template to that contact from a campaign or the inbox. It should arrive on your phone, and the ticks in the inbox should go sent → delivered → read (this proves the `messages` status webhooks).
6. **Reply** from your phone. The message should appear live in the **Inbox**, and you can now reply freely inside the 24-hour window.
7. **STOP:** send `STOP` from your phone. The contact should be marked opted out, and campaigns should skip them.

- [ ] Test number connected through Embedded Signup.
- [ ] Template approved automatically (status webhook works).
- [ ] Template delivered to a real phone, and ticks updated.
- [ ] Inbound reply shows live in the inbox, and a free-form reply works.
- [ ] STOP marks the contact opted out.

**If something fails**, look in DigitalOcean → App → **Runtime Logs** (component `api` for signup and webhooks, `worker` for sending):
- `Meta webhook verification rejected`: the verify token doesn't match (step 5 and step 6).
- Webhooks arrive but nothing updates: wrong `META_APP_SECRET` (signature check fails), or the fields in step 6 aren't subscribed.
- Popup closes with an error: `app.upchatz.com` is missing from *Allowed domains for the JavaScript SDK* (step 3), or you don't have a role on the app.
- Number stuck on *pending*: click **Resync** on the WhatsApp page. A number still used in the WhatsApp Business app can't be registered.

---

## 8. Go live (so any business can connect)

1. **Become a Tech Provider.** App dashboard → WhatsApp → **Tech Provider / Partner** onboarding (the exact name may differ). Business verification from step 1 must be done.
2. **App Review → Permissions and features.** Request **Advanced access** for:
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
   - For each one, describe how UpChatz uses it. Attach a **screen recording** that shows a business signing in, connecting a number through Embedded Signup, creating a template and sending a message from the dashboard. Use the English UI and show the full flow without cuts.
3. Wait for approval, usually a few days. Answer any reviewer questions from `support@upchatz.com`.
4. Switch the app from **Development** to **Live** (the toggle at the top of the app dashboard).
5. Connect one real business, or your own real number, from start to finish (repeat part 7 once in Live mode).

- [ ] Tech Provider onboarding complete.
- [ ] Advanced access approved for `whatsapp_business_management` and `whatsapp_business_messaging`.
- [ ] App switched to **Live**.
- [ ] One real business connected and sending in Live mode.

---

## 9. Optional, later

### UpChatz alerts number (order alerts to sellers)
This is UpChatz's own number, used to send sellers alerts about new orders. Leave it empty to turn alerts off; everything else still works.
1. In **your own** WABA (not a customer's), add a dedicated number that isn't used anywhere else.
2. **Business settings → Users → System users:** create an admin system user and give it the UpChatz app and that WABA (full control). Then **Generate token** with `whatsapp_business_management` and `whatsapp_business_messaging`, and expiry **Never**.
3. In the DigitalOcean App Spec, set `PLATFORM_WA_WABA_ID`, `PLATFORM_WA_PHONE_NUMBER_ID`, `PLATFORM_WA_DISPLAY_PHONE_NUMBER` (for example `+91 98xxxxxxx`) and `PLATFORM_WA_ACCESS_TOKEN` (**SECRET**).
4. After the redeploy, open the **api** component's **Console** and run `python manage.py sync_platform_templates`. Wait until Meta approves the templates.

- [ ] Alerts number added, system user token generated.
- [ ] `PLATFORM_WA_*` set and the templates synced and approved.

### Native catalog mode (optional)
It needs extra App Review for `catalog_management` and `business_management`, plus Meta's review of each product. Bot mode (menus and cart) already works without it.

---

## 10. Final readiness checklist

Everything below must be ticked before you tell customers to connect:

- [ ] **Business:** portfolio verified; privacy and terms pages final (no draft note).
- [ ] **App:** Business app with WhatsApp and Facebook Login for Business; domains, icon and contact email set.
- [ ] **Embedded Signup:** configuration created with `whatsapp_business_management` and `whatsapp_business_messaging`; `app.upchatz.com` in the allowed JS SDK domains.
- [ ] **DigitalOcean:** `META_APP_ID`, `META_APP_SECRET`, `META_EMBEDDED_SIGNUP_CONFIG_ID`, `META_WEBHOOK_VERIFY_TOKEN`, `META_GRAPH_API_VERSION` set; `WHATSAPP_GRAPH_CLIENT` is the HTTP client.
- [ ] **Webhook:** `https://app.upchatz.com/webhooks/meta/` verified; all six fields subscribed.
- [ ] **Tested:** signup → template approved → sent → delivered/read → inbound reply → STOP, all in the dashboard.
- [ ] **Review:** Tech Provider done; both permissions have Advanced access; app is **Live**.
- [ ] **Security:** the App secret and tokens exist only in DigitalOcean and your password manager; any value that was ever pasted into chat has been rotated.
