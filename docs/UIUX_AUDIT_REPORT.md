# 1SaudiCyber — UNDERSTAND → AUDIT → MAP (تقرير الفحص قبل إعادة التصميم)

> PHASE 22 deliverable. تقرير فقط — **لم يُعدَّل أي template/CSS/JS/backend**. كل استنتاج مدعوم بـ`file:line`؛ وحيث لا دليل → **NOT VERIFIED**. المصدر: فحص فعلي للكود عبر 5 مسارات + مجلد «سيناريو» (النموذج الأوّلي + الشعار + صور الرحلة 1–9).

---

## A. Architecture Understanding

Django server-rendered (ليست SPA). Apps ذات `models.py`: `core, compliance, auditors, auditor_portal, billing, risk, monitoring, ai_engine, dashboard`. `api/` و`cybertrust_ksa/` بلا نماذج.

- **التوجيه الجذري** `cybertrust_ksa/urls.py`: `''`→core(50)، `compliance/`→compliance(52)، `compliance/risks/`→risk(51)، `dashboard/`→dashboard(55)، `ai/`→ai_engine(56)، `auditor/`→auditor_portal(57)، `auditors/`→auditors(58)، `monitoring/`→monitoring(60)، `billing/`→billing(61)، `/admin/`→Django admin(48)، `/platform-admin/`→auditors/admin_urls(59)، `i18n/`(47).
- **الترتيب المفاهيمي المعتمد** (`compliance/workflow_stepper.py:66-84 _STAGE_DEFS`): registration → onboarding → intake → applicability → approval → control_plan → checklist → upload → analysis → auditor_selection → auditor_review → risk_register → subscription → reports → download/assign. (الـstepper يقفل بصريًا `reports/download_assign` خلف الاشتراك فقط، بينما حُرّاس العروض الفعلية أشد — تعارض، انظر J/P.)
- **i18n/RTL**: `USE_I18N`, `LANGUAGE_CODE='ar'`, `LANGUAGES=[ar,en]` (`settings.py:129-137`), `LocaleMiddleware:61`, `set_language` عبر `i18n/` (`urls.py:47`). الاتجاه يُشتق من `LANGUAGE_BIDI`.
- **AI**: OpenAI (`ai_engine/services.py:9`, `gpt-4o`)، OCR محلي (Tesseract/pdf2image بلا خروج). residency افتراضيًا **`disabled`** (`settings.py:228`).

---

## B. Actors (كيف يميّزهم الكود — لا حسب `role`)

المصنّف القانوني الوحيد: `core/roles.py:portal_for()` يرجع واحدًا من `platform_admin | auditor | company | company_unlinked | anonymous` (الترتيب مهم، fail-closed).

| Actor | التمييز الفعلي | Evidence |
|---|---|---|
| **Platform Admin** (Get Solution staff) | `is_staff` أو `is_superuser` — **ليس** `role` | `core/roles.py:17-20`; `auditors/admin_services.py:42-48` |
| **Auditor** | وجود `AuditorProfile` (أي حالة)، والوصول الفعّال يتطلب `status='active'` | `core/roles.py:31-33`; `auditors/services.py:8-12` |
| **Company user** | authenticated، ليس staff، ليس auditor، وله `Company` مرتبطة (`user.company`) | `core/roles.py:36-49` |

- **حقل `User.role`** (`admin/company_admin/compliance_officer/it_security/bu_manager/executive/auditor` — `core/models.py:29-37`) هو **تسمية مخزّنة**، والقرارات تعتمد `is_staff/is_superuser` + `AuditorProfile` + `AuditorAssignment`. `role='auditor'` وحده **لا يمنح** وصول مدقّق.
- **حدود المدقّق↔الشركة** (fail-closed، مصدر واحد): `auditors/services.py:86-110 is_auditor_eligible_for_company` — يتطلب `is_active` + ملف `active` + إسناد `accepted` حيّ.
- **قاعدة الاستقلالية:** `compliance/auditor_verdict.py:47` — `if user.company_id == submission.company_id: return False` (لا أحد من الشركة المُدقَّقة يوقّع حكمها).

---

## C. Company Journey — As Implemented (21 خطوة، كلها منفّذة)

الحُرّاس المتكرّران: `company_portal_required` (`core/roles.py:98-106`)، `email_verified_required` (`:149-157`, يحجب الرفع/الاعتماد للبريد غير المُوثَّق، staff يتجاوز).

