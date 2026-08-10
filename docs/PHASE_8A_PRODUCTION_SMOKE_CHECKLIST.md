# Phase 8A — Production Smoke Checklist

> PLANNING ONLY. To be executed by the deployer AFTER a future approved deploy. Not run in this phase.
> Domain `https://cyber-5.com`; health endpoint `/healthz/`.

## A. Public / unauthenticated (curl + browser)
```
[ ] GET /                          → 200
[ ] GET /healthz/                  → 200 {"status":"ok"}
[ ] GET /login/                    → 200 (Arabic RTL, language switcher visible)
[ ] GET /dashboard/                → 302 redirect to /login (anonymous)
[ ] GET /compliance/classification/ → 302 to /login (protected)
[ ] GET /compliance/applicability/  → 302 to /login (protected)
[ ] GET /compliance/reports/auditor-reviewed/ → 302 to /login (protected)
[ ] HTTPS valid (cert OK); HTTP→HTTPS redirect intact
```

## B. Authenticated — company user (own data only)
```
[ ] login succeeds (Arabic UI, RTL)
[ ] /dashboard/ loads
[ ] /compliance/dashboard/ (journey) loads; wizard renders
        # NOTE: /compliance/dashboard/ is the journey dashboard route. There is no /compliance/journey/ URL.
[ ] /compliance/classification/ loads (advisory wording present)
[ ] /compliance/applicability/ loads
[ ] evidence submission detail loads for OWN company submission
[ ]   extraction / ai-analysis / rule-evaluation / auditor-verdict pages load (own submission)
[ ] /compliance/reports/ loads
[ ] /compliance/reports/auditor-reviewed/ → report renders OR subscription gate shows
[ ] /monitoring/continuous/ loads or redirects appropriately
```

## C. Wording / safety (visual)
```
[ ] NO "334" shown as the current official total (417 is the official total)
[ ] NO official certification / accreditation claim
[ ] NO "معتمد من NCA/أرامكو/سابك", "شهادة رسمية" as a positive claim
[ ] required negation disclaimers present on verdict + auditor-reviewed report pages
[ ] AI analysis labelled advisory; Rule Engine labelled suggested ("بانتظار مراجعة المدقق")
[ ] English mode renders (switch language; core pages OK)
```

## D. Staff / auditor + isolation
```
[ ] staff/superuser can open an auditor-verdict page and submit a verdict
[ ] company user CANNOT submit a verdict (view-only message)
[ ] cross-company: company A user cannot open company B submission pages (redirect)
[ ] run-* endpoints reject GET (405) / require POST + session
```

## E. Operational
```
[ ] docker compose ps → web + db healthy
[ ] docker compose logs --tail=200 web → no tracebacks/500s
[ ] static assets load (collectstatic succeeded)
[ ] no secrets in logs
```

**If any C/D item fails → trigger rollback (see PHASE_8A_PRODUCTION_ROLLBACK_PLAN.md).**
