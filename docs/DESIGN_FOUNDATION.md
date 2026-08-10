# P0-UIUX-FND-01 — Design Foundation & Frontend Normalization
**1SaudiCyber — Foundation + Normalization + Canonical Workflow Closure**

> النطاق: أساس تصميم/واجهة موحّد + تطبيع + إغلاق المسار القانوني. **لا إعادة تصميم لأي رحلة/شاشة.** الـLanding الأخيرة = **مرجع بصري معتمد**. التغيير التقني الوحيد المُنفَّذ فعليًا = ترحيل Tailwind من CDN إلى build (P/S/T).
>
> **§32 — فصل المستويات:** `✅ VERIFIED FROM CODE` (بدليل file:line) · `🎨 DESIGN DECISION` (قرار تصميمي) · `💡 PROPOSED` (مقترح للاعتماد) · `❓ NOT VERIFIED`. لا يُعرَض أي قرار تصميمي كأنه حقيقة backend.

---

## A. Canonical Workflow Matrix (المسار القانوني لكل نطاق) — ✅ VERIFIED

| النطاق | Canonical Path (المصدر الحقيقي) | Evidence |
|---|---|---|
| التسجيل | `company_self_register` (self-service، OTP) → onboarding | `core/views.py:330-382` |
| تأكيد البريد | **OTP 6 أرقام + throttle 60ث** (غير حاجب للدخول) | `core/views.py:256-285`; `otp_services.py` |
| إعداد المنشأة | `onboarding` → `onboarding_complete` → `compliance:dashboard` | `core/views.py:402-420` |
| الاشتراك | `billing:home` → `select_plan` → `create_pending_subscription` | `billing/views.py:21-84` |
| الدفع | manual (تأكيد إداري) أو moyasar (تفعيل بعد تحقّق خادمي فقط) | `subscription_services.py`; `billing/verification.py:143-175` |
| التصنيف | **حتمي بلا AI** `smart_classification.classify_company` (المُغذّي `intake_wizard`) | `compliance/views.py:461-546`; `smart_classification.py:2,9` |
| اعتماد النطاق | الشركة تعتمد نطاقها `approve_company_scope` (`@email_verified_required`) | `compliance/views.py:718-765` |
| إنشاء التقييم | auditor: `ensure_assessments_for_auditor` لكل إسناد accepted؛ staff: `generate_assessments_view` | `auditor_portal/views.py:94-117`; `compliance/views.py:1124` |
| رفع الأدلة | v2 `evidence_upload_v2` (`EvidenceSubmission`) | `compliance/views.py:882-949` |
| إسناد المدقّق | `AuditorAssignment` (طلب من الشركة/الإدارة → قبول المدقّق) | `auditors/views.py:210`; `services.py:39-50` |
| RFI | `DocumentRequest`: auditor create/close/reopen · company respond | `auditor_portal/views.py:534-696` |
| التقرير | `submit_report` → `AuditReport` write-once (**«جاهزية داخلية، ليست شهادة»**) | `auditor_portal/views.py:728-805` |

---

## B. Duplicate / Legacy Flow Matrix (ازدواجيات تحتاج حسمًا) — ✅ VERIFIED + ❓ قرار مطلوب

