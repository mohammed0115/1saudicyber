# Phase 8C — Public UX Trust Polish

> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. Internal package
> `cybertrust_ksa` (technical-only).

**Status:** Local-code only. No production deployment, no SSH, no migration, no secret change.

## Summary
Polished the public-facing experience for trust and Arabic consistency before showing the platform to
real customers: Arabic registration labels/help text, a required terms/privacy acceptance, password and
CR guidance, safer auditor wording (no implied accreditation), safer marketing claims, a dynamic footer
year, and a smoke-checklist route note. All changes are template/forms/docs copy + tests — **no model,
no migration, no engine/logic changes**.

## Files Changed
- `core/forms.py` — added `SECTOR_CHOICES_AR` / `SIZE_CHOICES_AR` (Arabic labels, **same values**);
  `SelfServiceRegistrationForm` now uses them + password `help_text` (reflects the **real** 12-char
  minimum, not weakened) + CR `help_text` + required `accept_terms` (form-only, not stored);
  `CompanyRegistrationForm` choices relabeled to Arabic.
- `core/views.py` — `register_company` passes the Arabic choice lists to the template context.
- `templates/onboarding/_field.html` — renders `help_text` when present.
- `templates/onboarding/register.html` — terms/privacy checkbox + error in step 3.
- `templates/onboarding/auditor.html`, `templates/auditors/list.html`,
  `templates/compliance/reports_index.html` — "مدقّق معتمد" → "مدقّق أو مراجع امتثال داخل المنصّة".
- `templates/core/landing.html` — removed the "24/7 مراقبة مستمرة" absolute claim → "جاهزية للمراقبة
  المستمرة (أساس تقني عند ربط مصادر البيانات المناسبة)"; added "مؤشرات توضيحية…" disclaimer under the
  metrics; demo readiness card badge "مباشر" → "مثال توضيحي"; footer year dynamic.
- `templates/base.html` — footer `© {% now "Y" %}` (was hardcoded 2024).
- `docs/PHASE_8A_PRODUCTION_SMOKE_CHECKLIST.md` — note that `/compliance/dashboard/` is the journey
  dashboard route (there is no `/compliance/journey/` URL).
- `core/tests.py` (+`Phase8CPublicUXTrustTests`, 8 tests) and registration POST payloads across
  `core/auditors/billing/risk` tests updated to include `accept_terms`.

## UX Fixes Completed
- **Login Arabic consistency:** already fully `{% trans %}`-localized (UX-1C); confirmed default Arabic
  copy ("مرحبًا بعودتك", "تسجيل الدخول") with no English fallback in Arabic mode.
- **Registration Arabic labels:** sector/size now show Arabic ("الرعاية الصحية", "متناهية الصغر", …) —
  stored enum values unchanged (form-level relabel, no migration).
- **Terms/privacy acceptance:** required checkbox; submit blocked without it; error
  "يجب الموافقة على شروط الاستخدام وسياسة الخصوصية قبل إنشاء الحساب." (form-only — **no DB field/migration**).
- **Password guidance:** "استخدم كلمة مرور قوية لا تقل عن 12 حرفًا…" (reflects the real `min_length=12`).
- **Commercial registration hint:** "رقم السجل التجاري في السعودية يتكوّن غالبًا من 10 أرقام." (existing
  10-digit validation kept).
- **Auditor wording safety:** replaced "مدقّق معتمد" with "مدقّق أو مراجع امتثال داخل المنصّة" + "يخضع
  لمراجعة وتفعيل إدارة المنصّة" — no implied official accreditation.
- **Marketing metrics safety:** "24/7" absolute claim removed → readiness wording; illustrative disclaimer
  added; demo card marked "مثال توضيحي". 75%/60%/87%… remain but are framed as illustrative.
- **Footer dynamic year:** `{% now "Y" %}` in base + landing (no hardcoded 2024).
- **Smoke checklist route:** documented `/compliance/dashboard/` as the journey route (the 8A checklist
  already used it; added a clarifying note; no `/compliance/journey/` URL exists / none added).

## Legal / Trust Safety
No official certification/accreditation claim was added. Verified absent from public pages
(landing/login/get-started/auditor): "شهادة امتثال رسمية", "اعتماد رسمي", "معتمد من NCA/أرامكو/سابك",
"certified by NCA", "official accreditation", "اعتماد حكومي". The only "شهادة/رسمية" usages remain inside
negation disclaimers (verdict/report pages). `417` is the official total; `334` is not shown as current.

## Migrations
**No migrations created.** Sector/size relabeling is at the form/view layer; terms acceptance is
form-only (not stored). `makemigrations --check --dry-run` → No changes detected.

## Tests
`Phase8CPublicUXTrustTests` (8): login Arabic copy; registration Arabic labels + help text; terms
required (blocks submit) / succeeds with terms; auditor public wording safe; public pages no certification
claims; footer dynamic year; landing marketing safety (no 24/7, disclaimer present, 417 shown).
Registration payloads across core/auditors/billing/risk updated for the new required `accept_terms`.

## Production Safety
No production deployment, no SSH, no production migration, no secret change, no database change.

## Remaining Notes
- Terms/Privacy **content pages** are not created here (no dedicated routes existed); the checkbox text is
  shown but not yet linked to standalone Terms/Privacy pages — add them in a later content phase.
- Visual/manual browser QA (mobile layout, language switch, first dashboard after login) is recommended —
  Phase 8D.

## Final Status
**GO WITH NOTES** — public UX/trust polish complete and fully test-covered; only follow-ups are standalone
Terms/Privacy content pages and browser QA.