1. **التسجيل** — مساران: (A) `core:company_register`=/get-started/company/ → `company_self_register` (`core/views.py:330-382`): Company+User(`company_admin`) في معاملة، `login`, OTP، **redirect `core:onboarding`**. (B) legacy `core:register`=/register/ → `register_company` (`:68-150`): تصنيف AI inline + checklist + رابط تحقّق، **redirect `dashboard:main`**.
2. **تأكيد البريد (OTP)** — `core:verify_email_otp` (`:256-285`, `@login_required`)، redirect dashboard/auditors؛ resend مُقيّد؛ **غير حاجب للدخول** (`:242-245`). legacy: رابط `verify_email/<token>` (`:225-238`, بلا login).
3. **onboarding** — `core:onboarding` (`:402-408`)؛ إكمال `onboarding_complete` (`:411-420`) → `company.onboarding_completed=True` → **redirect `compliance:dashboard`**.
4. **اختيار الاشتراك** — `billing:home` (`billing/views.py:21-43`)؛ trial 14 يوم (`subscription_services.py:47-64`)؛ `select_plan` (`:58-84`) → `create_pending_subscription` (pending_payment + Payment) → moyasar→checkout / manual→home.
5. **الدفع** — manual: **لا مسار تأكيد للشركة** (التأكيد فعل إداري)؛ moyasar: `checkout` (`:87-118`)، `moyasar_callback` (`:121-162`) **لا يُفعّل أبدًا**، webhook (`:165-189`).
6. **التفعيل** — manual عبر admin `confirm_manual_payment`→`activate_subscription` (30 يوم)؛ moyasar فقط بعد تحقّق خادمي `verification.process_moyasar_payment_result` (`:143-175`).
7. **التصنيف الذكي** — أساسي **حتمي بلا AI** `compliance:classification` → `smart_classification.classify_company` (`smart_classification.py:2,9`)؛ المُغذّي `intake_wizard` (`compliance/views.py:491-546`) → `evaluate_company(apply=True)` → **redirect applicability_review**. legacy AI: `ai_engine:classify`.
8. **اعتماد النطاق** — **الشركة تعتمد نطاقها**: `approve_company_scope` (`:718-765`, `@email_verified_required` POST) يعتمد proposed/needs_review ثم يولّد الخطة+القائمة → **redirect control_plan**. مراجعة `applicability_review` (`:549-610`, `can_approve=is_staff`). مسارات staff لكل-نطاق منفصلة (`:670-715`). **ازدواجية: اعتماد ذاتي للشركة مقابل اعتماد staff** (انظر P).
9. **اللوحة** — `dashboard:main` (`dashboard/views.py:14-35`) موجّه fail-closed (staff→CRM، auditor→portal، وإلا `compliance_officer_dashboard`)؛ لوحة الرحلة `compliance:dashboard` (`:202-244`).
10. **التقييمات** — `auditor_review_queue` (`:1064-1075`)، توليد/قرار **staff-only** (`:1092,1129`).
11. **الضوابط/الخطة** — `controls_list` (`:19-78`)، `control_detail` (`:81-110`)، `control_plan` (`:783-808`, `can_generate=is_staff`).
12. **رفع الأدلة** — v2 `evidence_upload_v2` (`:882-949`, `@email_verified_required` + plan-gate `evidence_upload`، magic-byte + sha256، `EvidenceSubmission(pending_review)`)؛ legacy `upload_evidence` (`:113-196`). غياب الاشتراك **لا يحجب** الرفع (soft).
13. **AI استشاري (للشركة)** — على أدلة الشركة نفسها: `run_evidence_ai_analysis` (`:328-350`) «النتيجة استشارية ولا تُعد قرارًا نهائيًا» (`:344`)؛ استخراج نص؛ تقييم قواعد.
14. **تحليل الفجوات** — حتمي غير محجوب `gap_dashboard` (`:1240-1261`, «رؤية مبدئية دائمًا»)؛ إعادة الحساب plan-gated؛ تقرير الفجوات subscription-gated.
15. **المخاطر** — `/compliance/risks/` (`risk/views.py`): list/aggregate/detail/create/edit؛ `generate_risks` (`:75-92`, plan-gate `risk_engine`).
16. **المعالجة** — `RemediationTask` تحت مخاطرة؛ `task_set_status` (`:95-111`)؛ CAPA للـfindings منفصلة.
17. **مراجعة المدقّق (جانب الشركة)** — اختيار المدقّق **subscription-HARD-gated** `auditors_list` (`auditors/views.py:187-207`, `can_company_assign`)؛ `assign` (`:210-239`, + plan-gate `auditor_review`)؛ حالة المراجعة للقراءة `auditor_review_status` (`:1450-1493`, «تعرض ولا تُغيّر حكم المدقّق»).
18. **الرد على RFI** — `company_rfi_respond` (`auditor_portal/views.py:650-696`, tenant-scoped، يُقفل إن كان التقييم locked، يقلب RFI→responded).
19. **عرض الأحكام** — `auditor_verdict_view` (`:389-435`, الشركة تعرض ولا تُقدّم)؛ تقرير مُراجَع من المدقّق subscription-gated «تقرير داخلي — ليس شهادة».
20. **تقرير الجاهزية** — commercial_readiness plan-gated (`:1288-1303`)؛ تقارير subscription-HARD-gated عبر `_require_full_reports` (`:1144-1150`): executive/gap/matrix/framework؛ CSV/XLSX عبر `_require_report_export`.
21. **المراقبة المستمرة** — `monitoring:overview` (`:122-139`)، checks/findings، hub/realtime، SSE `event_stream` (`:81-116`).