| Domain | Path A (Canonical مقترح) | Path B (Legacy) | Evidence | Canonical | Legacy | Migration Risk |
|---|---|---|---|---|---|---|
| التسجيل | `company_self_register` (OTP) | `register_company` (رابط + AI inline) | `core/views.py:330` مقابل `:68-150` | **A** 💡 | B | متوسط — كلاهما يُنشئ Company+User؛ B يبني checklist |
| تأكيد البريد | OTP `verify_email_otp` | رابط `verify_email/<token>` | `:256` مقابل `:225-238` | **OTP** 💡 | link | منخفض |
| التصنيف | حتمي `smart_classification` | AI `ai_engine:classify` | `smart_classification.py` مقابل `ai_engine/views.py:13` | **حتمي** 💡 | AI | منخفض (AI استشاري) |
| اعتماد النطاق | الشركة (`approve_company_scope`) | staff per-scope (`approve_framework_scope_view`) | `:718` مقابل `:670-715` | **❓ يحتاج قرارك** | — | **عالٍ — عقد صلاحية (§8)** |
| التقييم | `Assessment` (auditor_portal) | `ControlAssessment` (compliance Phase 3G) | `compliance/models.py:201` مقابل `:880` | ❓ | — | عالٍ — نموذجان |
| الأدلة | `EvidenceSubmission`→checklist | `Evidence`→CompanyControl | `models.py:780` مقابل `:160` | **Submission** 💡 | legacy | متوسط |
| حكم الضابط | `AuditorControlVerdict` | `AuditorFinalVerdict`/`ControlAssessment` | `auditor_portal/models.py:84` مقابل `compliance:1081` | ❓ | — | عالٍ — silos للأحكام |
| إسناد المدقّق | `AuditorAssignment` (شركة) | `Assessment.assigned_auditor` (User) | `auditors/models.py:54` مقابل `compliance:237` | كلاهما مطلوب | — | آليتان متكاملتان |
| RFI حالة | open/responded/closed | `under_review` (بلا كاتب) | `auditor_portal/models.py:32-42` | إزالة dead-state 💡 | — | منخفض |

> **§7 القاعدة:** لا حذف Legacy في هذه المرحلة؛ الهدف تعريف **SOURCE OF TRUTH**. الحذف الآمن لاحقًا بطلب صريح.

### §8 — عقد اعتماد النطاق (يحتاج حسمك قبل تصميم الرحلة) — ✅ الحقائق:
- **من يقترح؟** `propose_framework_scopes(apply=True)` من `intake_wizard`/`applicability_review` (`compliance/views.py:562`).
- **من يؤكّد؟** ازدواجية: (A) **الشركة نفسها** `approve_company_scope` (`:744-745`)، (B) **staff** per-scope `approve_framework_scope_view` (`:675 if not is_staff: return`).
- **متى Approved؟** عند اعتماد proposed/needs_review → يولّد الخطة+القائمة (`:748-756`).
- **بعد الاعتماد:** أي تعديل intake يُبطِل النطاقات المعتمدة إلى `needs_review` (`intake_wizard:515-516`).
- **❓ قرار مطلوب:** هل الاعتماد ذاتي للشركة أم يتطلب موافقة staff؟ الكود يسمح بالاثنين — **لا UX قبل حسم هذا**.

---

## C. Final Reference Image Audit (مجلد «سيناريو» — 19 صورة فريدة) — ✅ (بصري)

**تغطية:** تسويق + قمع التسجيل/التهيئة فقط. **لا صور** للتطبيق المُصادَق ولا بوابة المدقّق ولا CRM الإدارة → تصميمها لاحقًا **من الكود** لا من صور.

| الصورة | الشاشة | الحكم | تعارض مع الكود |
|---|---|---|---|
| 1 | Landing (Hero + لوحة + أطر + AI flow) | IMPROVE | فيها **ISO 27001** (الحيّة أصلحتها) |
| 2 | اختيار الحساب (منشأة/فردي) | KEEP | ❓ تسجيل ذاتي للمدقّق مقابل «الإدارة تُزوّد» |
| 3(=4) | نموذج التسجيل | REDESIGN | **Microsoft/Google/SSO — لا backend** → احذف |
| 5 | تحقّق البريد | IMPROVE | **عدّاد 01:45 وهمي + «رابط»** بينما الكود OTP+60ث |
| 6 | «تم التحقق بنجاح» | KEEP | — |
| 7 | إعداد المنشأة (CR/قطاع/حجم/حساسية) | KEEP | يطابق `CompanyIntakeProfile` |
| 8.1–8.6 | معالج التصنيف/النطاق (6 خطوات) | KEEP (5,6 IMPROVE) | **نِسب انطباق 44/74/55% قبل تقييم**؛ شارات تنقلب 8.5↔8.6؛ سابك 92/94 |
| 9 / 9.1 | إتمام الإعداد (نسختان) | KEEP/توحيد | 9.1 يعرض **«جاهزيتك 58%» قبل تقييم** |
| 5.2–5.5 (ChatGPT) | أطر منطبقة / جدول متطلبات / إجراءات تالية / جاهز للانطلاق | KEEP/IMPROVE | تناقضات بيانات وهمية (27/87 معكوسة) |
| logo | شعار (درع ذهبي/كحلي) | IMPROVE | **خطأ إملائي + raster** (انظر R) |

