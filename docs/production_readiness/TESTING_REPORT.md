# CyberTrust KSA — Testing Report

**Status:** Complete · **Final result:** 450 tests, all passing.

## Runner
- **Django test runner** (`manage.py test`). pytest is **not** used in this project.
- In-memory SQLite test database; no external services required.

## Headline results
| Command | Result |
|---|---|
| `python manage.py check` | System check identified no issues (0 silenced). |
| `python manage.py makemigrations --check --dry-run` | No changes detected (no pending migrations). |
| `python manage.py test` | Ran 450 tests — **OK**. |

## Command examples
```bash
# from the project root, using the project virtualenv
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
# focused runs
python manage.py test compliance.tests.SecurityTenantIsolationTests
```

## Major test areas covered
| Area | Coverage |
|---|---|
| Official controls | Dataset load, validation, official-vs-legacy separation, counts. |
| Intake / applicability | Intake profile, deterministic `FrameworkApplicabilityResult`. |
| Framework scope / control plan | Propose/approve/reject scope; official-only `ControlApplicabilityResult`. |
| Evidence checklist | `EvidenceRequirement` templates → `EvidenceChecklistItem` planning. |
| Evidence Upload v2 | `EvidenceSubmission`, checksum, type/size validation, versioning. |
| Advisory analysis | `EvidenceAnalysisResult`; advisory containment (no compliance decision). |
| ControlAssessment | Auditor-driven status/decision, remediation fields. |
| Reports | Executive summary, gap analysis, evidence matrix, CSV/XLSX exports. |
| Dashboard journey | Read-only stage status, next-step ladder, empty states. |
| Security / tenant isolation | Auth coverage, IDOR, staff-only gates, upload safety, export scoping (Phase 3J, 41 tests). |

## History
- Phase 3I: +31 tests → 409.
- Phase 3J: +41 tests → 450.
- Phase 3K: documentation only; no test changes; suite remains 450 OK.
