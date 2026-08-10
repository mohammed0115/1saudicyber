# Phase UX-1C — Language Switcher + English Catalogs

> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. The internal Django
> project package name remains `cybertrust_ksa` (technical-only, intentionally unchanged).

**Status:** Local-only. Not deployed to production.

## What was changed
Completed the local bilingual i18n foundation: a clean Arabic↔English language switcher backed by
Django i18n catalogs, plus conversion of the remaining legacy English Python user-messages to
Arabic `gettext` msgids. English is delivered **through catalogs and the switcher**, never by adding
English text in parentheses beside Arabic.

## Arabic default decision
- `LANGUAGE_CODE = 'ar'` — Arabic is the default language; default render is `lang="ar" dir="rtl"`.
- English is opt-in via the switcher (session/cookie), rendering `lang="en" dir="ltr"`.
- `User.preferred_language` is **not** written in this phase — session/cookie selection only.

## i18n foundation (already present, confirmed)
- `USE_I18N = True`, `LANGUAGE_CODE = 'ar'`, `LANGUAGES = [('ar','العربية'), ('en','English')]`.
- Middleware order correct: `SessionMiddleware` → `LocaleMiddleware` → `CommonMiddleware`.
- `django.template.context_processors.i18n` present (provides `LANGUAGE_CODE` / `LANGUAGE_BIDI`).
- `LOCALE_PATHS = [BASE_DIR / 'locale']`.
- **Added:** `path('i18n/', include('django.conf.urls.i18n'))` → exposes `set_language`.

## Language switcher behavior
- POST form to `{% url 'set_language' %}` with `{% csrf_token %}` and a hidden `next` = `request.path`.
- Two `language` submit buttons (`ar` / `en`); the active language is marked (bold + underline).
- **Desktop:** in the authenticated top nav account area (`hidden sm:flex`).
- **Mobile:** inside the `<details>` hamburger menu.
- **Anonymous:** a compact switcher on the login page (the main anonymous entry).
- No new JavaScript; pure form POST. RTL/LTR follows `LANGUAGE_BIDI`.

## English catalog coverage
- `locale/en/LC_MESSAGES/django.po` + compiled `django.mo` (gettext tools present: `msgfmt`/`xgettext`).
- 37 Arabic msgids → English msgstr, covering: shell nav (لوحة التحكم→Dashboard, مسار الامتثال→Compliance
  Journey, الأطر→Frameworks, الأدلة→Evidence, التقارير→Reports, المراقبة→Monitoring, المزيد→More,
  المراجعة→Review, الضوابط→Controls, خطة الضوابط→Control plan, التصنيف→Intake, تسجيل الدخول/الخروج),
  login page strings, journey-wizard hero + step status badges, and the converted system messages.
- `locale/ar/LC_MESSAGES/django.po` generated as identity (empty msgstr → Django returns the Arabic msgid).

### Examples
```po
msgid "لوحة التحكم"
msgstr "Dashboard"

msgid "بيانات الدخول غير صحيحة. حاول مرة أخرى."
msgstr "Invalid credentials. Please try again."

msgid "تم رفع الدليل. التحليل الاستشاري قيد التنفيذ ولا يُعد قرارًا نهائيًا."
msgstr "Evidence uploaded. Advisory analysis is running and is not a final decision."
```

## Python messages converted (Arabic msgid via `gettext as _`)
| Location | Old (English literal) | New Arabic msgid |
|---|---|---|
| `core/views.py` register | Company registered successfully! AI classification in progress. | تم تسجيل الشركة بنجاح. جارٍ تجهيز التصنيف الأولي. |
| `core/views.py` login | Invalid credentials. Please try again. | بيانات الدخول غير صحيحة. حاول مرة أخرى. |
| `core/views.py` mfa_setup | Multi-factor authentication enabled. | تم تفعيل التحقق بخطوتين. |
| `compliance/views.py` | No company associated with your account. | لا توجد شركة مرتبطة بحسابك. |
| `compliance/views.py` | Please select a file to upload. | يرجى اختيار ملف للرفع. |
| `compliance/views.py` | Evidence uploaded. AI analysis is running in the background. | تم رفع الدليل. التحليل الاستشاري قيد التنفيذ ولا يُعد قرارًا نهائيًا. |

> AI/analysis wording kept **advisory** — never implies a final automated compliance decision.

## Tests run
- `core.tests.BilingualSwitcherTests` (10) + `core.tests.ArabicResidueCleanupTests` (6) — all pass.
- `python manage.py check` → clean; `makemigrations --check --dry-run` → No changes.
- Full suite green (see report).

## Missing tooling notes
None — GNU gettext (`msgfmt`, `xgettext`) is installed, so `.po` and `.mo` both built.

## Remaining translation gaps (low priority, future phases)
- Several deeper templates/pages (full landing, register-company form copy, auditor pages, monitoring
  dashboards, MFA/email-verify/delete-company system messages) are not yet fully wrapped in `{% trans %}`;
  untranslated strings fall back to Arabic in English mode (acceptable, Arabic-default).
- A real bilingual catalog for those pages can be extended incrementally via `makemessages` + `compilemessages`.

## Out of scope confirmed
No OCR, AI Evidence Analyzer, Rule Engine, Smart Classification backend, Applicability Engine, payment,
external connectors, alerting, reports/subscription/auditor/risk/control decision logic, CompanyControl
generation, OTCC/DCC import, upload workflow, frontend stack, models, migrations, production deployment,
or secrets were changed.
