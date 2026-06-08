# MASTER_EXECUTION_CHECKLIST

## قبل البداية

- [ ] خذ نسخة احتياطية من المشروع الحالي.
- [ ] شغل `python manage.py check`.
- [ ] شغل `python manage.py makemigrations --check`.
- [ ] شغل `python manage.py migrate`.
- [ ] شغل الاختبارات إن وجدت.
- [ ] وثق المشاكل الحالية في CURRENT_SYSTEM_AUDIT.md.

## قواعد التنفيذ

- [ ] لا إعادة بناء من الصفر.
- [ ] لا حذف Feature تعمل حالياً.
- [ ] أي تعديل في Models يجب أن يتبعه migration.
- [ ] أي خدمة جديدة يجب أن يكون لها tests.
- [ ] أي endpoint جديد يجب أن يكون موثقاً.
- [ ] أي قرار AI لا يصبح final status مباشرة.
- [ ] أي بيانات شركة يجب أن تكون معزولة حسب tenant/company.
- [ ] أي رفع ملف يجب أن يمر على file validation.
- [ ] أي إجراء حساس يجب أن يسجل في AuditLog.

## بوابة القبول النهائية

- [ ] تسجيل شركة يعمل.
- [ ] التصنيف يعمل.
- [ ] applicable controls تتولد.
- [ ] رفع evidence يعمل.
- [ ] OCR/extraction يعمل أو fallback واضح.
- [ ] AI analysis مخزن منفصل عن final status.
- [ ] Rule Engine يصدر status.
- [ ] Auditor override يعمل.
- [ ] NCA report يعمل.
- [ ] Aramco/SACS report يعمل.
- [ ] Dashboards scoped by role.
- [ ] Monitoring alerts تعمل.
- [ ] API endpoints تعمل.
- [ ] Security/tenant tests موجودة.
