# Moyasar Sandbox Validation & Webhook Confirmation (Phase 8J-B)

Local-only validation guide for the 1SaudiCyber ↔ Moyasar sandbox integration.
**Owner:** Get Solution Company. **Scope:** verify sandbox checkout, browser callback,
and server-verified webhook activation — without deploying, pushing, or committing keys.

> ⚠️ **DO NOT COMMIT KEYS.** Never place real or test Moyasar keys in the repository,
> tests, templates, logs, or any tracked file. Keys live only in a local, git-ignored
> `.env` (already ignored — verified). `MOYASAR_SECRET_KEY` must never reach templates,
> HTML, JavaScript, logs, or browser output. No card data is ever sent to or stored by
> our backend — the Moyasar hosted form handles the card; we only receive an opaque
> payment id + status + our own metadata.

---

## 1. How Moyasar's webhook secret works (confirmed behavior)

Moyasar dashboard webhooks use a **dashboard-defined shared "Secret Token"**, not an
HMAC request signature. When you configure a webhook endpoint in the Moyasar dashboard
and set a secret token, Moyasar **includes that token in the webhook JSON body as a
top-level `secret_token` field**. There is no standardized signature header (unlike
Stripe's `Stripe-Signature`).

Webhook envelope shape (sandbox & live):

```json
{
  "id": "evt_...",
  "type": "payment_paid",
  "created_at": "2026-01-01T00:00:00Z",
  "secret_token": "<the token you set in the dashboard>",
  "data": {
    "id": "<provider_payment_id>",
    "status": "paid",
    "amount": 49900,
    "currency": "SAR",
    "metadata": {
      "internal_payment_id": "123",
      "company_id": "45",
      "subscription_id": "67",
      "plan_code": "basic"
    },
    "source": { "type": "creditcard", "company": "visa", "...": "..." }
  }
}
```

- `amount` is in the **smallest currency unit (halalas)** — SAR × 100.
- `metadata` is the exact object we attached at checkout (`billing.moyasar.checkout_metadata`).
- `source` may contain a masked card brand/last-four; **we do not read or store it.**

### Does our implementation match?

**Yes.** `billing.verification.process_moyasar_webhook`:

1. Reads the shared token from the **top-level body** `secret_token`
   (`payload.get('secret_token')`), compared to `settings.MOYASAR_WEBHOOK_SECRET`
   using `hmac.compare_digest` (constant-time). This is Moyasar's confirmed mechanism.
2. As a harmless, optional fallback only when the body token is absent, it also checks
   `X-Moyasar-Token` / `X-Event-Secret` headers. These header names are **not part of
   Moyasar's documented behavior** and are never required; the body token is authoritative.
   No cryptographic signature is invented.
3. If `MOYASAR_WEBHOOK_SECRET` is unset, the token check is **skipped** and security relies
   entirely on the server-side Fetch Payment verification (below), which is the real gate.

### Source of truth for activation

Regardless of the webhook body, activation **only** happens after a server-side
`GET https://api.moyasar.com/v1/payments/{id}` (HTTP Basic auth, secret key as username)
confirms `status == paid` **and** the fetched `amount`, `currency`, and `metadata`
(`internal_payment_id`, `company_id`, `subscription_id`) match our `Payment` row. A forged
webhook body cannot activate anything, because the decision comes from the authenticated
Fetch result, not the received payload.

Full HMAC/header signature validation is **deferred** (Moyasar does not provide one for
dashboard webhooks); the shared body token + server Fetch is the confirmed, secure design.

---

## 2. Required local env vars (git-ignored `.env` only)

```bash
PAYMENT_PROVIDER=moyasar
MOYASAR_MODE=sandbox
MOYASAR_PUBLISHABLE_KEY=pk_test_<YOUR_SANDBOX_PUBLISHABLE_KEY>     # browser-safe; sandbox only
MOYASAR_SECRET_KEY=sk_test_<YOUR_SANDBOX_SECRET_KEY>          # server-only; NEVER in templates
MOYASAR_WEBHOOK_SECRET=<any strong random string>       # must equal the dashboard token
PUBLIC_BASE_URL=https://<your-local-tunnel>.example     # only when testing the webhook
```

Notes:
- Only the **publishable** key (`pk_test_...`) is exposed to the browser, and only when it
  starts with `pk_test_` (`billing.moyasar.publishable_key_for_template`). A `pk_live_` or
  empty key renders `''` and the checkout shows "Moyasar checkout is not configured yet".
- Leaving these unset keeps the app on `PAYMENT_PROVIDER=manual` (default) — the manual
  billing flow is unchanged and does not require any Moyasar key.

---

## 3. Sandbox test steps (manual, local)

1. Put the sandbox keys in local `.env`, restart `python manage.py runserver`.
2. Register/log in as a company user; open `/billing/`.
3. **Select a plan** (e.g. `basic`) → creates a `pending_payment` subscription + a pending
   `Payment(provider='moyasar')` and redirects to `/billing/payments/<id>/checkout/`.
4. **Checkout page** renders the Moyasar hosted form using the publishable key. Confirm the
   page shows the sandbox notice and the safe disclaimer, and that **no `sk_...` string**
   appears in view-source.
5. Pay with a Moyasar **sandbox test card** (see Moyasar sandbox docs; use only test cards).
6. Moyasar redirects to the **browser callback** `/billing/moyasar/callback/?ipid=<id>&id=<ppid>&status=paid`.
   Confirm the page message: *"Payment result received. Subscription will be activated after
   verification."* — the subscription is **still `pending_payment`** (callback never activates).

### Webhook setup

7. In the Moyasar dashboard, add a webhook pointing to
   `${PUBLIC_BASE_URL}/billing/moyasar/webhook/` with event(s) like `payment_paid`,
   `payment_failed`, and set the **Secret Token = `MOYASAR_WEBHOOK_SECRET`**.
8. For local delivery, expose the dev server via a tunnel (e.g. an HTTPS tunnel) and set
   `PUBLIC_BASE_URL` to that URL. Do **not** deploy.
9. Complete a sandbox payment. Moyasar POSTs the webhook → the server **fetches the payment**
   from the Moyasar API and, if verified `paid` + matching, activates the subscription.
   Confirm `/billing/` now shows the subscription **active**.

---

## 4. Expected callback vs webhook behavior

| Event | Endpoint | Effect |
|------|----------|--------|
| Browser return | `GET /billing/moyasar/callback/` | Records `provider_payment_id`/status; shows "pending verification"; **never activates**. |
| Provider webhook (paid) | `POST /billing/moyasar/webhook/` | Optional token check → server Fetch → verify amount/currency/metadata → **activate** + audit. |
| Provider webhook (failed/cancelled/voided) | `POST .../webhook/` | Marks `Payment` failed/cancelled; **no activation**. |
| Provider webhook (refunded) | `POST .../webhook/` | Marks `Payment` refunded; no activation. |
| Provider webhook (initiated/authorized) | `POST .../webhook/` | Stays pending. |

Webhook HTTP responses: `405` non-POST · `400` malformed JSON / missing id · `403` wrong
shared token · `200` processed (including safely-ignored unknown payment). No stack trace,
path, or secret is ever leaked in the response.

---

## 5. Failure cases (all fail closed — no activation)

- **Missing `MOYASAR_SECRET_KEY`** → Fetch returns `no_secret` → never activates.
- **Fetch/network/API error** → never activates (safe downgrades from body still allowed).
- **Amount mismatch / currency mismatch** → rejected, stays pending.
- **Metadata mismatch** (`internal_payment_id`/`company_id`/`subscription_id`) → rejected.
- **Unknown `provider_payment_id`** → ignored (200), no effect.
- **Forged webhook for another company's payment** → fetched metadata won't match → rejected.
- **Wrong `secret_token`** (when `MOYASAR_WEBHOOK_SECRET` set) → `403`, not processed.
- **Payment not `pending`** or **subscription not `pending_payment`** → not activatable.
- **Duplicate paid webhook** → idempotent (`already_paid`); no double activation, no
  subscription extension, no duplicate rows (row-locked `transaction.atomic`).

---

## 6. Sandbox validation checklist

- [ ] `PAYMENT_PROVIDER=moyasar`, `MOYASAR_MODE=sandbox` in local `.env`
- [ ] `MOYASAR_PUBLISHABLE_KEY=pk_test_...`, `MOYASAR_SECRET_KEY=sk_test_...` (local only)
- [ ] `MOYASAR_WEBHOOK_SECRET` set locally and equals the dashboard token
- [ ] `PUBLIC_BASE_URL` set to a local tunnel **only** while testing the webhook
- [ ] Select plan → pending subscription + pending payment created
- [ ] Checkout page renders the Moyasar form; no `sk_...` in view-source
- [ ] Sandbox payment completes
- [ ] Callback shows "pending verification"; subscription still `pending_payment`
- [ ] Webhook (server-verified) activates the subscription
- [ ] Duplicate paid webhook is idempotent (no re-extension)
- [ ] Failed payment does not activate
- [ ] Missing `MOYASAR_SECRET_KEY` does not activate

---

## 7. Automated coverage (already in `billing/tests.py`)

- `MoyasarWebhookSecretTests` — body `secret_token` accepted / wrong token → 403.
- `MoyasarWebhookEndpointTests` — non-POST 405, malformed 400, unknown-id ignored,
  paid activates after Fetch, fetch-failure/forged-amount no activation, duplicate idempotent.
- `MoyasarMissingSecretTests` — no secret → Fetch safe, no activation.
- `MoyasarCallbackTests` — callback records but never activates; forged callback no effect.
- `MoyasarVerificationServiceTests` — amount/currency/metadata mismatch → no activation;
  status mapping paid/failed/refunded/voided/initiated.

These simulate the Moyasar API via `mock.patch('billing.moyasar.fetch_moyasar_payment')`
(no live API calls, no real keys). A **live sandbox smoke test** (real sandbox keys + real
webhook delivery) remains a manual pre-production step.
