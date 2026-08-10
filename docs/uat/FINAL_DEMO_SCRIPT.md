# 1SaudiCyber — Final Demo Script (~15–20 min)

> **UAT only — do not use in production.**

## 0. Setup (before the demo)
```bash
# App
python manage.py runserver 0.0.0.0:9999     # or Docker per the runbook
# Optional sample data + active subscription
export UAT_DEMO_PASSWORD='temporary-local-uat-password'
python manage.py seed_uat_demo_data --apply --subscribe
# Superuser for admin (auditor activation)
python manage.py createsuperuser
```

## 1. Brand & landing (2 min)
- Open `/` — Arabic-first, RTL, **1SaudiCyber** brand, footer shows **cyber-5.com**.
- Highlight honest content: **417 official controls** (NCA ECC 108, Aramco 92, SABIC 94); "جاهزية الامتثال" (no certification-granting claims).

## 2. Company self-service journey (6 min)
- `/get-started/` → "إنشاء حساب شركة" → register **Najd Digital Solutions** via the 3-step stepper.
- Onboarding → Journey Dashboard → show the **Workflow Stepper** (13 grouped stages + next action).
- Intake → framework review → approve (staff) → control plan → evidence checklist → upload evidence.
- Trigger advisory analysis; emphasize it is **advisory only** ("لا يُعد قرارًا نهائيًا").

## 3. Subscription gate (3 min)
- As an unsubscribed company: reports/exports show the **subscription-required** page; stepper shows reports **locked**.
- Activate: `activate_company_subscription --company-id <id> --plan-name "UAT Plan" --days 30`.
- Reload: reports unlock; export CSV/XLSX; show the two options (external download / platform auditor).

## 4. Auditor assignment (4 min)
- Register an auditor → status `pending_review` → activate in admin.
- Company assigns its file → auditor accepts → auditor sees **read-only** company context.
- Show isolation: auditor cannot open another company's assignment; cannot change assessments.

## 5. Security & honesty (2 min)
- Anonymous protected page → redirect to login.
- Non-staff cannot run staff-only actions; unsubscribed cannot export.
- AI never sets compliance. Close with `KNOWN_LIMITATIONS_BEFORE_PRODUCTION.md`.

## Talking points
- Read-only reporting and dashboard; auditor is the only decision-maker.
- Tenant isolation enforced everywhere.
- Internal package remains `cybertrust_ksa`; public brand is **1SaudiCyber / cyber-5.com**.
