# Scenario B — Subscription Gate (UAT)

> **UAT only — do not use in production.** No payment gateway is involved; activation is manual.

**Goal:** Confirm report viewing/exports and platform-auditor assignment are gated by an active subscription.

## B1 — Without an active subscription
| # | Step | Expected |
|---|------|----------|
| 1 | As the company user, open `/compliance/reports/` | Reports index loads with a "يتطلب ... تفعيل الاشتراك" notice |
| 2 | Open Executive Summary / Gap Analysis / Evidence Matrix | **Subscription-required** page ("تفعيل الاشتراك مطلوب") — not the full report |
| 3 | Request CSV export `/compliance/reports/evidence-matrix.csv` | **No CSV file** — subscription-required page is shown instead |
| 4 | Request XLSX export | **No XLSX file** — subscription-required page |
| 5 | Open `/auditors/` (assign) | Subscription-required page (assignment also gated) |
| 6 | Workflow stepper (dashboard) | "التقارير" / "تنزيل أو إسناد" stages shown **مقفل** ("يتطلب اشتراكًا فعالًا") |

## B2 — Activate the subscription (manual / admin)
```bash
python manage.py activate_company_subscription --company-id <id> --plan-name "UAT Plan" --days 30
# or, via Django admin: Billing → Company subscriptions → set status=active, ends_at in the future
```

## B3 — With an active subscription
| # | Step | Expected |
|---|------|----------|
| 1 | Reload `/compliance/reports/` | "التقارير مفعّلة" + two options (external download / platform auditor) |
| 2 | Open Executive Summary / Gap / Matrix | Full report renders (read-only) |
| 3 | CSV export | CSV downloads (`Content-Type: text/csv`, contains `control_id`) |
| 4 | XLSX export | XLSX downloads (starts with `PK`) |
| 5 | Dashboard stepper | "التقارير" stage no longer **مقفل** |

**Pass criteria:** report calculations are unchanged by subscription; unreviewed controls are never
counted as compliant; gating affects access only, not the numbers.
