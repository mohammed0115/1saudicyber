# Prompt 18 — API Contract, Tests & Final Repair Gate

Create or repair API contracts and final test gate.

Required API endpoints from SRS:
- POST /api/v1/register/
- POST /api/v1/login/
- POST /api/v1/classify/
- GET /api/v1/controls/
- GET /api/v1/controls/{id}/
- POST /api/v1/evidence/upload/
- POST /api/v1/evidence/{id}/analyze/
- GET /api/v1/gap-analysis/
- GET /api/v1/dashboard/executive/
- GET /api/v1/dashboard/compliance/
- GET /api/v1/monitoring/scores/
- GET /api/v1/monitoring/alerts/
- POST /api/v1/reports/generate/
- GET /api/v1/auditor/assignments/
- POST /api/v1/auditor/review/{id}/

Add:
- OpenAPI/Swagger documentation.
- API serializers.
- Standard error response format.
- Authentication/authorization checks.
- Pagination/filtering for controls/evidence/alerts.
- Tests for all endpoints.

Final E2E flows:
1. Register company.
2. Classify company.
3. Generate applicable controls.
4. Upload evidence.
5. OCR/extract text.
6. AI analysis.
7. Rule Engine status.
8. Gap analysis.
9. Auditor review and override.
10. Generate NCA report.
11. Generate Aramco/SACS report.
12. Monitoring alert generated.

Acceptance criteria:
- python manage.py check passes.
- migrations pass.
- test suite passes.
- E2E scenario documented with screenshots or logs.
- FINAL_REPAIR_REPORT.md generated.
