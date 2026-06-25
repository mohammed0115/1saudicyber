# 1SaudiCyber — UAT Sample Data Guide

> **UAT only — do not use in production.**

## Sample company
| Field | Value |
|------|------|
| Arabic name | شركة نجد للحلول الرقمية |
| English name | Najd Digital Solutions LLC |
| CR Number | 1010123456 |
| VAT Number | 300123456700003 (informational; not stored as a separate field) |
| City | Riyadh |
| Country | Saudi Arabia (SA) |
| Industry | Technology / SaaS / Cybersecurity (`sector=technology`) |
| Size | Medium (50–249) (`size=medium`; ~120 employees) |
| Website | https://example.local |
| Contact | Ahmed Al-Qahtani — ahmed.qahtani@example.local — +966500000001 |

## Sample intake profile (demo signals)
- is_government_entity: **false**
- is_critical_system_operator: **true**
- uses_cloud_services: **true**
- provides_cloud_services: **true**
- handles_sensitive_data: **true**
- handles_personal_data: **true**
- has_ot_environment: **false**
- has_remote_work: **true**
- manages_official_social_media_accounts: **true**
- works_with_aramco: **true**
- works_with_sabic: **true**

## Expected framework applicability (informational)
| Framework | Expected |
|-----------|----------|
| NCA ECC | applicable |
| NCA CSCC | applicable |
| NCA CCC | applicable |
| NCA TCC | applicable |
| NCA OSMACC | applicable |
| Aramco SACS-002 | applicable |
| SABIC | applicable |
| NCA OTCC | unavailable / backlog |
| NCA DCC | blocked / backlog |

> Applicability is computed deterministically by the rule engine from the intake signals; verify the
> on-screen results during UAT rather than asserting exact applicability here.

## Seeding the data
```bash
# Preview only (writes nothing)
python manage.py seed_uat_demo_data --dry-run

# Create the sample company, intake, demo users, active auditor (+ optional subscription)
export UAT_DEMO_PASSWORD='temporary-local-uat-password'
python manage.py seed_uat_demo_data --apply --subscribe
```

## What the seed does NOT do (by design)
- Does **not** import official controls, OTCC, or DCC.
- Does **not** create `CompanyControl`.
- Does **not** fabricate any `ControlAssessment` / compliance decision.
- Does **not** commit or print real secrets.
- Is **idempotent** (safe to re-run).

To exercise framework applicability / control plan / checklist with official controls, seed the
official library separately per `ADMIN_GUIDE.md` (e.g. `seed_framework_versions` + the official
import commands), then drive the workflow from the UI.
