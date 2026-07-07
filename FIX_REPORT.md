# FIX_REPORT — CyberTrust KSA

Phased hardening (P0 → P1 → P2). One item per section. Secrets via environment only;
no `.env` committed. Governing principle preserved: **Rules first → AI advisory → human
auditor final.**

---

## P0 — Critical blockers

### P0-1 — Unify `DJANGO_SECRET_KEY` + fail-closed in production
- **Was:** `settings.py` read `DJANGO_SECRET_KEY` with an insecure default, while `.env.example`
  and `README.md` told users to set `SECRET_KEY` (name mismatch) → production could silently run
  on the exposed default key. No boot-time guard.
- **Now:** single env var name `DJANGO_SECRET_KEY` everywhere; a fail-closed check raises
  `ImproperlyConfigured` at startup when `DEBUG=False` and the key is missing or equal to the
  default. No-op under `DEBUG` or the test runner.
- **Files:** `cybertrust_ksa/env_checks.py` (new helper), `cybertrust_ksa/settings.py`,
  `.env.example`, `README.md`.
- **Test:** `core/tests_env_checks.py::SecretKeyValidationTests` (5 cases: prod missing/default →
  raise; prod real key → boots; DEBUG and test-runner → allowed).
- **Migration:** none.
- **Status:** ✅ `check` clean · `makemigrations --check` no changes · 5/5 tests OK.

### P0-2 — Safe production defaults (DEBUG / ALLOWED_HOSTS / CORS)
- **Was:** `DEBUG` defaulted `True`, `ALLOWED_HOSTS` defaulted `*`, `CORS_ALLOW_ALL_ORIGINS = DEBUG`
  → an unconfigured deploy ran wide open.
- **Now:** `DEBUG` defaults `False`; `ALLOWED_HOSTS` defaults empty and is validated fail-closed
  (`ImproperlyConfigured` when `DEBUG=False` and hosts are empty or `*`); under the test runner a
  `testserver/localhost` fallback keeps tests env-independent. `CORS_ALLOW_ALL_ORIGINS` is now
  `False` by default in production (tracks the safe `DEBUG`).
- **Files:** `cybertrust_ksa/env_checks.py` (`validate_allowed_hosts`), `cybertrust_ksa/settings.py`.
- **Test:** `core/tests_env_checks.py::AllowedHostsValidationTests` (5 cases: prod empty/`*` → raise;
  prod explicit host → boots; DEBUG and test-runner → allowed).
- **Migration:** none.
- **Status:** ✅ `check` clean · no migrations · env 10/10 · core+dashboard+auditor_portal 298 OK.

### P0-3 — OpenAI client built outside try → graceful degradation
- **Was:** `classify_company` / `analyze_evidence` / `generate_gap_analysis` built the client
  (`get_openai_client()`) *before* the try; with an empty `OPENAI_API_KEY` the client raised
  `OpenAIError` uncaught → HTTP 500.
- **Now:** each function early-returns a safe advisory result `{'ai_available': False, …}` when no
  key is set; the client build + call now sit inside the existing try/except; the client uses
  `timeout=30s, max_retries=2`. Governing principle unchanged — these are advisory/insufficient
  results, never a final verdict.
- **Files:** `ai_engine/services.py` (`ai_enabled()` added; three functions guarded).
- **Test:** `ai_engine/tests_ai_guard.py` (empty key → all three degrade safely, no network,
  `insufficient_evidence` for evidence; key present → `ai_enabled()` True).
- **Migration:** none.
- **Status:** ✅ `check` clean · no migrations · ai_engine 6/6 · compliance evidence pipeline 6/6.

### P0-5 — Remove embedded admin credentials
- **Was:** `create_admin.py` seeded a hardcoded superuser (`admin@cybertrust.sa` / `CyberTrust2024`).
- **Now:** credentials read from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (optionally `ADMIN_FIRST_NAME` /
  `ADMIN_LAST_NAME`); the script exits with an error if either is missing — no default password.
  Logic extracted to a pure, testable helper.
- **Files:** `create_admin.py` (rewired), `core/admin_bootstrap.py` (new helper).
- **Test:** `core/tests_admin_bootstrap.py` (missing → refuse; valid env → creates superuser;
  idempotent). Repo scan confirms no `CyberTrust2024` / `admin@cybertrust.sa` literals remain.
- **Migration:** none.
- **Status:** ✅ `check` clean · no migrations · 4/4 tests OK · secret scan clean.

### P0-6 — Evidence upload: real content-type validation (magic bytes)
- **Was:** both upload paths (`upload_evidence`, `evidence_upload_v2`) validated by file extension
  only → a `.exe` renamed `.pdf` passed.
- **Now:** a shared validator sniffs the leading bytes with `filetype`: a recognised type must
  match the declared (allowed) extension; unrecognised (`None`) is accepted only for the explicit
  text allowlist (txt/csv/md) — never rejected merely because sniffing returned `None`. Applied to
  BOTH paths. Rejection is a safe, path-free bilingual message; no 500.
- **Files:** `compliance/upload_validation.py` (new), `compliance/views.py` (both paths),
  `requirements.txt` (`filetype==1.2.0`, pure-Python, no libmagic).
- **Test:** `compliance/tests_upload_validation.py` (8 unit + 2 view-rejection on both paths);
  existing valid-upload tests still green (EvidenceValidation + hotfix_evidence 27/27).
- **`pip check`:** `No broken requirements found.`
- **Migration:** none.
- **Status:** ✅ `check` clean · no migrations · 10/10 new · 27/27 existing upload tests OK.

