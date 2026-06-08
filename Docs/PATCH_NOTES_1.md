# CyberTrust KSA — Critical Bug Fixes (Patch Notes)

Drop these files back into `cybertrust_django/`, preserving their paths. After deploying, run:
`python manage.py check` (passes clean) and re-test registration + /monitoring/realtime/.

## 1. File upload size conflict  (FR-005.2 / NFR-006)
**File:** `cybertrust_ksa/settings.py`
- Removed the 10 MB `DATA_UPLOAD_MAX_MEMORY_SIZE` that silently blocked the promised 50 MB.
- Added `MAX_EVIDENCE_FILE_SIZE = 50 MB`, sane spool threshold, and an `ALLOWED_EVIDENCE_EXTENSIONS` whitelist.

## 2. Evidence validation  (FR-005.11)
**File:** `compliance/views.py`
- `upload_evidence` now rejects unsupported file types and oversized files with a clear message *before* creating the Evidence row.

## 3. Gap-analysis save bug  (FR-007.1)
**File:** `ai_engine/views.py`
- `run_gap_analysis` previously persisted a `GapAnalysis` row for **NCA only**. It now saves one row **per targeted framework** (NCA / Aramco / SABIC) with real per-framework counts and score.

## 4. Missing real-time template  (Prototype Phase 10B)
**File:** `templates/monitoring/realtime.html` (NEW)
- The `realtime_monitoring` view referenced a template that did not exist → `TemplateDoesNotExist` crash. Added a styled live-event-feed page consistent with the gov-green theme.

## 5. Registration validation bypass  (FR-002.10 / .11 / FR-012.4)
**Files:** `core/forms.py`, `core/views.py`
- Registration now uses `CompanyRegistrationForm` instead of raw `request.POST`.
- CR number validated as exactly 10 digits; duplicate CR and duplicate email handled gracefully (no more uncaught HTTP 500).
- Password minimum raised to 12 characters; at least one certification target required.
- Wrapped Company+User creation in a transaction.

## Bonus — control checklist creation  (UC-001 step 9 / FR-003)
**File:** `core/views.py`
- After classification, the company's control checklist is now actually built from its targeted frameworks (`_create_company_control_checklist`). Without this the dashboards and controls list were empty. Landing-page control count is now read from the DB instead of the hardcoded 334.
