# TEST_RESULTS

Date: 2026-06-09 · `python manage.py test` (Django test runner) · SQLite in-memory.
Environment: `.venv` built from `requirements.txt` (+ `openpyxl`, now in requirements).

## Result
```
Ran 28 tests in ~11s
OK
```
**28 passed, 0 failed, 0 errors.** Baseline before this pass was 17. (`pytest` is not configured;
the project uses Django `TestCase`, so the suite is run via `manage.py test`.)

## New tests added this pass (11)
| App | Class.test | Covers |
|-----|-----------|--------|
| compliance | `UploadSizeConfigTests.test_evidence_limit_is_50mb` | PATCH #1 |
| compliance | `UploadSizeConfigTests.test_request_body_cap_exceeds_evidence_limit` | PATCH #1 (no 10 MB reintroduction) |
| compliance | `UploadSizeConfigTests.test_supported_extensions_cover_srs_formats` | FR-005.1 |
| compliance | `EvidenceValidationTests.test_rejects_unsupported_extension` | PATCH #2 |
| compliance | `EvidenceValidationTests.test_rejects_oversized_file` | PATCH #2 |
| compliance | `EvidenceValidationTests.test_accepts_valid_file_and_creates_row` | PATCH #2 + STORAGES fix (B) |
| ai_engine | `PerFrameworkGapAnalysisTests.test_one_row_per_targeted_framework` | PATCH #3 |
| monitoring | `RealtimeTemplateTests.test_realtime_page_renders` | PATCH #4 + realtime view fix (A) |
| core | `RegisterViewTests.test_invalid_cr_does_not_create_company` | PATCH #5 |
| core | `RegisterViewTests.test_duplicate_cr_rejected` | PATCH #5 |
| core | `RegisterViewTests.test_successful_registration_builds_checklist` | PATCH #6 |

## Pre-existing tests (17, still green)
RegistrationFormTests (×4), EmailVerificationTests, MFATests, ExtractionTests (×3),
MonitoringTests (×2), ReportingTests (×2), ApiTests (×2), AuditLogTests, PdplTests.

## Notes / caveats
- `staticfiles.W004` warning appears during the run (no `static/` dir at the time the baseline
  was taken). A `static/.gitkeep` was added; the warning is cosmetic and does not affect results.
- Tests that touch OpenAI/Celery are isolated by mocking (`generate_gap_analysis`,
  `classify_company`, `analyze_evidence_async.delay`) — no network or broker is contacted.
- Celery task wrappers and the SSE stream generator are **not** covered by automated tests
  (see REMAINING_GAPS.md).