### تعارضات جديدة (مرجع مقابل كود) — يجب ألا تدخل النظام:
1. **درجات/نِسب قبل أي تقييم** (انطباق % / «جاهزيتك 58%») → أعِد الصياغة **«تقدير مبدئي استشاري»** لا «درجة» (AI استشاري، الشركة لا تُصدر حكمًا — `compliance/services.py:126-130`).
2. **إطلاق «إلزامي/مطلوب» قاطعًا** على الأطر → من عائلة مخاطر «شهادة رسمية» (التقارير دائمًا «ليست اعتمادًا رسميًا» — `dashboard/reports.py:17-22`).
3. **SSO / ISO 27001 / countdown وهمي** → `NOT SUPPORTED` حتى يوجد backend (§10).
4. تناقضات بيانات وهمية في الصور (QA للـmockup).

---

## D. Landing-derived Visual Principles — 🎨 (مُستخرَجة من الـbaseline المعتمد)

من `templates/core/landing.html` + `سيناريو/index.html` (النموذج الأوّلي):
- **فاتح دائمًا:** أبيض/عاجي/محايد دافئ أساس؛ الداكن للنص/lاكنات فقط. لا أسطح داكنة مهيمنة.
- **أخضر مؤسسي primary + ذهبي لكنة محدودة جدًا + كحلي للشعار/العناوين.**
- **حدود أولًا، ظلال ثانيًا** (`0 8px 26px rgba(31,45,40,.06)` نادرًا)، radius معتدل (10–16px).
- **إيقاع أقسام متنفّس** (padding-block ~4rem)، container موحّد.
- **بطاقات خفيفة** (سطح أبيض + حد رفيع + أيقونة صغيرة + عنوان + وصف مقتضب).
- **CTA واحدة مهيمنة** (أخضر) + ثانوية outline.
- **حركة راقية** (fade + translateY، stagger خفيف، مرة واحدة، reduced-motion).
- **RTL حقيقي** (`dir` من `LANGUAGE_BIDI`، أسهم rtl:/ltr:).
- **تنويه «بيانات توضيحية لأغراض العرض فقط»** إلزامي لأي معاينة.

---

## E. Color Token System — 💡 PROPOSED (semantic، مصدر حقيقة واحد)

> 🎨 **قرار جوهري:** توحيد على **`#176B55`** كـ`brand-primary` (هو اللون الفعلي للـLanding المعتمد `.lp/.au --brand`)؛ وتُطبَّع `gov-green-800 #2a5646` إليه تدريجيًا (Q). **brand ≠ success** — كلاهما أخضر لكن token منفصل + **لا لون وحده** (§21).

