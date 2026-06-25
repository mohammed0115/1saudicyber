# Phase UX-WIZARD-A — Compliance Journey Stepper/Wizard

**Public brand:** 1SaudiCyber — 1saudicyber.com · **Internal package:** `cybertrust_ksa` (unchanged).

## Purpose
Show the full **target** compliance journey as a guided, bilingual-ready, mobile-friendly wizard so
the user always knows: where am I now, what's complete, what needs action, what's next, what's not
available yet, and whether a step is a final decision or an advisory result. **UI/UX + language only**
— no OCR, AI analyzer, rule engine, or new business logic.

## 5-stage / 16-substep structure
| Stage | Substeps |
|---|---|
| **1. البدء والتصنيف** | تسجيل الشركة · بيانات الشركة · التصنيف الذكي |
| **2. الأطر والضوابط** | مكتبة الضوابط · قابلية التطبيق · إنشاء التقييم |
| **3. الأدلة والتحليل** | رفع الأدلة · استخراج النص / OCR · التحليل الاستشاري للذكاء الاصطناعي · محرك القواعد |
| **4. الفجوات والمعالجة** | تحليل الفجوات والمخاطر · خطة المعالجة |
| **5. المراجعة والتقارير والمراقبة** | مراجعة المدقق · النتيجة النهائية بعد المراجعة · التقارير · المراقبة المستمرة |

## Status rules (deterministic, read-only, from existing data)
Allowed statuses: `completed`, `current`, `needs_action`, `locked`, `planned`, `not_available`, `optional`
(Arabic: مكتمل / الخطوة الحالية / يحتاج إجراء / مقفل / قيد التجهيز / غير متاح حاليًا / اختياري).

- **completed** when the matching data exists: company (registration), intake/onboarding (profile),
  `FrameworkApplicabilityResult` (classification), control library (platform, always), applicable
  `ControlApplicabilityResult` (applicability), `ControlAssessment` (assessment creation),
  `EvidenceSubmission` (evidence upload), `EvidenceAnalysisResult` (AI advisory), `RiskItem` (gap/risk),
  `RemediationTask` (remediation), reviewed assessment / accepted assignment (auditor review),
  all-reviewed (final verdict), active subscription + reviewed (reports), `MonitoringCheck` (monitoring).
- **current** = the **first** required, available, incomplete step (exactly one) → answers "أين أنا الآن؟".
- **needs_action** = later required incomplete steps. **optional** = advisory/optional incomplete
  (AI advisory, gap/risk, remediation, monitoring). **locked** = reports without active subscription.
- **planned** (truthful) for unimplemented target features: **OCR**, **Rule Engine**, and **Final
  Verdict** (no distinct sign-off object yet) → shown as «قيد التجهيز», not available.

Stage status rolls up from its substeps (current → completed → needs_action → locked → planned), with a
per-stage `progress_percent` and an overall progress %.

## What is active vs planned
- **Active:** registration, profile/intake, classification (rule-based applicability), control library
  (417 official controls), control plan, assessments, evidence upload, **advisory** AI analysis (Phase
  3F), risk register + remediation (5A), auditor review, reports (subscription-gated), continuous
  monitoring **foundation** (5B).
- **Planned (قيد التجهيز, غير مفعّل بعد):** OCR / text extraction, rule engine, a distinct auditor final
  verdict sign-off.

## Mobile behavior
- Hero card (progress + next action) → a responsive 5-stage segmented progress (`grid-cols-2
  sm:3 md:5`, no horizontal overflow) → stages as **`<details>` accordions** (the current stage open by
  default), each expanding to compact substep cards (`grid-cols-1 md:2 lg:3`). No 16-step cramped row.

## Language rules
- Arabic-first copy; **bilingual-ready** via `{% load i18n %}{% trans "…" %}` with the Arabic text as
  the default msgid (so output is unchanged until an English catalog is compiled). **No English in
  parentheses** beside Arabic. No "official certification" claim; AI clearly labelled advisory.
- Consistent terminology (Dashboard→لوحة التحكم, Journey→مسار الامتثال, Intake→التصنيف, Controls→الضوابط,
  Review→المراجعة, Reports→التقارير, Monitoring→المراقبة, Auditor Final Verdict→النتيجة النهائية بعد
  المراجعة, AI Evidence Analyzer→التحليل الاستشاري للذكاء الاصطناعي, Rule Engine→محرك القواعد).

## Files
- `compliance/journey.py` — `build_company_compliance_journey(company, user)`.
- `templates/components/{journey_wizard,journey_step_card,status_badge}.html`.
- `templates/compliance/journey_dashboard.html` — wizard added as the hero; the prior 14-step stepper
  kept inside a collapsible «عرض المسار التفصيلي»; the title's English parenthetical removed.
- `compliance/views.py` — `journey` added to the dashboard context.

## Permissions / safety
Read-only and tenant-scoped (`request.user.company`); the builder never writes (no ControlAssessment /
subscription / risk mutation). Anonymous → login. Auditor read-only flows (risk/monitoring) unchanged.

## Tests run
`compliance` subset + builder/view wizard tests (15 new) green; `manage.py check` clean;
`makemigrations --check --dry-run` → no changes (no model change). Full suite re-run.

## Out of scope
No OCR, AI analyzer/rule-engine/smart-classification backend, payment, external integrations, alerts,
new compliance decisions, ControlAssessment/Risk/Report/Subscription/Auditor rewrites, frontend stack
replacement, destructive migration, production deployment, or secret changes.