---

## D. Auditor Journey — As Implemented

`auditors` (onboarding/approval/assignment/CRM) + `auditor_portal` (المراجعة/الأحكام/RFI/التقرير).

1. **تسجيل** `auditors:register` (`auditors/views.py:20-73`) → User(`auditor`) + AuditorProfile(`pending_review`) + إشعار staff + OTP.
2. **اعتماد الإدارة** `auditor_approval_action` (`admin_views.py:463-475`, `@platform_admin_required`) → `apply_auditor_action` (`admin_services.py:101-175`): approve→`active`, reject→`inactive` (**لا حالة `rejected` منفصلة**), suspend→`suspended`, reactivate→`active`.
3. **الإسناد** `AuditorAssignment` (`auditors/models.py:54-95`): من الشركة `assign` (`:210-239`) أو من الإدارة `crm_assign_auditor` (`:331-356`) → `create_assignment` status `requested` (واحد نشط لكل شركة)؛ رد المدقّق `respond_to_assignment` (`services.py:124-141`).
4. **البوابة** `auditor_dashboard` (`auditor_portal/views.py:119-132`) — `ensure_assessments_for_auditor` يُنشئ `Assessment(auditor_review)` لكل إسناد accepted؛ queryset مُقيّد `assigned_auditor=request.user`.
5–7. **مراجعة التقييم/الضابط/الأدلة** (`:181-256`) — الأدلة **للقراءة فقط** («المدقّق لا يحذف/يستبدل أدلة الشركة» `review_control.html:90`)؛ **AI استشاري عرض فقط** («لا يمثل قراراً نهائياً» `:56`).
8. **القرار المبدئي** — لا كائن منفصل؛ التقرير النهائي `pass` = «جاهز مبدئيًا (مراجعة داخلية)» (`review_assessment.html:237`).
9. **RFI** `DocumentRequest` — create/close/cancel/reopen (المدقّق)، respond (الشركة).
10. **الحكم النهائي للضابط** `save_verdict` (`:286-328`) → `AuditorControlVerdict` (overwrite) + `AuditorControlVerdictHistory` (append-only)؛ rationale/recommendation مطلوبة حسب الحكم.
11. **إتمام المراجعة + التقرير** `submit_report` (`:728-805`) — `validate_ready_for_completion` (`lifecycle.py:76-115`: لا RFI مفتوح، كل ضابط في النطاق له حكم نهائي...) → `AuditReport` **write-once immutable** + `transition_to('completed')` — **«تقرير جاهزية داخلي، ليس شهادة»** (`:732-738`).

**عزل الوصول الأفقي = VERIFIED (fail-closed):** `_assigned_assessment_or_404` + `_require_live_engagement` (404 لا 403) على كل عرض (`views.py:27-47`)؛ يعتمد `is_auditor_eligible_for_company`. **De-provisioning كامل:** `apply_auditor_action` يُلغي الإسنادات الحيّة + `is_active=False` + AuditLog (`admin_services.py:143-169`). اختبارات: `tests_deprovisioning.py`, `tests_tenant_isolation.py`.

---

## E. Platform Admin Journey — As Implemented

سطحان: **Django admin** `/admin/` و**كونسول CRM مخصّص** `/platform-admin/` (حارس `platform_admin_required`, staff/superuser، `admin_views.py:22-32`).

