# Scenario C — Auditor Assignment (+ Scenario D — External Auditor) (UAT)

> **UAT only — do not use in production.** No payments, marketplace pricing, payouts, chat, or
> external share links are implemented.

## Scenario C — Platform auditor assignment
| # | Step | Expected |
|---|------|----------|
| 1 | Register an auditor at `/auditors/register/` | User + `AuditorProfile` created |
| 2 | Check status | `AuditorProfile.status = pending_review` |
| 3 | Pending auditor opens `/auditors/dashboard/` | Pending message; **no** company data |
| 4 | Activate auditor (admin) | Django admin → Auditor profiles → status **active** (seed sets active) |
| 5 | Subscribed company opens `/auditors/` | Active+available auditors listed; "طلب مراجعة من مدقق المنصّة" |
| 6 | Company assigns to the auditor | Assignment created with status `requested` (loading: "جارٍ إسناد الملف إلى المدقق...") |
| 7 | Re-assign same auditor | Duplicate active assignment prevented (one active row) |
| 8 | Auditor opens `/auditors/dashboard/` | Sees only its own assignments |
| 9 | Auditor opens the assignment, clicks accept | Status → `accepted` (loading: "جارٍ تحديث حالة الطلب...") |
| 10 | Auditor views accepted assignment | **Read-only** company context: name, approved frameworks, subscription label, assessment summary, evidence-matrix summary |
| 11 | Auditor tries another company's assignment URL | Redirected — cannot view unassigned company data |
| 12 | Auditor attempts a company export endpoint | No file served (auditor has no company scope) |
| 13 | Confirm assessment immutability | Auditor cannot change `ControlAssessment` (staff-only) |

## Scenario D — External auditor option
| # | Step | Expected |
|---|------|----------|
| 1 | Subscribed company exports CSV/XLSX | Report files download |
| 2 | Company shares files outside the platform | Done manually by the company (email, etc.) |
| 3 | Confirm scope | **External auditor public share links are NOT implemented** — sharing is manual/off-platform |

**Pass criteria:** assignment requires an active subscription; pending/suspended/inactive auditors get
no company data; assigned+active auditors get read-only context only; no cross-company leakage; the
assignment flow creates no `CompanyControl` and changes no `ControlAssessment`.