### Hotfix (during P0-6) — template comment leak in evidence status badge
- **Was:** `templates/components/evidence_status.html` had a multi-line `{# … #}` comment; Django's
  `{# #}` is single-line only, so the comment text leaked into the rendered evidence/upload page.
- **Now:** converted to a `{% comment %}…{% endcomment %}` block.
- **Files:** `templates/components/evidence_status.html`.
- **Test:** regression assertions in `tests_auditor_verdict_status.py` (rendered page must not
  contain `cognitive conflation` / `INDEPENDENT dimensions`).
- **Status:** ✅ local fix + regression test (11/11); goes live on the next push after P0 review.
- **Open question (raised to owner):** "AI processing report didn't appear" — needs clarification
  of which flow/page (checklist path is human-review by design and shows no AI; control-detail path
  runs AI). Related to P1-1 (v1/v2 evidence-path duality). Not guessed.

### P0-4 — Test suite green from a clean venv (no collectstatic)
- **Was:** `pdfplumber` undeclared (PDF extraction + report tests failed in a clean image);
  `ManifestStaticFilesStorage` made admin/static tests fail with "Missing staticfiles manifest"
  unless `collectstatic` had been run first.
- **Now:** `pdfplumber` (+ pinned transitive deps) added to `requirements.txt`; under `TESTING` the
  staticfiles backend is the plain non-manifest `StaticFilesStorage`, so `{% static %}` needs no
  manifest. OpenAI-less test paths already degrade safely (P0-3).
- **Files:** `requirements.txt`, `cybertrust_ksa/settings.py`.
- **Exact command (clean image, no collectstatic):**
  `docker run --rm --entrypoint python <image> manage.py test <apps>`.
- **Migration:** none.
- **Status:** ✅ Proven in a freshly built container with NO collectstatic:
  other apps (dashboard/auditor_portal/core/monitoring/api/risk) **394 OK** (previously 380 with 3
  manifest errors); compliance **785 OK** (pdfplumber). `pip check` clean.

---

---

## P1 — High priority

### P1-6 — Data sovereignty gate for external AI (PDPL / NCA)
- **Was:** evidence analysis / classification / gap-analysis sent client text to OpenAI (outside
  the Kingdom) whenever a key was present — no residency control.
- **Now:** new `AI_DATA_RESIDENCY_MODE` (`disabled` default | `external` | `local`). External LLM
  calls happen only when mode is `external` AND a key is set (`external_ai_allowed()`); otherwise a
  safe advisory/insufficient result is returned and **no text leaves**. `local` is reserved for a
  future in-Kingdom adapter (treated as no-external for now). Governing principle preserved
  (advisory only). NOTE: with a key set, AI stays OFF until `AI_DATA_RESIDENCY_MODE=external`.
- **Files:** `cybertrust_ksa/settings.py`, `ai_engine/services.py`.
- **Test:** `ai_engine/tests_data_residency.py` (disabled+key → no external call, mocked client
  asserted uncalled; local → no external; external w/o key → blocked; external+key → calls).
- **Migration:** none.
- **Status:** ✅ `check` clean · no migrations · ai_engine + pipeline + ai_state 17/17 OK.

### P1-5 — Auditor independence / conflict of interest
- **Was:** `can_submit_final_verdict` let any staff/superuser sign any company's verdict; no
  affiliation check.
- **Now:** anyone whose `user.company` is the audited company is blocked (conflict of interest),
  even staff. Auditors are platform-side (no company link) so only true self-audits are blocked.
- **Files:** `compliance/auditor_verdict.py`.
- **Test:** `tests_auditor_verdict_status.py::VerdictIndependenceTests` (company-affiliated staff
  blocked + raises VerdictError; independent staff allowed).
- **Migration:** none. **Status:** ✅.

### P1-6 (gap closure) — checklist AI path now obeys residency
- **Was:** `evidence_ai_analyzer.OpenAIEvidenceProvider.analyze` checked only the API key, bypassing
  the P1-6 data-residency gate (a second external-AI path).
- **Now:** it calls `external_ai_allowed()` — no evidence text leaves unless residency is `external`.
- **Files:** `compliance/evidence_ai_analyzer.py`.
- **Test:** `ai_engine/tests_data_residency.py::ChecklistProviderResidencyTests`.
- **Migration:** none. **Status:** ✅ (33 tests green with verdict + residency + analyzer suites).

### OCR enablement — Tesseract + poppler in the image
- **Was:** Dockerfile installed no OCR system packages, so scanned-PDF/image evidence yielded no
  extractable text → AI/extraction gated off for those files.
- **Now:** `tesseract-ocr`, `tesseract-ocr-ara`, `poppler-utils` installed in the image.
- **Files:** `Dockerfile`. **Test:** build-time (image builds; `tesseract` present). **Status:** ✅.

### P1-1 / P1-2 / P1-3 — deferred (documented, not rushed)
Large/architectural (v1↔v2 consolidation; conditional per-control applicability; rule-engine
evaluation criteria). Require deliberate design; not safe as a tail-of-session change. P1-4 Moyasar
verification intentionally deferred: manual payment is the shipped default; Moyasar stays gated
behind config until the account agreement + `.env` keys are added.

---

## Deploy note (surfaced by P0-1/P0-2 fail-closed)
After P0, a production container (`DEBUG=False`) **will refuse to boot** unless the server `.env`
sets a strong `DJANGO_SECRET_KEY` **and** an explicit `ALLOWED_HOSTS` (no `*`). This is the intended
hardening. Update the server `.env` (use the name `DJANGO_SECRET_KEY`, not the old `SECRET_KEY`)
before deploying.