- **Operations dashboard** `crm_dashboard` (`:74`) — ملخص للقراءة + `data_health` + طوابير.
- **إدارة الشركات** `crm_companies_list` (`:84`) + **«Company 360» = `crm_company_detail`** (`:109-145`, template 67KB): snapshot تشغيلي + رحلة + أدلة/فجوات/مخاطر/تقارير/اشتراك + `framework_entitlement` + تعارضات الأحكام `_verdict_disagreements` (`:163-166`).
- **الاشتراك/الدفع** `crm_subscription_action` (`:191-232`: activate/cancel/start_trial، reason)، `add/confirm/reject_manual_payment` (`:235-303`, reason، try/except «لا يُسقط الكونسول»).
- **المدقّقون** approval (`:461-475`) + assignment (`:329-381`, «المدقّق ما زال يجب أن يقبل»).
- **المراقبة** `crm_auditor_requests` (`:384-399`) + `crm_rfi_dashboard` (`:478-511`, «الإدارة تراقب — لا تُصدر/تُعدّل حكم مدقّق أبدًا»).
- **CRM/الحسابات** notes/status/link-unlink («لا يحذف شيئًا» `:441`).
- **اعتماد النطاق والتقارير** ليست في الكونسول — **داخل بوابة الشركة بحارس staff** (`compliance/views.py:675,604,805`).
- **ما لا يستطيعه الأدمن:** إصدار/تعديل حكم مدقّق؛ تفعيل اشتراك نشط لا يُمدّده (`:208`)؛ توقيع حكم لشركته (قاعدة الاستقلالية).

---

## F. Permission Matrix (مختصر، بأدلة)

| القدرة | Company | Auditor | Platform Admin | Evidence |
|---|---|---|---|---|
| إنشاء شركة/تسجيل | ✅ (ذاتي) | — | (عبر admin link) | `core/views.py:330` |
| اعتماد نطاق الشركة | ✅ (نطاقه) | ❌ | ✅ (staff، per-scope) | `compliance/views.py:718,675` |
| رفع الأدلة | ✅ (بريد مُوثَّق) | ❌ (قراءة فقط) | (staff) | `:882-928`; `review_control.html:90` |
| حكم الضابط النهائي | ❌ (يعرض) | ✅ (المُعيَّن النشط) | ✅ (staff، غير شركته) | `save_verdict:286`; `auditor_verdict.py:47` |
| إصدار AuditReport | ❌ | ✅ (المُعيَّن) | ❌ | `submit_report:728` |
| تفعيل اشتراك/دفع | ❌ (يطلب) | ❌ | ✅ | `admin_views.py:256-303` |
| إسناد مدقّق | ✅ (يطلب، مشترك) | يقبل/يرفض | ✅ (يطلب) | `auditors/views.py:210`; `admin_views.py:331` |
| رؤية شركة غير مُعيَّنة | ❌ | ❌ (404) | ✅ | `auditor_portal/views.py:27-47` |
| AI يُصدر قرار امتثال نهائي | ❌ | ❌ | ❌ | `compliance/services.py:126-130` (R3) |

**قاعدة تصميمية (PHASE 2):** لا يجوز للـUI أن يوحي بأي قدرة أعلاه غير الموجودة — مثل زر «اعتماد» للمدقّق على الأدلة، أو «إصدار شهادة»، أو تفعيل اشتراك ذاتي للشركة.

---

## G. Workflow / State Machines (بأدلة)

- **Company.status** (`core/models.py:125-139`): `registered→classified→in_assessment→audit_ready→certified→expired`.
- **Assessment.status** (`compliance/models.py:209-231`): `draft/in_progress/ai_complete/auditor_review/completed/expired`؛ TERMINAL={completed,expired}؛ الانتقال الحقيقي الوحيد `auditor_review→{completed,expired}` (`transition_to`, `InvalidAssessmentTransition`).
- **CompanyControl.status** (`:126-135`): `not_started/in_progress/evidence_uploaded/ai_reviewed/compliant/non_compliant/partially_compliant/not_applicable`.
- **EvidenceSubmission.status** (`:782-789`): `uploaded/pending_review/accepted/rejected/needs_reupload/archived`.
- **Applicability/Scope**: `FrameworkApplicabilityResult.decision` (applicable/not_applicable/needs_review/manually_overridden)؛ `CompanyFrameworkScope.status` (proposed/approved/rejected/needs_review).
- **Subscription.status** (`billing/models.py:61-70`): inactive/trial/pending_payment/active/past_due/expired/suspended/cancelled؛ `is_active`=status∈{active,trial} AND `ends_at≥now`.
- **Payment.status** (`:119-122`): pending/paid/failed/cancelled/refunded. Moyasar callback→failed/cancelled فقط؛ التفعيل فقط بعد Fetch verification.
- **AuditorProfile.status**: pending_review/active/suspended/inactive (reject=inactive).
- **AuditorAssignment.status**: requested/accepted/rejected/cancelled/completed (ACTIVE=requested,accepted).
- **AuditorControlVerdict.status**: not_reviewed/compliant/partially_compliant/non_compliant/needs_more_evidence/not_applicable (needs_more_evidence **ليست نهائية** للإتمام، `lifecycle.py:16`).
- **AuditReport.verdict** (write-once): pass=«جاهز مبدئيًا»/conditional_pass/fail.
- **DocumentRequest (RFI).status**: open/pending(legacy)/responded/under_review/closed/cancelled — **`under_review` حالة بلا كاتب (dead-state)**.
- **AuditFinding.status**: open/in_remediation/reverify/closed/reopened؛ CorrectiveAction: planned/in_progress/done/verified.
- **RiskItem.status**: open/in_progress/mitigated/accepted/closed؛ severity حتمي من likelihood×impact.

