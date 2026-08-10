# Scenario A — Company Self-Service Journey (UAT)

> **UAT only — do not use in production.**

**Goal:** A self-registered company completes the full workflow up to reports and auditor assignment.

| # | Step | Expected result |
|---|------|-----------------|
| 1 | Open the landing page `/` | Arabic-first, RTL; brand **1SaudiCyber**; "ابدأ تقييم الامتثال" CTA |
| 2 | Click "ابدأ الآن" → `/get-started/` | Two cards: company / auditor |
| 3 | "إنشاء حساب شركة" → register Najd Digital Solutions | 3-step stepper; calm loading on submit |
| 4 | Submit registration | User + company created; redirected to `/onboarding/` |
| 5 | Onboarding `/onboarding/` | Welcome + journey stepper; "الانتقال إلى لوحة الرحلة" |
| 6 | Open Journey Dashboard `/compliance/dashboard/` | **Workflow Stepper** shows 13 grouped stages + next action |
| 7 | Complete intake `/compliance/intake/` | Profile saved (loading: "جارٍ حفظ البيانات...") |
| 8 | Framework review `/compliance/applicability_review/` | Deterministic applicability with reasons |
| 9 | Approve frameworks (staff) | Approve form shows loading; scope becomes "معتمد" |
| 10 | Generate control plan (staff) `/compliance/control-plan/` | Official applicable controls listed (legacy 334 excluded) |
| 11 | Generate evidence checklist (staff) | Checklist items planned |
| 12 | Upload evidence (Upload v2) | Submission recorded with SHA-256; loading: "جارٍ رفع الدليل..." |
| 13 | Trigger advisory analysis (staff) | Loading: "جارٍ تحليل الدليل استشاريًا..."; result clearly **advisory** |
| 14 | Confirm advisory note | "التحليل يساعد المدقق ولا يُعد قرارًا نهائيًا" present |
| 15 | Auditor review queue `/compliance/auditor-review/` | Assessments generated as `not_reviewed`; staff can decide |
| 16 | Activate subscription | `activate_company_subscription --company-id <id> ...` or seed `--subscribe` |
| 17 | Reports `/compliance/reports/` | "التقارير مفعّلة" + two options (external download / platform auditor) |
| 18 | Export CSV/XLSX | Files download; loading: "جارٍ تجهيز ملف CSV/Excel..." |
| 19 | Assign to platform auditor `/auditors/` | Available auditors listed; assign sends a request |

**Pass criteria:** every step renders without error, loading states appear where listed, advisory
analysis never sets a compliance decision, and reports/exports/assignment require the active subscription.