```
/* Brand */
--color-brand-primary:        #176B55;   /* أخضر مؤسسي — chrome/CTA/روابط */
--color-brand-primary-hover:  #125845;
--color-brand-primary-subtle: #EDF5F1;
--color-brand-secondary:      #15243D;   /* كحلي — الشعار/العناوين الكبرى/emphasis */

/* Accent (ذهبي محدود جدًا) */
--color-accent:               #B0821F;   /* لكنة/هوية فقط — لا مساحات */
--color-accent-subtle:        #F6EFDA;
--color-accent-ink:           #7A5A14;   /* نص ذهبي AA على subtle */

/* Neutrals (فاتح دافئ) */
--color-background:     #F8FAF9;
--color-surface:        #FFFFFF;
--color-surface-muted:  #F4F7F5;
--color-text-primary:   #1F2D28;
--color-text-secondary: #46534C;
--color-text-muted:     #5C6A63;
--color-border:         #DDE6E2;
--color-border-strong:  #C7D3CD;

/* Semantic (منفصلة عن brand) — من حالات الـbackend + status chips المرصودة */
--color-success:         #2E8B6F;  --color-success-subtle: #E3F1EC;  /* ضمن النطاق/متوافق */
--color-warning:         #A96C24;  --color-warning-subtle: #F6ECD9;  /* موصى به/جزئي */
--color-danger:          #A64F45;  --color-danger-subtle:  #F6E3E0;  /* مطلوب/حرِج/غير متوافق */
--color-info:            #2B6C86;  --color-info-subtle:    #E2EEF2;  /* يحتاج مراجعة */
```
- ❓ **NOT VERIFIED / قرار:** درجة الأخضر النهائية (`#176B55` الحالي مقابل `#0c6b55` النموذج) — **أوصي `#176B55`** (الـbaseline الحيّ). الذهبي (`#B0821F` مقابل drift `#B8892B`/`#B08423`) — أوصي توحيد `#B0821F`.
- **الفجوة الحرِجة تبقى حمراء** (`--color-danger`)، لا ذهبية/خضراء (§28).

---

## F. Typography System — 💡 (Arabic-first)

- 🎨 **قرار:** الـbaseline الحيّ = **Inter (لاتيني/أرقام) + Noto Sans Arabic (عربي)**. النموذج يستخدم **IBM Plex Sans Arabic** (أفضل عربيًا) — **❓ قرار: نبقى Inter+Noto أم نعتمد IBM Plex Sans Arabic؟** أوصي: Noto/IBM-Plex للعربي + Inter للأرقام/أكواد الأطر.
- **السلّم** (rem، `text-wrap:balance` للعناوين، line-height عربي أعلى):

| Role | Size | Weight | line-height (AR) | استخدام |
|---|---|---|---|---|
| Display | 2.6–3.1rem clamp | 800 | 1.4 | Hero فقط |
| H1 | 1.9–2.3rem | 800 | 1.4 | عنوان صفحة |
| H2 | 1.5–1.9rem | 800 | 1.45 | قسم |
| H3 | 1.05–1.2rem | 700 | 1.5 | بطاقة |
| H4 | .98rem | 700 | 1.5 | فرعي |
| Body-L | 1.05rem | 400 | 1.9 | مقدّمات |
| Body | .95rem | 400 | 1.8 | نص |
| Body-S | .85rem | 400 | 1.7 | ثانوي |
| Label | .85rem | 600 | 1.4 | حقول |
| Caption | .78rem | 500 | 1.5 | مساعِد |
| Meta | .7rem | 500 | 1.4 | تنويهات |

- `tabular-nums` للأرقام في الجداول/المؤشرات؛ أكواد الأطر (NCA ECC) LTR داخل نص RTL.

---

## G. Spacing / Radius / Border / Shadow — 💡

- **Spacing scale (متوافق Tailwind، 4px base):** 4/8/12/16/20/24/32/40/48/64. لا قيم عشوائية (13/17/23px).
- **Radius:** sm 8px · **default 10px** · lg 16px · pill 999px. لا bubble.
- **Border:** hairline 1px `--color-border`؛ strong `--color-border-strong`؛ accent-rail 3–4px للحالة.
- **Shadow (محدودة، حدود > ظلال):** `none` · `subtle 0 4px 12px rgba(21,45,40,.05)` · `elevated 0 14px 40px rgba(21,45,40,.10)` (modals/hero فقط).
- **Container:** app 1140–1200px · marketing حتى 1420px.
- **Z-index scale:** base 0 · dropdown 40 · sticky-header 50 · overlay 60 · toast 70.
- **Breakpoints:** 320 · 390 · 768 · 1024 · 1440.

---

## H. Semantic Status System — 💡 (من حالات الـbackend الفعلية، لا لون وحده §21)

كل status = **لون + label عربي + أيقونة + معنى**. أمثلة مربوطة بالكود:

