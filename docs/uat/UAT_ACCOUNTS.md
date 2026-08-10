# 1SaudiCyber — UAT Sample Accounts

> **UAT only — do not use in production.** No real passwords or secrets are committed.
> Passwords are provided at runtime via the `UAT_DEMO_PASSWORD` environment variable; if unset,
> the seed command uses a clearly-temporary LOCAL-ONLY placeholder and prints a warning.

## Accounts created by the seed command
| Role | Email | Password source | Notes |
|------|-------|-----------------|-------|
| Company user | `client@cyber-5.local` | `UAT_DEMO_PASSWORD` (or local-only default) | role `company_admin`, linked to the sample company |
| Staff/admin | `admin@cyber-5.local` | `UAT_DEMO_PASSWORD` (or local-only default) | `is_staff=True` (staff-only actions); not a superuser |
| Auditor | `auditor@cyber-5.local` | `UAT_DEMO_PASSWORD` (or local-only default) | role `auditor` + active `AuditorProfile` |

## Setting the demo password (recommended)
```bash
export UAT_DEMO_PASSWORD='choose-a-temporary-local-uat-password'
python manage.py seed_uat_demo_data --apply --subscribe
```
If `UAT_DEMO_PASSWORD` is not set, the command still works in `--apply` mode using a documented
LOCAL-ONLY placeholder and prints a warning — never use that placeholder outside local UAT.

## Superuser (for Django admin / auditor activation)
Create manually (interactive, never committed):
```bash
python manage.py createsuperuser
```
Use the superuser to open Django admin and, if needed, set an `AuditorProfile` status to **active**
or run `activate_company_subscription`.

## Security notes
- These are local UAT identities only; rotate/remove before any shared or production environment.
- No account here grants cross-company access; tenant isolation is enforced by the app.
