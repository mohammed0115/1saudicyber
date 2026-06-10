# PATCH_IMPLEMENTATION_REPORT

Date: 2026-06-09. Scope: the 6 critical bugs from `Docs/PATCH_NOTES.md`, plus 2 runtime bugs
found while adding the required regression tests. Every fix is covered by a test.

## Key finding
The 6 PATCH_NOTES fixes were **already applied to the source** (the patch had been merged), but
**none of them had regression tests** — the per-app `tests.py` files were empty stubs. So this
pass:
1. Verified each of the 6 fixes is present and correct.
2. Added regression tests for all 6 (17 → 28 tests).
3. Fixed 2 genuine runtime defects the new tests exposed.

## The 6 PATCH_NOTES bugs

| # | Bug | State on entry | Action | Test added |
|---|-----|----------------|--------|------------|
| 1 | 50 MB upload conflict | Fixed: `MAX_EVIDENCE_FILE_SIZE=50MB`, `DATA_UPLOAD_MAX_MEMORY_SIZE` raised above it ([settings.py:206](cybertrust_ksa/settings.py#L206)) | Verified; locked with assertions | `compliance.UploadSizeConfigTests` (×3) |
| 2 | Evidence validation | Fixed: extension + size checked before row creation ([compliance/views.py:97](compliance/views.py#L97)) | Verified | `compliance.EvidenceValidationTests` (reject .exe, reject oversize, accept valid) |
| 3 | Per-framework gap-analysis save | Fixed: one `GapAnalysis` row per targeted framework with real counts ([ai_engine/views.py:81](ai_engine/views.py#L81)) | Verified | `ai_engine.PerFrameworkGapAnalysisTests` (2 targets → 2 rows, per-fw counts) |
| 4 | Missing `realtime.html` | Template present, **but view still 500'd** | **Fixed the view** (see below) | `monitoring.RealtimeTemplateTests` |
| 5 | Registration validation bypass | Fixed: view uses `CompanyRegistrationForm` ([core/views.py:51](core/views.py#L51)) | Verified | `core.RegisterViewTests` (bad CR, dup CR rejected) |
| 6 | Post-classification checklist | Fixed: `_create_company_control_checklist` runs after register ([core/views.py:105](core/views.py#L105)) | Verified | `core.RegisterViewTests.test_successful_registration_builds_checklist` |

## 2 runtime bugs found by the new tests

### A. `realtime_monitoring` crashed — `TypeError: Cannot filter a query once a slice has been taken`
The view sliced `Alert...[:50]` then called `.filter(severity=...)` on the slice. Patch #4 added
the *template* but the *view* still raised a 500 on every load.
**Fix** ([monitoring/views.py:47](monitoring/views.py#L47)): compute severity counts from the
unsliced queryset, slice only for display.

### B. Evidence upload broken — `InvalidStorageError: Could not find config for 'default'`
`STORAGES` defined only `staticfiles`. When `STORAGES` is set, Django does **not** backfill the
`default` key, so every `FileField.save()` (i.e. all evidence upload, FR-005) raised. Invisible
before because no test saved a real file.
**Fix** ([settings.py:104](cybertrust_ksa/settings.py#L104)): add explicit
`default: FileSystemStorage`.

## Other real defects fixed (non-PATCH_NOTES)
- **`openpyxl` missing from `requirements.txt`** — used at runtime by XLSX evidence extraction
  ([ai_engine/services.py:87](ai_engine/services.py#L87)) and `seed_all_controls`. A clean
  `pip install -r requirements.txt` would break both. Added `openpyxl==3.1.5`.
- **Stale `.env.example`** — `MAX_UPLOAD_SIZE=10485760` (10 MB) contradicted the 50 MB limit.
  Updated to 52428800 with a clarifying comment.
- **Added `.gitignore`** — repo had none; `.venv/`, `.env` (secrets), `__pycache__/`, `media/`
  were all untracked-but-committable.

## Constraints honored
- No feature rebuilt from scratch; no working functionality removed.
- No model changes → **no new migrations** (`makemigrations --check` clean).
- Rules First → AI Second → Auditor Final preserved (no AI-writes-final-status change).
- No dashboard/AI/monitoring feature work beyond repairing the crashing realtime view.