| Domain (Model.field) | القيم (✅ من الكود) | التوكن الدلالي |
|---|---|---|
| CompanyControl.status | not_started/in_progress/evidence_uploaded/ai_reviewed/compliant/partially/non_compliant/not_applicable | gray/info/info/info/**success**/warning/**danger**/gray |
| EvidenceSubmission.status | uploaded/pending_review/accepted/rejected/needs_reupload/archived | info/warning/success/danger/warning/gray |
| Assessment.status | draft/in_progress/ai_complete/auditor_review/completed/expired | gray/info/info/info/success/gray |
| Subscription.status | inactive/trial/pending_payment/active/past_due/expired/suspended/cancelled | gray/info/warning/success/danger/gray/danger/gray |
| Payment.status | pending/paid/failed/cancelled/refunded | warning/success/danger/gray/info |
| CompanyFrameworkScope.status | proposed/approved/rejected/needs_review | info/success/danger/warning |
| AuditorAssignment.status | requested/accepted/rejected/cancelled/completed | warning/success/danger/gray/info |
| DocumentRequest(RFI).status | open/responded/closed/cancelled (`under_review` dead) | warning/info/success/gray |
| AuditorControlVerdict.status | not_reviewed/compliant/partially/non_compliant/needs_more_evidence/not_applicable | gray/success/warning/danger/info/gray |
| AuditReport.verdict | pass=«جاهز مبدئيًا»/conditional_pass/fail | success/warning/danger |
| RiskItem.severity | low/medium/high/critical | success/warning/danger/danger-strong |

> **قاعدة صدق:** «مطلوب/إلزامي» في التصنيف = **أحمر دلالي**، لكن الصياغة **«تقدير مبدئي استشاري»** لا حكم قاطع (C.1).

---

## I. Public Shell Architecture — 💡 (موجودة جزئيًا كـ`.lp`/`.au`)

- **الاستخدام:** Landing · Login · Registration · Verification · Password recovery.
- **البنية:** top bar خفيف (شعار + مبدّل لغة + «تسجيل الدخول») + محتوى + footer فاتح (Get Solution إلزامي). بلا sidebar. أفق الرياض watermark اختياري.
- **الحالي:** `templates/core/landing.html` (`.lp`) + `templates/onboarding/auth_base.html` (`.au`) — **يُبقيان** بعد توحيد الـtokens.

---

## J. Onboarding Shell Architecture — 💡

- **الاستخدام:** إعداد المنشأة · الاشتراك · الدفع · التصنيف/النطاق (معالج 8.1–8.6).
- **البنية (من صور 7/8.x):** header خفيف + **stepper أفقي 5 خطوات** أعلى + **left summary rail** (متتبّع خطوات فرعية + شريط تقدّم % + بطاقة «تحتاج مساعدة؟») + منطقة النموذج + footer. **بلا sidebar تطبيق كاملة** (تركيز، تشتيت منخفض).
- **الحالي:** `auth_base.html` + `_stepper.html` أساس صالح للتوسّع.

---

## K. Application Shell Architecture + IA — 💡 (data-driven من `portal_for()`، لا branching في القالب)

- **الاستخدام:** بعد التهيئة — كل وحدات التطبيق.
- **البنية:** **left sidebar دائم (desktop) / collapsible (tablet) / Alpine drawer (mobile)** + top bar (شعار، بحث، إشعارات، مستخدم + شارة دور). يحلّ مشكلة top-bar «المزيد» + القائمتين المكرّرتين (J في تقرير الـAudit).
- **IA للشركة (✅ وحدات مُتحقَّقة بالكود):**

