# 1SaudiCyber — Production Go-Live Runbook

خطوات إطلاق الإنتاج بالترتيب. كل الأوامر تُنفَّذ على خادم/بنية الإنتاج (داخل المملكة — PDPL).
الكود جاهز؛ هذه الوثيقة تنقلك من "جاهز" إلى "مُطلَق".

> **مبدأ:** لا تُطلِق قبل اجتياز **المرحلة 5 (التحقق)** كاملةً.

---

## المرحلة 0 — المتطلّبات (بنية تحتية داخل المملكة)
- خادم/حاوية (Docker) — منطقة سعودية (Aramco/STC Cloud / me-central-1) لسيادة البيانات.
- PostgreSQL 16 مُدار أو حاوية · Redis 7 · تخزين S3-متوافق داخل المملكة (اختياري لكن مُوصى للتوسّع).
- نطاق + شهادة TLS (خلف عاكس TLS مثل nginx / load balancer).
- حساب SMTP (بريد المعاملات) · حساب Sentry · حساب Moyasar (للدفع الحيّ).

## المرحلة 1 — التهيئة (env)
```bash
cp deployment/docker/env.example .env
```
عبّئ **كل** القيم الإلزامية في `.env` (راجع الملف — كلها موثّقة):
- `DJANGO_SECRET_KEY` (عشوائي ≥50 حرفًا) · `DEBUG=False` · `ALLOWED_HOSTS` · `CSRF_TRUSTED_ORIGINS`
- `POSTGRES_*` (يبدّل تلقائيًا من SQLite إلى Postgres)
- `REDIS_URL` + `CELERY_BROKER_URL` · `EVIDENCE_ASYNC_ENABLED=True`
- `EMAIL_BACKEND=...smtp...` + `EMAIL_HOST/USER/PASSWORD` + `DEFAULT_FROM_EMAIL`
- `SENTRY_DSN` · `LOG_LEVEL=INFO`
- الأمن: `ENFORCE_ADMIN_MFA=True` · `SESSION_COOKIE_AGE=43200`
- (اختياري) `AWS_STORAGE_BUCKET_NAME` + `AWS_S3_REGION_NAME=me-central-1` + مفاتيح S3
- **الدفع الحيّ:** `MOYASAR_MODE=live` + `MOYASAR_PUBLISHABLE_KEY=pk_live_...` + `MOYASAR_SECRET_KEY` + `MOYASAR_WEBHOOK_SECRET`

## المرحلة 2 — البناء والتشغيل
```bash
docker compose build
docker compose up -d          # يشغّل: db · redis · web · worker · beat
docker compose ps             # تأكّد أن الكل healthy
```
> `worker` يعالج OCR/AI/PDF خارج الطلب · `beat` يشغّل المهام المجدولة.

## المرحلة 3 — قاعدة البيانات والملفات
داخل الحاوية أو عبر entrypoint (يتم تلقائيًا في الصورة):
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py create_admin   # مستخدم إداري أولي (ENV)
```
> تشمل الهجرات: الفهارس المركّبة · findings/CAPA · CompanyMessage · UserInvite · قيد المبلغ.

## المرحلة 4 — عاكس nginx (TLS + حماية الأدلة)
- وجّه `/static/` إلى `staticfiles`.
- **احجب `/media/evidence*` عن العموم** (داخلي فقط) — التطبيق يقدّم تنزيلًا مُصادَقًا عبر `download_evidence_file`. مثال X-Accel-Redirect موصى.
- أعِد التوجيه إلى HTTPS (التطبيق يفعّل HSTS/SSL redirect تلقائيًا عند `DEBUG=False`).

## المرحلة 5 — التحقّق (بوابة الإطلاق — لا تتخطّها)
```bash
docker compose exec web python manage.py check --deploy      # يجب: 0 issues
docker compose exec web python manage.py makemigrations --check --dry-run   # No changes
curl -f https://<domain>/healthz/                            # {"status":"ok"}
```
يدويًا:
- [ ] تسجيل شركة جديدة + تحقّق بريد (SMTP يعمل).
- [ ] **دفعة Moyasar حيّة حقيقية** (مبلغ صغير) → تأكّد التفعيل بعد التحقّق الخادمي + وصول الويبهوك.
- [ ] دخول إداري → يُطلب MFA (لأن `ENFORCE_ADMIN_MFA=True`) → إتمام الإعداد.
- [ ] رفع دليل → يُعالَج عبر `worker` (لا يحجب الطلب).
- [ ] ظهور خطأ متعمّد في Sentry.

## المرحلة 6 — الجدولة (cron)
```cron
0 2 * * *  docker compose exec -T web python manage.py backup_db --keep-days 14
0 6 * * *  docker compose exec -T web python manage.py send_audit_reminders --days 3
0 * * * *  docker compose exec -T web python manage.py purge_expired_data   # PDPL retention
```

## المرحلة 7 — قبل البيع المؤسسي/الحكومي (مصداقية)
- [ ] **اختبار اختراق طرف‑ثالث** + معالجة النتائج (لا يكفي التقييم الذاتي).
- [ ] حزمة **تقييم ذاتي NCA ECC** (أدلة الضوابط) للعرض على العميل.
- [ ] تأكيد **الاستضافة داخل المملكة** + سياسة الاحتفاظ/الحذف (PDPL).
- [ ] نسخ احتياطي مُختبَر الاستعادة (استعادة تجريبية فعلية).

---

### تحصين إضافي مُوصى (بعد الإطلاق)
- تشفير `mfa_secret` at-rest (مكتبة تشفير حقول) — يحتاج هجرة.
- CSP: إزالة `script-src 'unsafe-inline'` عبر nonce (يتطلب نقل السكربتات المضمّنة).
- pgbouncer/pooler لقواعد بيانات عالية الحمل.

## 🔐 تدوير الأسرار (إلزامي قبل الإطلاق — CRITICAL)

الأسرار الحيّة تعيش فقط في `.env` (مُستبعد من git) أو في مدير أسرار. قبل الإطلاق:

1. **دوّر كل مفتاح** ظهر يومًا في `.env` على القرص أو في نسخة احتياطية أو ملف مشترك: `OPENAI_API_KEY` · `EMAIL_HOST_PASSWORD` · `DJANGO_SECRET_KEY` · مفاتيح Moyasar.
2. انقل الأسرار من `.env` إلى **AWS Secrets Manager / Vault**، ولا تُبقِ نسخة نصّية على القرص.
3. تأكّد أن نسخ قاعدة البيانات/الملفات الاحتياطية **لا تحتوي** أي `.env`.
4. فعّل `ENFORCE_ADMIN_MFA=True` و`EVIDENCE_ASYNC_ENABLED=True` في الإنتاج (موجودة في `deployment/docker/env.example`).

*كل ما سبق مدعوم بالكود الحالي؛ هذه الوثيقة هي مسار التنفيذ على بنيتك الحقيقية.*