---

## H. Current Frontend Architecture

- **الغلاف الأساسي** `base.html` (285 سطر): `dir` من `LANGUAGE_BIDI` (`:2`)؛ بلوكات `title/extra_head/body/content/extra_js`؛ **navbar داكن `bg-gov-green-800`** (authenticated `:90-190`) مقابل public (`:191-206`).
- **ثلاثة أصداف / أربعة أنظمة تنسيق:** 87 قالبًا يمتدّ `base.html` (dark-pine legacy)، 9 يمتدّ `platform_admin/base.html`، 3 يمتدّ `onboarding/auth_base.html` (light `.au`)؛ + `core/landing.html` (light `.lp`) + `components/auth_form_styles.html` (جزيرة تنسيق رابعة). **125 قالبًا** إجمالًا.
- **لا Alpine.js إطلاقًا** (grep=0). التفاعل عبر `<details>/<summary>` + IIFEs يدوية (busy-overlay، pw-toggle، scroll-reveal). لا Node build tooling.
- **Tailwind عبر CDN `<script>` في الإنتاج** (`base.html:7`) + Font Awesome CDN + Google Fonts CDN.
- **لا sidebar تطبيق دائم للمستخدم الداخل** — تنقّل top-bar فقط + `<details>` «المزيد» يخفي 10+ وجهات؛ قائمتا Desktop/Mobile **نسختان يدويتان مكرّرتان** (`:99-135` مقابل `:152-186`).
- عدة بلوكات **تُثبّت `dir="rtl"`** بغضّ النظر عن اللغة (`platform_admin/base.html:15,23`, `pagination.html:7`) → خطأ في واجهة EN.

---

## I. Current Design System (tokens)