| عنصر التنقّل | Module (route) | Evidence | حالة |
|---|---|---|---|
| نظرة عامة | `compliance_officer_dashboard` / `journey_dashboard` | `dashboard/views.py:72`; `compliance/views.py:202` | ✅ |
| التقييمات | `auditor_review_queue` | `compliance/views.py:1064` | ✅ |
| الضوابط | `controls_list` | `:19` | ✅ |
| الأدلة | `evidence_checklist`/`evidence_submission_list` | `:816,882` | ✅ |
| الفجوات | `gap_dashboard` | `:1240` | ✅ |
| المخاطر | `risk:list` | `risk/views.py:13` | ✅ |
| المعالجة | RemediationTask (تحت المخاطر) | `risk/views.py:188` | ✅ |
| طلبات المعلومات | `company_rfi_list` | `auditor_portal/views.py:636` | ✅ |
| التقارير | `reports_index` | `compliance/views.py:1162` | ✅ |
| المراقبة | `monitoring:overview` | `monitoring/views.py:122` | ✅ |
| الفريق | `team_view` (UserInvite) | `core/urls.py:55` | ✅ |
| الإعدادات | `settings_hub` | `core/urls.py:56` | ✅ |
| سجل النشاط | AuditLog model موجود؛ **عرض للشركة** | `core/models.py:255` | ❓ NOT VERIFIED (نموذج نعم، view للشركة غير مؤكّد) |

> **قاعدة:** لا يُضاف عنصر تنقّل لقدرة غير موجودة (§12). المدقّق/الإدارة لهما IA منفصل (auditor_portal / platform_admin) — **تصميم منفصل، ليس هذه المرحلة**.

---

## L. Component Architecture — 💡 (عرّف الآن، لا تُنفّذ الرحلات)

- **يُحفَظ ويُحسَّن (موجود يعمل):** `components/journey_*` (stepper/current_step_card ×8/next_action_card)، `_workflow_stepper`، `status_badge`، `evidence_status` (فصل حالة الملف عن الحكم — سليم)، `pagination`، `journey_nav`، `feature_blocked`، `onboarding/_au_field`/`_au_pw_field`/`_stepper`، busy-overlay، smart_processing.
- **أساسية موحّدة (تُبنى):** Button · Input/Select/Textarea/Checkbox/Radio/Search · Card · Badge/StatusChip · Table (responsive) · Tabs · Breadcrumb · Stepper · Progress · Modal · **Drawer** · Dropdown · Toast · Tooltip · Pagination · **EmptyState** · **ErrorState** · **Skeleton** · FileUpload · Timeline · ActivityItem.
- **Domain (مربوطة بـH):** FrameworkBadge · ControlStatus · EvidenceStatus · AssessmentStatus · PaymentStatus · ScopeStatus · GapSeverity · RiskRating · RemediationStatus · RFIStatus · AuditorVerdict.
- Alpine.js لـ: Drawer/Dropdown/Tabs/Accordion/Modal/Toast/Filters/FilePreview فقط — **Business logic تبقى backend**.

---

## M. RTL Strategy — 💡

- الاتجاه من `LANGUAGE_BIDI` فقط؛ **إزالة `dir="rtl"` المُثبّت** (`platform_admin/base.html:15,23`, `pagination.html:7`) — سبب أخطاء EN.
- **Logical properties** (`ms-/me-/ps-/pe-`, `inset-inline-*`, `border-inline-*`) لا `left/right`.
- مكوّنات **direction-aware من الأصل** (لا ملف RTL-override ضخم): أسهم/breadcrumb/stepper/timeline/drawer/table headers/pagination عبر `rtl:`/`ltr:`.
- أكواد الأطر/الأرقام LTR داخل RTL.

---

## N. Accessibility Foundation — 💡 (WCAG 2.2 AA)

- **focus-visible** موحّد (`outline:2px var(--color-brand-primary); offset:2px`)؛ keyboard كامل؛ لا `div` قابل للنقر.
- حالات: disabled/error/required (`aria-invalid`, `aria-describedby`, `*` + label)؛ **لا لون وحده** (أيقونة+label مع الحالة).
- **تباين مُتحقَّق:** gold-ink `#7A5A14` على gold-subtle `#F6EFDA` (AA)؛ text-primary على surface (AAA)؛ كل أزواج الـtokens تمرّ مراجعة تباين قبل الاعتماد.
- touch targets ≥44px؛ modal/drawer focus-trap + Esc + إعادة التركيز؛ `aria-live` للإشعارات؛ skip-link.

