# CyberTrust KSA — سلسلة برومبتات إصلاح المشروع الحالي

هذه الحزمة مخصصة لإصلاح مشروع Django الحالي، وليست لإعادة بنائه من الصفر.

## المراجع التي بنيت عليها السلسلة

1. Software Requirements Specification (SRS) — CyberTrust KSA AI-Powered Continuous Cybersecurity Compliance Platform.
2. CyberTrust KSA Developer Prototype v3.2.
3. Third Party Cybersecurity Compliance Report Template — Aramco/SACS-002.
4. المعمارية المتفق عليها: Rules First → AI Second → Auditor Final.

## طريقة الاستخدام

- استخدم برومبت واحد فقط في كل مرة مع Claude/Codex/Copilot.
- بعد كل برومبت اطلب منه: migrations + tests + implementation report.
- لا تنتقل للبرومبت التالي إلا بعد نجاح `python manage.py check` ونجاح الاختبارات المتاحة.
- لا تسمح للأداة بحذف المشروع أو إعادة بنائه من الصفر.

## ترتيب التنفيذ المختصر

Foundation:
01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10

Engines + Reports:
11 → 12 → 13

Dashboards + Monitoring + Security + API Gate:
14 → 15 → 16 → 17 → 18

## القاعدة الذهبية

```text
Rules First → AI Second → Auditor Final
```

يعني:
- الـ Controls والـ Rules هي أساس النظام.
- الذكاء الاصطناعي يحلل ويقترح فقط.
- Rule Engine يعطي حكم النظام.
- المدقق يعطي الحكم النهائي.
