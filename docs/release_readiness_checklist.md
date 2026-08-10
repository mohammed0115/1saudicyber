# 1SaudiCyber — Release Readiness Checklist (Phase 8K-A)

> **Local-only readiness document.** Nothing here has been deployed, pushed, or run
> against production. No real keys, no card data, no live payment calls.

---

## A) Release Summary

| Field | Value |
|-------|-------|
| Product | **1SaudiCyber** (CyberTrust KSA) — AI-assisted cybersecurity **readiness** platform |
| Owner / operator | Get Solution Company (شركة احصل الحل) |
| Branch | `cybertrust-execution` |
| Current HEAD | `de7b058` — Document Moyasar sandbox validation checklist |
| Local readiness | **Green** — `manage.py check` clean; migrations consistent; full suite passing |
| Commercial readiness estimate | **~95%** — feature-complete for a commercial MVP; remaining 5% is a **manual live-sandbox payment smoke test** + standard deploy config |
| Database | PostgreSQL in prod (via `POSTGRES_*`); SQLite locally for dev/tests |

**Included in this release:** company onboarding → classification → controls → evidence
upload + text extraction → deterministic gap engine → risk/remediation → commercial HTML
report → PDF export → subscription plans & billing → Moyasar sandbox checkout → webhook
server-verified activation → plan feature limits & access control → Get Solution CRM →
auditor workflow → OTP / forgot-password. The platform provides **internal readiness tools
only — it does not issue an official certification or a government accreditation.**

---

## B) Feature Coverage

| Area | Status | Notes |
|------|--------|-------|
| Company onboarding / registration / login | ✅ | Role-guarded; unlinked users get a safe no-company page |
| Classification / applicability / controls | ✅ | Deterministic engine; control counts unchanged |
| Evidence upload | ✅ | Tenant-scoped; file-type/size validated; no fake OCR |
| Text extraction | ✅ | Truthful extraction gate; never 500 on bad files |
| Gap engine | ✅ | Deterministic internal readiness; POST recalc gated by plan |
| Risk / remediation | ✅ | Generated from gaps; status updates; auditor read-only |
| Commercial HTML report | ✅ | Handles empty + populated data; safe disclaimer |
| PDF export | ✅ | Tenant-scoped; plan/limit gated; safe fallback on error |
| Subscriptions / plans | ✅ | Single subscription per company; trial + 4 seeded plans |
| Moyasar sandbox checkout | ✅ | pk_test only to browser; hosted form; no card data to us |
| Moyasar webhook verification | ✅ | Server-side Fetch is source of truth; activation gated |
| Feature limits / access control | ✅ | Flag + limit enforcement; soft on no-subscription (by design) |
| CRM (platform-admin) | ✅ | Staff-only; subscription/payment/feature/usage summaries |
| Auditor workflow | ✅ | Register → pending → approve/suspend; read-only company context |
| OTP / forgot password | ✅ | EmailOTP model; safe messaging |

---

## C) Required Environment Variables

Set via a **git-ignored `.env`** (already ignored). **No real values below.**

### Core
```bash
DJANGO_SECRET_KEY=<strong-random-secret>
DEBUG=False                      # True only for local dev
ALLOWED_HOSTS=example.com,www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com
SITE_URL=https://example.com
PUBLIC_BASE_URL=https://example.com   # used for Moyasar callback/webhook absolute URLs
```

### Database (PostgreSQL in production)
```bash
POSTGRES_DB=<db>
POSTGRES_USER=<user>
POSTGRES_PASSWORD=<password>
POSTGRES_HOST=<host>
POSTGRES_PORT=5432
DB_CONN_MAX_AGE=60
# (local dev falls back to SQLite automatically when POSTGRES_* is unset)
```

### Email
```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=<smtp-host>
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<user>
EMAIL_HOST_PASSWORD=<password>
DEFAULT_FROM_EMAIL=no-reply@example.com
```

### Payments / Moyasar
```bash
PAYMENT_PROVIDER=moyasar          # 'manual' (default) | 'moyasar'
MOYASAR_MODE=sandbox              # 'sandbox' | 'live'
MOYASAR_PUBLISHABLE_KEY=pk_test_<sandbox-publishable>   # browser-safe (pk_test only exposed)
MOYASAR_SECRET_KEY=sk_test_<sandbox-secret>             # SERVER-ONLY; never in templates/logs
MOYASAR_WEBHOOK_SECRET=<shared-token-matching-dashboard>
```