---

## O. Motion Foundation — 💡 (من لغة Landing الهادئة)

- **fast 150ms** (hover/feedback) · **normal 200–250ms** (dropdown/drawer/tabs) · **slow 400–600ms** (onboarding success/diagram reveal، مرة واحدة).
- بلا particles/bounce/neon/infinite. `prefers-reduced-motion: reduce` يُعطّل reveal/counters/diagrams.
- Progressive enhancement: المحتوى ظاهر بلا JS (لا `opacity:0` دائم).

---

## P. Tailwind Build Migration Report — ✅ **مُنفَّذ ومُتحقَّق** (بلا regression)

- `npm i -D tailwindcss@3.4.17` → build `static/css/app.css` = **40,320 bytes** (مصغّر).
- `tailwind.config.js`: `content:['./templates/**/*.html']` (كل الـ120 قالبًا تحت `templates/`؛ classes الديناميكية = تبديل سلاسل **كاملة** فلا فقد) + palette منسوخ حرفيًا + `fontFamily.sans`.
- `base.html`: `{% load i18n static %}` + حذف CDN `<script>` + الـinline config + `<link {% static 'css/app.css' %}>`. الأنماط العامة + Google Fonts + Font Awesome **بلا لمس**.
- **تحقّق:** `check` ✅ · `collectstatic` (2 copied, 412 post-processed) ✅ · `/`, `/get-started/`, `/get-started/company/`, `/login/` = **200، بلا `cdn.tailwindcss.com`، مع `css/app.css`** · لقطة Landing كاملة التنسيق (لا FOUC) · **22 اختبارًا OK** (Localization/CommentLeak/LandingTranslation).
- **CDNs متبقّية (خارج النطاق، لم تُلمَس):** Google Fonts + Font Awesome — تُعالَج لاحقًا.

---

## Q. Legacy CSS Normalization Plan — 💡 (لا global replace)

- المشكلة: **4 أخضرات** (`#2a5646` ×100، `#176B55`، `#3b7a66`، `#1a4731`) + **3 أنظمة أصناف** (`gov-*` ×1018، `.au/.lp-*` ×225، `ct-*`) + hex خام مضمّن.
- **الخطة (تدريجية، per-shell، بعد GO):**
  1. اعتماد token layer واحد (E) في `input.css` (`:root` + `@theme`) — **مصدر حقيقة واحد**.
  2. تصنيف كل استخدام لـ`#2a5646` (brand/button/text/border/success/nav) → ربط بالـtoken الصحيح — **لا بحث-استبدال أعمى** (الدلالات مختلفة).
  3. توحيد `gov-green-800 → brand-primary` عبر alias في tailwind.config (يمنع كسر 1018 استخدامًا).
  4. دمج `.au/.lp` (نسختان تنجرفان) في نظام واحد مُشارك.
  5. توحيد أنظمة الحقول الثلاثة في مكوّن Input واحد.
- **يُطبَّق per-shell عند تصميم كل رحلة** — لا تعديل 125 قالبًا الآن (§33/§34).

---

## R. Logo / Brand Asset Status — 🚫 **BLOCKER**

- ✅ الأصل الوحيد = `سيناريو/logo.png` **raster** (1536×1024 RGBA، mockup بتوهّج). **لا مصدر SVG/vector في المستودع كله.**
- ✅ **خطأ إملائي في الأصل:** «منصة الامنتال السـيراني» بدل «منصة الامتثال السيبراني».
- **حسب §6: لن أخترع شعارًا.** المطلوب **مصدر vector رسمي (AI/SVG/EPS)** من المصمّم + تصحيح الإملاء عند المصدر، ثم إنتاج معمارية: أفقي · symbol فقط · light/dark · monochrome.
- **stopgap مؤقّت (ليس رسميًا):** درع SVG inline مبنيّ يدويًا (ذهبي + «1S» + wordmark كحلي، **بالإملاء الصحيح**) موجود في `auth_base.html`/`landing.html` — يُستخدم **مؤقتًا فقط** حتى يصل الـvector الرسمي.

