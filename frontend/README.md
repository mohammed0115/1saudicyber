# 1SaudiCyber — Frontend

منصة الامتثال السيبراني | واجهة أمامية مستقلة مبنية بـ **Alpine.js** و **Tailwind CSS**

---

## هيكل المشروع

```
frontend/
├── index.html                          # الصفحة الرئيسية (Landing Page)
├── assets/
│   ├── css/
│   │   ├── input.css                   # مصدر Tailwind CSS
│   │   └── style.css                   # ملف CSS المبني (لا تعدّله يدويًا)
│   ├── js/
│   │   └── app.js                      # Alpine.js data & utilities
│   └── images/
│       └── logo.png                    # شعار المنصة
└── pages/
    ├── login.html                      # تسجيل الدخول
    ├── register.html                   # اختيار نوع الحساب
    ├── register-company.html           # نموذج إنشاء حساب منشأة
    ├── verify-email.html               # تأكيد البريد الإلكتروني
    ├── verify-success.html             # نجاح التحقق
    ├── onboarding/
    │   ├── company-setup.html          # إعداد بيانات المنشأة
    │   └── scope-wizard.html           # معالج نطاق الامتثال والتصنيف
    ├── company/
    │   ├── dashboard.html              # لوحة تحكم الشركة (نظرة عامة، ضوابط، أدلة، فجوات، مخاطر، تقارير)
    │   └── rfi.html                    # الرد على طلبات المعلومات
    ├── auditor/
    │   └── portal.html                 # بوابة المدقق (مراجعة الضوابط، الأحكام، RFI)
    └── admin/
        └── platform.html              # لوحة Platform Admin (شركات، مدققين، مدفوعات، تعيينات)
```

---

## الرحلات المدعومة

### رحلة الشركة
`Landing → Register → Verify → Company Setup → Scope Wizard → Dashboard → Controls → Evidence → Gaps → Risks → RFI Response → Readiness Report`

### رحلة المدقق
`Auditor Portal → Assigned Companies → Control Review → Evidence Review → AI Advisory → Verdict / RFI → Assessment Completion`

### رحلة الإدارة
`Admin Login → Platform Dashboard → Company Management → Payment Approval → Auditor Management → Auditor Assignment → Review Monitoring → Reports`

---

## التقنيات

| التقنية | الإصدار | الغرض |
|---------|---------|-------|
| [Alpine.js](https://alpinejs.dev/) | v3.x | التفاعلية والحالة |
| [Tailwind CSS](https://tailwindcss.com/) | v3.x | التصميم والأنماط |
| IBM Plex Sans Arabic | — | الخط العربي |

---

## البناء والتطوير

```bash
# تثبيت الاعتماديات
npm install

# بناء CSS للإنتاج
npx tailwindcss -i ./assets/css/input.css -o ./assets/css/style.css --minify

# وضع المراقبة أثناء التطوير
npx tailwindcss -i ./assets/css/input.css -o ./assets/css/style.css --watch
```

---

## الربط بالباكند

المشروع مستقل تمامًا ومصمم للربط لاحقًا. نقاط الربط:

- **API calls**: استبدل بيانات Alpine.js الوهمية في `app.js` بطلبات `fetch()` للـ API
- **Auth**: صفحات تسجيل الدخول والتسجيل جاهزة لإضافة JWT/Session
- **Forms**: جميع النماذج تحتوي على `@submit.prevent` جاهزة لإرسال البيانات
- **Django backend**: المشروع الرئيسي في مجلد الجذر يستخدم Django

---

## ملاحظات التصميم

- اللغة العربية RTL بالكامل
- نظام الألوان: أخضر `#0c6b55` + ذهبي `#c69b5a` + حبر `#102c2d`
- الخط: IBM Plex Sans Arabic
- متجاوب مع الشاشات الصغيرة

---

تطوير بواسطة [شركة احصل الحل](https://gscompany.sa/) — © 2026 1SaudiCyber