### Security (auto-applied when `DEBUG=False` and not testing — see settings.py:231)
`SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS=31536000` (+ subdomains/preload),
`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_CONTENT_TYPE_NOSNIFF`,
`SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `healthz` redirect-exempt.
A Content-Security-Policy is defined.

### Optional (AI advisory / async / retention)
```bash
OPENAI_API_KEY=<optional>   OPENAI_MODEL=<optional>     # AI is advisory-only; safe if unset
CELERY_BROKER_URL / CELERY_RESULT_BACKEND / CELERY_TASK_ALWAYS_EAGER
RETAIN_AUDIT_LOGS_DAYS / RETAIN_AI_LOGS_DAYS / RETAIN_ALERTS_DAYS / RETAIN_VERIFICATION_TOKENS_DAYS
```

---

## D) Migration Checklist

`makemigrations --check --dry-run` → **No changes detected** (models & migrations in sync).
The fresh test database applies **all** migrations cleanly (full suite green), so every
migration below is verified-applicable.

**Apply on target DB:** `python manage.py migrate`

Key app migration state (local dev DB at time of writing):

| App | Latest migration | Applied on local dev DB |
|-----|------------------|--------------------------|
| core | `0005_emailotp` | ✅ |
| billing | `0001_initial`, `0002_plan_companysubscription_activated_at_and_more`, `0003_starter_plans` | ✅ |
| auditors | `0002_companycrmnote_companycrmprofile` | ⏳ **pending on dev DB** — run `migrate` |
| compliance | `0016_controlgapassessment` (of 0001–0016) | ⏳ **pending on dev DB** — run `migrate` |
| risk | `0001_initial` | ✅ |
| monitoring | `0002_...monitoringfinding` | ✅ |
| ai_engine | `0002_initial` | ✅ |
| auditor_portal | `0003_initial` | ✅ |

> `auditors/0002` (CRM notes/profile) and `compliance/0016` (ControlGapAssessment) are the
> two migrations pending on the **local dev SQLite DB** — they must be applied on any
> target environment. They apply cleanly (proven by the test DB). No data migration hazards
> beyond additive tables. `billing/0003_starter_plans` seeds the 4 plans idempotently.

---

## E) Pre-release Test Checklist

```bash
python manage.py check                          # → 0 issues
python manage.py makemigrations --check --dry-run # → No changes detected
python manage.py test                           # → full suite (1421 tests) OK
```

Safety scans (all confirmed CLEAN this phase):
```bash
# Unsafe affirmative certification/accreditation wording (must be empty)
grep -rniE "official certification|official accreditation|government accredited|certified by (nca|aramco|sabic)|معتمد من (nca|أرامكو|سابك)" templates/ | grep -viE "not an official|not a government|لا يُعد|لا يمثّل|لا تُعد|never"
# Real Moyasar keys anywhere (must be empty; test placeholders excluded)
grep -rnE "sk_(test|live)_[A-Za-z0-9]{6,}|pk_live_[A-Za-z0-9]{6,}" . --include=*.py --include=*.html | grep -vE "\.venv/|secretmustnotleak|shouldnevershow"
# Card-data fields in billing (must be empty)
grep -rniE "card_number|cvv|cvc|card_holder|\bpan\b" billing/ templates/billing/
# Automated: core.tests_uat scans all templates (negation-aware) for the above
```

---

## F) Manual Smoke Test Checklist

### Company journey
- [ ] Register + login as company user
- [ ] `/billing/` renders (features, limits, usage panel)
- [ ] Start trial → subscription active (trial)
- [ ] Select plan → pending subscription + pending Moyasar payment
- [ ] Moyasar sandbox checkout renders (pk_test only; no `sk_` in source)
- [ ] Complete sandbox payment → callback shows **"pending verification"** (not active)
- [ ] Webhook delivered → server-verified → subscription **active**
- [ ] Evidence upload works; unsupported types rejected safely
- [ ] Text extraction runs without 500
- [ ] Gap recalculation (POST) works
- [ ] Risk generation (POST) works
- [ ] Remediation status update works
- [ ] Commercial HTML report renders
- [ ] PDF export downloads a PDF

### CRM journey (staff/superuser only)
- [ ] Platform-admin login; company list + detail
- [ ] Subscription + Moyasar payment summary (no secrets/card data)
- [ ] Feature/usage summary (evidence/PDF/frameworks)
- [ ] CRM notes / follow-up
- [ ] User linking / unlinking
- [ ] Auditor approval

### Auditor journey
- [ ] Auditor registration → pending state
- [ ] Admin approve / reject / suspend / reactivate
- [ ] Auditor portal accessible after activation
- [ ] Auditor **cannot** reach company billing/evidence/company-portal routes

---

## G) Payment Readiness Checklist

- [ ] Sandbox keys present in **local `.env` only** (`pk_test_` / `sk_test_`)
- [ ] Webhook configured in Moyasar dashboard → `${PUBLIC_BASE_URL}/billing/moyasar/webhook/`
- [ ] Dashboard **Secret Token == `MOYASAR_WEBHOOK_SECRET`**
- [ ] Callback URL correct → `${PUBLIC_BASE_URL}/billing/moyasar/callback/`
- [ ] Server-side Fetch verification works (secret key valid)
- [ ] Duplicate paid webhook is idempotent (no re-activation/extension)
- [ ] failed / refunded / cancelled do **not** activate
- [ ] Browser callback **never** activates a subscription
- [ ] Missing `MOYASAR_SECRET_KEY` → no activation
- [ ] See `docs/moyasar_sandbox_validation.md` for full sandbox steps

---

## H) Security Checklist

- [x] No real secrets/keys in repo (scan CLEAN; only fake test placeholders)
- [x] `.env` git-ignored and untracked
- [x] No card data stored (no card fields on `Payment` model or templates)
- [x] No unsafe certification/accreditation wording (negation-aware template scan)
- [x] Tenant isolation verified (company A ⟂ B: evidence/reports/PDF/payments/usage)
- [x] Role separation (company / auditor / staff) via explicit portal guards
- [x] CSRF preserved everywhere except the external webhook (csrf-exempt but token+fetch protected)
- [x] Webhook protected by shared token (body `secret_token`) + server-side Fetch
- [x] PDF export tenant-scoped (own company only)
- [x] CRM staff-only
- [x] `MOYASAR_SECRET_KEY` never rendered to templates/HTML/JS/logs
- [ ] Production hardening auto-enables when `DEBUG=False` — verify on target host

---

## I) Rollback Checklist (documentation only — do not execute here)

- [ ] **Record current commit hash** before release: `git rev-parse HEAD`
- [ ] **DB backup** before migrating: `pg_dump` of the production database
- [ ] **Media backup** before release (uploaded evidence files)
- [ ] **App rollback placeholder:** redeploy previous known-good commit hash
- [ ] **Migration rollback caution:** additive tables (`auditors/0002`, `compliance/0016`)
      are safe to keep; reverse only with a tested `migrate <app> <prev>` and a fresh backup
- [ ] **Payment rollback caution:** never delete `Payment`/subscription rows; disable
      new charges by setting **`PAYMENT_PROVIDER=manual`** (instant, safe fallback — checkout
      shows manual flow, no Moyasar calls)
- [ ] Pause the Moyasar dashboard webhook if halting payment processing

---

## J) Known Remaining Risks

1. **Live sandbox payment test is still manual** — automated tests mock the Moyasar API; a
   real sandbox payment + real webhook delivery must be exercised once (owner-provided keys).
2. **No-subscription soft behavior is an intentional product decision** — internal readiness
   tools stay open without a subscription; only plan-disabled flags / reached limits hard-block.
3. **`max_frameworks` is display-only** — shown in billing/CRM; not a hard gate (no paid
   framework-selection action to bind it to yet).
4. **Arabic shaping in PDF deferred** — PDF export works; advanced Arabic glyph shaping is not
   implemented in this release.
5. **PDF-export usage counting is AuditLog-based** — reliable locally; not a transactional
   counter (acceptable for MVP).
6. **No recurring billing / refunds / invoices** — out of scope this release.
7. **Full webhook HMAC/header signature deferred** — Moyasar provides none for dashboard
   webhooks; security relies on the shared body token + server-side Fetch (confirmed design).

---

## K) Final GO / NO-GO Matrix

| Dimension | Status | Notes |
|-----------|--------|-------|
| Code tests | ✅ GO | Full suite green (1421 tests) |
| Migrations | ✅ GO | In sync; apply `auditors/0002` + `compliance/0016` on target |
| Security scan | ✅ GO | No secrets / no card data / no unsafe wording |
| Payment readiness | ⚠️ GO-with-condition | Code verified; **manual live-sandbox smoke test pending** |
| CRM readiness | ✅ GO | Staff-only; safe summaries |
| Company journey | ✅ GO | End-to-end covered + happy-path test |
| Auditor journey | ✅ GO | Role isolation verified |
| Legal / trust wording | ✅ GO | Internal-readiness framing; no certification claims |
| Deployment readiness | ⏸️ DEFERRED | Local-only phase; deploy config/hardening on target host |
| **Final recommendation** | **✅ GO for release preparation** | Ship after (1) applying migrations on target, (2) one manual live-sandbox payment test, (3) production env/hardening review |

---

*Generated for release preparation only. No deployment, push, SSH, or production change was
performed. Verify production hardening (`DEBUG=False`, HTTPS, cookies) on the target host.*