---

## S. Files Changed (هذه المهمة فقط)

**تقني (ترحيل Tailwind — commit مستقل مقترح):** `templates/base.html` (رأس فقط) · `tailwind.config.js` (جديد) · `static/src/input.css` (جديد) · `static/css/app.css` (جديد، مبني) · `package.json` + `package-lock.json` (جديد) · `.gitignore` (`node_modules/`).
**توثيق:** `docs/DESIGN_FOUNDATION.md` (هذا التقرير) · `docs/UIUX_AUDIT_REPORT.md` (سابق).
**لم يُلمَس:** أي من الـ125 قالبًا (عدا رأس base.html) · أي backend/routes/forms/tests · أي رحلة/شاشة.

---

## T. Tests Run + Exact Results

- `python manage.py check` → **System check identified no issues (0 silenced)**.
- `python manage.py collectstatic --noinput` → 2 copied, 157 unmodified, 412 post-processed (exit 0).
- `python manage.py test core.tests.Phase4AFixALocalizationTests core.tests.Phase8CFixDCommentLeakTests core.tests.Phase8D2FixBLandingTranslationTests` → **Ran 22 tests … OK**.
- تحقّق بصري: 4 صفحات رئيسية 200 + لقطة Landing كاملة التنسيق (بلا CDN، بلا FOUC).
- ❓ لم يُشغَّل الـFull suite في هذه المهمة (ترحيل تقني معزول؛ يُنصح تشغيله قبل الـcommit).

---

## U. Remaining Risks

- **CDNs متبقّية** (Google Fonts + Font Awesome) — نقطة هشاشة إنتاج ثانية؛ تُعالَج لاحقًا.
- **توحيد الـtokens لم يُطبَّق بعد** على القوالب (per-shell قادم) — الصدعان البصريان قائمان مؤقتًا.
- **ازدواجيات غير محسومة** (اعتماد النطاق، التقييم، الأحكام) — **تمنع تصميم الرحلة** قبل قرارك (B/§8).
- **مخاطر صدق في المرجع** (نِسب قبل تقييم، «إلزامي» قاطع، SSO/ISO/countdown) — يجب تحييدها في كل شاشة قادمة (C).
- **لا صور مرجعية للتطبيق/المدقّق/الإدارة** — تُصمَّم من الكود (مخاطرة تصميم أعلى).
- **الشعار blocker** — يوقف إغلاق الهوية.
- **Full suite لم يُشغَّل بعد ترحيل Tailwind** (منخفض الخطر لكن يُنصح).

---

## V. Recommendation

### 🟡 GO WITH CONDITIONS

الأساس التقني مُنجَز وآمن (Tailwind build بلا regression، 22 اختبار OK)، والفحص/الأدلة كاملة. **قبل بدء Company Journey** يلزم حسمك في:

1. **الهوية اللونية/الخطية (E/F):** اعتماد `brand-primary = #176B55` + الذهبي `#B0821F`؛ والخط (Inter+Noto مقابل IBM Plex Sans Arabic).
2. **الازدواجيات القانونية (B/§8):** اعتماد النطاق (ذاتي/staff)، مسار التسجيل، نموذجا التقييم/الأحكام.
3. **الشعار (R):** توفير vector رسمي مُصحَّح (blocker للهوية).
4. **قواعد الصدق (C):** الموافقة على تحييد «النِسب قبل التقييم» و«إلزامي القاطع» و SSO/ISO/countdown في كل شاشة قادمة.
5. **(اختياري الآن):** توقيت إزالة Fonts/FA CDN + تطبيق الـtokens per-shell.

**بعد الاعتماد** نبدأ **Company Journey خطوة-بخطوة** (مع مراجعة بعد كل شاشة)، محافظين على Landing كمرجع بصري معتمد.

**🛑 STOP (§35) — بانتظار: GO / GO WITH CONDITIONS / NO-GO. لن أبدأ أي رحلة أو تعديل قوالب قبل قرارك.**