- **Tailwind config inline** (`base.html:9-51`, «Sakinah»): `gov-green` (50 #eff4f1 … 700 #356a54 800 **#2a5646** 900 #1f4135 950 #12271f)؛ `gov-gray` greige؛ `gov-sand #b49a6a`؛ semantics `gov-ok #4e9c7f / gov-warn #c08a3e / gov-crit #b4675c`.
- **خطوط:** Inter + Noto Sans Arabic (Google CDN).
- **انجراف حادّ للـtokens:** **أربعة أخضرات** متعايشة: `#2a5646` (token، مكرّر خامًا **100×**)، `#176B55` (`.au/.lp --brand`)، `#3b7a66` (focus ring base.html)، `#1a4731` (زر auth). **ثلاثة أنظمة أصناف:** `gov-*` (1018 استخدام)، `.au-*/.lp-*` (225)، `ct-*` (hex مضمّن). كثافة `style=` inline عالية (compliance 320، core 204).
- `#ct-busy-overlay` (`base.html:241-281`، `data-busy` × **60**)، reduced-motion محترم (`:83`).

---

## J. UI/UX Problems (مصنّفة — لم تُصلَح)

**P0 (حرجة):**
- Tailwind عبر CDN في الإنتاج (render-blocking، بلا purge، تعطّل CDN يُسقط الواجهة) — `base.html:7`.
- لا مصدر حقيقة واحد للألوان (4 أخضرات، 3 أنظمة أصناف؛ `#2a5646` مكرّر 100×) → تغيير palette مستحيل من مكان واحد.
- صدعان بصريان: dark-pine (التطبيق) مقابل light `.au/.lp` (Landing/التسجيل) — المستخدم يعبر حدًّا بصريًا حادًّا؛ والـtokens منسوخة لا مشتركة وتنجرف (gold `#B8892B` مقابل `#B08423`).

**P1 (مهمة):**
- لا sidebar تطبيق دائم؛ تنقّل top-bar عميق + «المزيد» يخفي وجهات؛ قائمتان مكرّرتان يدويًا.
- تكامل RTL: `dir="rtl"` مُثبّت في مواضع → EN يُحاذى يمينًا خطأً.
- الجداول: 37 `<table>` مقابل 22 `overflow-x` → فيض أفقي محتمل على الموبايل.
- تواصل الحالة غير متّسق: `status_badge`/`evidence_status`/`ct-badge` تُرمّز الألوان مستقلةً؛ semantic tokens مُتجاوَزة بـhex خام.

**P2 (تحسينية):**
- ثلاثة أنظمة تنسيق حقول (base/‎.au-input/.auth-card) بألوان تركيز/أنصاف مختلفة.
- Empty-states نص عاري بلا مكوّن موحّد؛ **لا skeleton/loading placeholders** إطلاقًا.
- بريق a11y (reduced-motion، focus rings، skip-link) موجود لكنه مبعثر بين جزر تنسيق.

---

## K. Analysis of Reference Images (مجلد «سيناريو»)

المجلد = مرجع بصري (prototype `index.html/styles.css` + `logo.png` + صور رحلة 1–9، والـ8.x/9.1 لم تُفتح بعد). **مرجع بصري لا حقيقة وظيفية** (PHASE 6/20).

**نظام تصميم الـprototype (styles.css):** خط **IBM Plex Sans Arabic**؛ ألوان `--green:#0c6b55`، `--gold:#c69b5a`، `--ink:#102c2d`، `--line:#dfe7e3`، semantics `#cd5a52/#c38c34`؛ container **1420px**؛ Hero ضخم (clamp حتى 5.15rem)؛ لوحة app-window (sidebar 160px + 4 KPIs + أشرطة أطر + دونات) + تنويه «بيانات توضيحية لأغراض العرض فقط».

| الصورة | الشاشة | KEEP / IMPROVE / تعارض مع الكود |
|---|---|---|
| logo.png | الشعار: **درع ذهبي «1S» + wordmark كحلي** + «منصة الامتثال السيبراني» | KEEP الاتجاه؛ **يحتاج SVG production نظيف** (فيه خطأ إملائي «الامنتال») |
| 1.png | Landing (**أخضر**، لوحة غنية، فيه **ISO 27001**) | KEEP التخطيط؛ **احذف ISO 27001** (غير مدعوم) |
| 2.png | 2.1 اختيار الحساب (منشأة/فردي، أفق) | KEEP؛ «فردي» = مسار المدقّق/الأفراد |
| 3.png | 2.2 تسجيل split + **Microsoft/Google/SSO** | IMPROVE؛ **احذف SSO** (لا backend) |
| 5.png | 2.3 تحقّق **برابط + عدّاد `01:45`** | **تعارض: الكود OTP 6 أرقام + throttle 60ث** — استبدل بالعدّاد الحقيقي |
| 6.png | 2.4 «تم التحقق بنجاح» + الخطوة التالية | KEEP (صادق ببيانات حقيقية) |
| 7.png | إعداد المنشأة (اسم قانوني/CR/تاريخ/قطاع/حجم/مدينة/حساسية/تواصل +966) + «ملخص الإعداد» جانبي | KEEP — يطابق `CompanyIntakeProfile`/`Company` |
| 9.png | اكتمال الإعداد (ملخص + «ما التالي؟» + «ابدأ رحلتك») | KEEP |

**تعارضات المرجع الداخلية:** stepper 4 خطوات (2.x) مقابل 5 خطوات (إعداد المنشأة) — يجب توحيده. الشعار في 2.png/logo.png ذهبي/كحلي، بينما Landing (1.png) أخضر — قرار هوية مطلوب (انظر M).

---

## L. Proposed Design Direction (Saudi Enterprise، ليس Cyberpunk)

اتجاه **مؤسسي سعودي هادئ فاتح**، Arabic-first RTL، يوحّد الصدعين الحاليين في نظام واحد:
- **نظام تصميم واحد (Foundations + Components)** يُشارك بين Landing/التسجيل/التطبيق — لا نسخ.
- **سطوح فاتحة** (أبيض/عاجي/محايد دافئ)، حبر داكن للنص، **أخضر مؤسسي كـprimary**، **ذهبي كلكنة محدودة جدًا**، **كحلي للشعار/العناوين الكبرى فقط**.
- **App shell جديد**: sidebar تطبيق دائم (يحلّ مشكلة «المزيد») مبنيّ **data-driven حسب `portal_for()`** لا branching داخل القالب — فيمنع أن يوحي بصلاحية غير موجودة.
- **مكوّنات موحّدة**: badge/status/card/table/stepper/timeline/empty/skeleton/toast/drawer — تُغطّي كيانات المجال (framework/control/evidence/gap/risk/RFI/verdict) بألوان دلالية ثابتة.
- **Alpine.js** (progressive enhancement فقط: drawer/dropdown/tabs/accordion/modal/toast/filters/file-preview) — Business logic تبقى backend.
- **RTL/LTR حقيقي** (logical properties، لا `dir="rtl"` مُثبّت)، WCAG 2.2 AA، motion 150–250ms + reduced-motion.

---

## M. Proposed Color Direction (ابدأ من الحالي، لا Brand migration كاملة)

توحيد **token واحد** مصدرًا للحقيقة (يُنهي الأخضرات الأربعة):
- **Primary (أخضر مؤسسي):** توحيد على درجة واحدة — مرشّح `#176B55` (الحالي في `.au/.lp`) أو `#0c6b55` (prototype)؛ **قرار مطلوب منك**.
- **Neutrals:** خلفية عاجية/محايدة دافئة + سطوح بيضاء + حدود `#DDE6E2`.
- **Accent ذهبي محدود جدًا:** `#B8892B`/`#c69b5a` — للشعار واللمسات فقط، لا مساحات.
- **كحلي `#15243D`:** للشعار (درع ذهبي + wordmark كحلي) + عناوين كبرى اختياريًا — **ليس** خلفيات داكنة.
- **دلالية منفصلة (تبقى):** ok/warn/crit — الفجوة الحرِجة تبقى **حمراء**، لا ذهبية/خضراء.
- **ممنوع:** أسود مهيمن، navy مساحات كبيرة، neon، تدرّجات قوية، sidebar كتلة داكنة.

**تنبيه هوية (يحتاج قرارك):** الصور تعرض هويتين — Landing أخضر مقابل تسجيل/شعار ذهبي-كحلي. أوصي: **أخضر primary موحّد + شعار ذهبي/كحلي + لكنة ذهبية** عبر كل الأسطح (اتساق العلامة).

---

## N. Components to Preserve (يعمل جيدًا — حسّن لا تُعِد كتابة)

- **منطق الحُرّاس والحالات كما هو** (backend) — لا يُلمَس.
- `components/journey_*` (stepper/step_card/current_step_card ×8/next_action_card)، `_workflow_stepper.html` — بنية «أين أنا/ما التالي» ناضجة.
- `components/status_badge.html`, `evidence_status.html` (فصل حالة الملف عن حكم الامتثال — سليم دلاليًا)، `pagination.html`, `journey_nav.html`, `feature_blocked.html`.
- `onboarding/_au_field.html`/`_au_pw_field.html`/`_stepper.html`، غلاف `.au` الفاتح، Landing `.lp` الحالي (بعد توحيد الـtokens).
- `#ct-busy-overlay` + `smart_processing` + reduced-motion + focus rings + skip-link.
- **إسناد Get Solution** (إلزامي، `https://gscompany.sa/`).

---

## O. Components to Redesign / Unify

- **توحيد الـtokens** في مصدر واحد (ينهي 4 أخضرات + 3 أنظمة أصناف + hex مكرّر 100×).
- **App shell + sidebar تطبيق دائم data-driven** (يستبدل top-bar «المزيد» + القائمتين المكرّرتين).
- **نظام حقول موحّد** (بدل ثلاثة أنظمة تنسيق).
- **جداول responsive** (overflow-x شامل) + **skeleton/empty-state** موحّدة.
- **RTL منطقي** (إزالة `dir="rtl"` المُثبّت).
- **إخراج Tailwind من CDN** إلى build مُجمَّع (خارج نطاق التصميم لكنه P0 تقني).
- **شعار SVG production** (بدل raster/الحالي).

---

## P. Missing / Unclear Business Rules

1. **ازدواجية اعتماد النطاق:** الشركة تعتمد نطاقها ذاتيًا (`approve_company_scope`) **و** staff يعتمد per-scope — أيّهما المعتمد؟ (`compliance/views.py:718` مقابل `:670-715`). **قرار مطلوب.**
2. **تعارض الـstepper مقابل الحُرّاس:** الـstepper يضع auditor_selection قبل subscription ويقفل reports فقط، لكن `auditors_list` **يتطلب اشتراكًا فعّالًا** (`auditors/services.py:22`). ترتيب مضلّل.
3. **مسارا تسجيل** (self-service OTP مقابل legacy link+AI) — أيّهما القانوني؟ الـUI يجب أن يعكس واحدًا.
4. **ازدواجية النماذج:** تقييمان (`Assessment` مقابل `ControlAssessment`)، أدلة (`Evidence` مقابل `EvidenceSubmission`)، أحكام (`AuditorControlVerdict` مقابل `AuditorFinalVerdict`)، إسناد (`AuditorAssignment` مقابل `Assessment.assigned_auditor`) — أيّها يُعرَض في UI الجديد؟
5. **RFI `under_review`** حالة بلا كاتب (dead-state) — تُعرض أو تُزال؟
6. **`role='auditor'` decorative** — أي UI يعتمد `role` بدل `AuditorProfile` سيكون خاطئًا.
7. **مبالغ الدفع/الخطط** — لا تُخترع؛ من `Plan` فعليًا.
8. NOT VERIFIED: لا نموذج `Classification` مستقل، ولا `ReadinessReport` مستقل (PDF فقط)؛ صور 8.x/9.1 لم تُفتح بعد.

---

## Q. Risks Before Redesign

- **Regression عالٍ:** 125 قالبًا، منطق أدوار/حالات/حُرّاس معقّد؛ أي redesign يجب أن **يحافظ على الحُرّاس والحالات وأسماء الحقول والاختبارات** (اختبارات كثيرة تربط UI markers — `ct-step/data-step-pill/data-busy`، سلاسل عربية، صياغة «ليست شهادة»).
- **صدق UI:** خطر إيحاء بصلاحية غير موجودة (SSO، اعتماد مدقّق للأدلة، شهادة، تفعيل ذاتي) — F/K توثّق الممنوعات.
- **Tailwind CDN:** أي اعتماد على classes جديدة يزيد هشاشة الإنتاج حتى نُخرجه لـbuild.
- **انجراف الـtokens:** بدون توحيد أولًا، كل شاشة جديدة تضيف أخضر/hex خامًا.
- **AI:** الحفاظ على «advisory only» بصريًا (فصل تحليل AI عن قرار بشري) — R3/residency/الاستقلالية.
- **صور 8.x/9.1 غير مقروءة** — قد تكشف شاشات تطبيق/مدقّق/إدارة إضافية تغيّر النطاق.

---

## R. Proposed Redesign Order (step-by-step، بعد قرارك فقط)

**المرحلة 0 (أساس، قبل أي شاشة):** توحيد Design Tokens + Foundations + مكوّنات أساسية (Alpine للتفاعل) + App shell/sidebar data-driven + إخراج Tailwind من CDN.

ثم **Company Journey** (واحدة تلو الأخرى + مراجعة بعد كلٍّ):
1) Landing → مراجعة · 2) التسجيل (2.1→2.2→2.3 OTP→2.4) → مراجعة · 3) إعداد المنشأة/Intake → مراجعة · 4) التصنيف/النطاق → مراجعة · 5) اللوحة → مراجعة · 6) الضوابط/الأدلة → مراجعة · 7) الفجوات/المخاطر/المعالجة → مراجعة · 8) مراجعة المدقّق/RFI/الأحكام (جانب الشركة) → مراجعة · 9) التقارير/المراقبة → مراجعة.

ثم **Auditor Journey** (البوابة → طابور المراجعة → مراجعة التقييم/الضابط → RFI → الحكم → التقرير)، ثم **Platform Admin Journey** (Operations → Company 360 → الاشتراك/الدفع → المدقّقون → المراقبة).

**قاعدة:** لا انتقال تلقائي للخطوة التالية؛ مراجعة بعد كل خطوة.

---

## القرارات المطلوبة منك قبل GO
1. **درجة الأخضر الموحّدة** (`#176B55` أم `#0c6b55`؟) ونطاق الهوية الذهبية/الكحلية.
2. **حسم الازدواجيات** (P1–P4): اعتماد النطاق، مسار التسجيل، النماذج المزدوجة.
3. **إخراج Tailwind من CDN** الآن أم لاحقًا (P0 تقني).
4. هل أفتح صور **8.x/9.1** لإكمال K قبل GO؟

**STOP — بانتظار قرارك: GO / GO WITH CONDITIONS / NO-GO. لن أبدأ أي إعادة تصميم أو تعديل كود قبل ذلك (PHASE 24).**
