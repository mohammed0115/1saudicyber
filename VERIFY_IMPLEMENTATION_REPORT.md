# VERIFY_IMPLEMENTATION_REPORT

CyberTrust KSA — verification-and-repair pass.
Date: 2026-06-09 · Django 6.0.6 · Python 3.12 · SQLite (dev).

This report verifies the **claimed** partial-implementation features against the actual
code, tests run, and the authoritative source documents (SRS v1.0, Aramco/SACS-002 third-party
report template, consolidated control spreadsheets). Source text **was** extracted — see
[Source documents reviewed](#source-documents-reviewed) at the end.

Governing principle confirmed in code: **Rules First → AI Second → Auditor Final**
(AI verdict stored separately in `Evidence.ai_*` / `CompanyControl.ai_verdict`; never written
to the final/auditor field directly — see [compliance/services.py](compliance/services.py#L56-L64)).

## Verification matrix

| # | Claimed feature | Evidence in code | Files inspected | Test coverage | Status | Required fix |
|---|-----------------|------------------|-----------------|---------------|--------|--------------|
| 1 | `/api/v1` DRF app + JWT | `api` app registered; SimpleJWT issued on register; `IsAuthenticated` default | [api/views.py](api/views.py), [api/urls.py](api/urls.py), [cybertrust_ksa/settings.py:113](cybertrust_ksa/settings.py#L113) | `ApiTests` (register→JWT, controls 401 w/o auth, controls 200 w/ Bearer) | **PASS** | — |
| 2 | Celery + beat | 4 `@shared_task`s; `CELERY_BEAT_SCHEDULE` (daily/monthly/checks); sync fallback in upload | [monitoring/tasks.py](monitoring/tasks.py), [cybertrust_ksa/celery.py](cybertrust_ksa/celery.py), [settings.py:152](cybertrust_ksa/settings.py#L152) | Service layer tested (`recalculate_score`, `generate_monthly_report`); task wrappers/beat not exercised | **PARTIAL** | Needs Redis to run live; no eager-mode test of the task wrappers. Functional but unproven end-to-end. |
| 3 | SSE realtime feed | `event_stream` SSE endpoint (`text/event-stream`, keep-alive, 10-min cap) | [monitoring/views.py:74](monitoring/views.py#L74) | New `RealtimeTemplateTests` (page renders) | **PASS (after fix)** | **The `realtime_monitoring` page 500'd** (slice-then-filter). Fixed; see PATCH report. SSE stream still has no automated test. |
| 4 | Email verification | token model + `send_verification_email` + `verify_email` view; console backend in dev | [core/services.py:6](core/services.py#L6), [core/views.py:177](core/views.py#L177), [core/models.py:148](core/models.py#L148) | `EmailVerificationTests` (full verify flow) | **PASS** | — (real SMTP needs env vars) |
| 5 | TOTP MFA | `pyotp` enroll + challenge; `mfa_enabled/secret` on User; login defers to challenge | [core/services.py:43](core/services.py#L43), [core/views.py:143](core/views.py#L143) | `MFATests` (valid + invalid code) | **PASS** | — |
| 6 | PDF / Excel reporting | `reportlab` gap-analysis PDF + `openpyxl` controls workbook | [dashboard/reports.py](dashboard/reports.py) | `ReportingTests` (PDF `%PDF`, XLSX `PK` magic bytes) | **PASS** | — |
| 7 | DOCX / XLSX / TXT extraction | dispatch by extension to docx/openpyxl/text readers | [ai_engine/services.py:68-120](ai_engine/services.py#L68) | `ExtractionTests` (txt, docx, xlsx) | **PASS (after fix)** | **`openpyxl` was missing from `requirements.txt`** → clean install breaks XLSX upload + seeding. Added. |
| 8 | 334 controls seeded | DB holds exactly **334** (NCA 148 + Aramco 92 + SABIC 94); seeded from shipped spreadsheets | [seed_all_controls.py](compliance/management/commands/seed_all_controls.py), `compliance/data/*.xlsx` | Verified by query; `ApiTests`/`MonitoringTests` build control sets | **PASS** | Matches Evidence Matrix (334 rows). |
| 9 | PDPL retention + right-to-deletion | `DATA_RETENTION_DAYS`, `purge_expired_data` cmd, `/account/delete/` view | [settings.py:198](cybertrust_ksa/settings.py#L198), [core/views.py:199](core/views.py#L199), [purge_expired_data.py](core/management/commands/purge_expired_data.py) | `PdplTests` (purge runs); delete-view itself untested | **PASS** | Add a test for the deletion view (low priority). |
| 10 | Security: CSP / throttling / audit | CSP + audit middleware; DRF throttle 100/min; `SECURE_*` gated on `DEBUG` | [core/middleware.py](core/middleware.py), [settings.py:125,177,187](cybertrust_ksa/settings.py#L125) | `AuditLogTests` (POST logged) | **PASS** | `SECURE_*` only active when `DEBUG=False` (correct, but unverified in test). See gaps for tenant-isolation. |

### Cross-cutting bug found during verification (not in any claim)
**Evidence upload was broken at runtime**: `STORAGES` defined only `staticfiles`, not `default`,
so every `FileField.save()` raised `InvalidStorageError`. The original 17 tests never saved a
real file, so this was invisible. Discovered while testing patch #2. Fixed in
[settings.py:104](cybertrust_ksa/settings.py#L104) and covered by
`EvidenceValidationTests.test_accepts_valid_file_and_creates_row`.

## Summary
- **8 PASS, 2 PARTIAL** after repairs. No claim was outright fabricated, but **two claims were
  overstated**: the realtime page and evidence upload both crashed at runtime until fixed here.
- Test count: **17 → 28** (all green). New tests target the 6 PATCH_NOTES fixes plus the two
  runtime bugs above.

## Source documents reviewed
Text was extracted (not skipped) from the binary sources:
- **SRS v1.0** (`Docs/SRS/CyberTrust_KSA_SRS.pdf`) — FR-001…FR-012 + NFRs. Confirmed: standalone
  registration (FR-002.9, no external API), CR = 10 digits (FR-002.10/.11), 50 MB evidence
  (FR-005.2), 5 supported formats (FR-005.1), per-framework gap analysis (FR-007), 334 controls.
- **Aramco/SACS-002 third-party report template** (`Docs/SRS/third-party-cybersecurity-compliance-report-template.docx`)
  — structure confirmed: Third Party Information, Vendor ID, classification (General + Outsourced
  Infrastructure / Customized Software / Network Connectivity / Critical Data Processor / Cloud),
  Audit Firm Information, Assessors, TPC-N references, **Compliance / Noncompliance** status, Report Summary.
- **Consolidated control spreadsheets** (`compliance/data/*.xlsx`) — `Consolidated_Rules`,
  `NCA_ECC_114`, `Aramco_SACS002`, `SABIC_CyberTrust` sheets; Evidence Matrix = 334 controls.
- **NCA report template / Developer Prototype v3.2** (`Docs/SRS/CyberTrust_KSA_Developer_Prototype_v3.2.pdf`)
  — the v3.2 PDF is image-only (no embedded text layer); content cross-referenced via the SRS and
  the RTM spreadsheet (`Docs/CyberTrust_KSA_RTM_v3.xlsx`). A dedicated NCA report *template* file
  is not shipped; NCA reporting uses the C/PC/NC/N-A model described in the SRS and prompts.
