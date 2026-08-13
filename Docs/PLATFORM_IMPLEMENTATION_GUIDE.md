# CyberTrust KSA Platform Foundation — `manus` Branch

## Purpose

This branch converts the application from a dashboard-centred compliance product into an **API-first platform foundation**. It does not claim production integrations, autonomous compliance decisions, or a sovereign deployment. It establishes the versioned data contracts, tenant boundaries, review controls, testable connector lifecycle, and operational interfaces required before those claims can be made.

> The SaaS company, auditor, and administration screens remain application clients. The new platform APIs are the reusable technical core that those clients and future partner applications can consume.

## Implemented Platform Surfaces

| Surface | Implemented component | Boundary and safety control |
|---|---|---|
| Policy and common controls | `policy_engine` provides policy packs, versions, deterministic applicability evaluation, canonical controls, versioned coverage mappings, and replayable evaluation records. | Only approved and effective policy versions can be evaluated. Every result contains the policy hash, version, matched rules, and decision hash. |
| Tenant isolation | `api.permissions` scopes controls, evidence, tests, events, and recommendations to the authenticated company. | A cross-tenant resource identifier returns a denial or not-found result; evidence upload is limited to a company’s applicable controls. |
| Connector lifecycle | `integrations` provides providers, tenant connections, vault credential references, connector events, and a deterministic `mock` driver. | Raw secrets in request configuration are rejected. Only an external credential reference is persisted. No production provider driver is claimed or enabled. |
| Automated control testing | Versioned definitions schedule control tests from 15 minutes to 24 hours and produce per-control immutable evidence metadata. | Outcomes distinguish `pass`, `fail`, `warning`, and `error`. A provider/API failure is not represented as non-compliance. |
| Events and remediation | `platform_events` provides a durable event outbox, HTTPS webhook subscriptions, delivery records, and reviewable status recommendations. | A failed control test creates an alert and a **pending** recommendation. A human reviewer must accept a recommendation before `CompanyControl.status` changes. |
| Evidence intelligence | `ai_engine.governance` creates cited evidence chunks, validates decision outputs, and records model/prompt/policy/evidence lineage. | Low-confidence or invalid model output is marked `review_required`; the legacy analysis record no longer duplicates raw extracted evidence text. |
| Operations and developer experience | Correlation-ID middleware, response timing headers, a health endpoint, a capability endpoint, and an OpenAPI contract. | The health endpoint is low-disclosure. Outbound webhooks require HTTPS and an externally resolved signing secret. |

## Local Setup

Install the declared dependencies, then apply the migration set and seed only the safe local test provider.

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_all_controls
python manage.py seed_platform_catalog
python manage.py test
python manage.py runserver
```

The platform contract is available at `Docs/openapi/platform-v1.yaml`. The health check is at `GET /api/v1/health/`; authenticated consumers can discover platform features at `GET /api/v1/platform/capabilities/`.

## Operational Workflow Demonstrated by the Foundation

A company administrator creates a connection using a provider key, a non-secret configuration, and an external credential reference. The connection can be tested. The administrator then creates a control-test definition mapped only to controls applicable to that company, and either triggers the test manually or relies on its future scheduler integration.

A completed test writes immutable test results and evidence hashes. A failed test emits a durable `control.test.completed` event, raises a high-severity alert, and creates a pending control-status recommendation. An authorised compliance reviewer may accept or reject that recommendation through the platform API. This is intentional: automated technical evidence can inform a compliance state but does not silently create an unreviewed audit conclusion.

## External Infrastructure Required Before Production Activation

| Requirement | Why it is required | Production implementation expectation |
|---|---|---|
| PostgreSQL and managed object storage | SQLite and local media are unsuitable for production concurrency, durability, and evidence retention. | Use managed PostgreSQL, encrypted object storage, tested backup/restore, and explicit retention policies. |
| Redis/Celery workers and scheduler | Scheduled tests, evidence processing, event retries, and report generation require durable background work. | Run separate worker/beat processes with observability, dead-letter handling, autoscaling, and deployment health checks. |
| External secrets manager/KMS | Connector credentials and webhook signing secrets must never be stored in JSON fields, logs, or source code. | Replace development environment-variable secret resolution with a reviewed KMS/vault adapter and rotation policy. |
| OAuth2/OIDC service identity | JWT user authentication is not a complete partner-machine authentication model. | Add OAuth2 client credentials, scopes, key rotation, client lifecycle, quotas, and audit trails at an API gateway. |
| Provider driver packages | Only the deterministic `mock` driver is intentionally implemented. | Implement and security-review each Azure, AWS, Microsoft 365, SIEM, EDR, or scanner driver independently, using least privilege and acceptance tests. |
| HTTPS webhook delivery worker | Subscriptions and signing contracts are stored, but production delivery needs a retrying worker and outbound policy. | Use an allow-listed egress path, HMAC secret resolver, timeout/retry/backoff, idempotency, delivery observability, and dead-letter workflow. |
| AI evaluation and approved model routing | The governance schema is implemented; production model behaviour must be measured. | Create Arabic/English golden datasets, evaluation gates, human-review operations, model routing rules, cost controls, and drift monitoring. |
| SSO/SCIM and hardened tenancy | Basic user roles and tenant checks are insufficient for enterprise partner deployment. | Implement enterprise identity federation, service principals, ABAC/RLS or stronger isolation, external security testing, and incident procedures. |

## Explicit Non-Claims

The branch deliberately does **not** claim 200+ integrations, live access to Azure/AWS/Microsoft 365/SIEM/EDR systems, encrypted secret storage in the Django database, production OAuth2 client credentials, a complete vector database/RAG service, automatic final audit decisions, or an active webhook-hosting service. These require external infrastructure, tenant-specific configuration, provider approvals, and production validation.

## Recommended Next Engineering Milestones

The next implementation increment should replace the mock connector with one narrow, approved production connector and add a vault adapter plus a queue worker. It should be demonstrated against a design partner’s non-production environment with end-to-end test evidence, tenant isolation tests, documented scopes, and rollback controls. In parallel, the policy library should be populated with source-controlled framework versions and expert-approved canonical mappings rather than relying on seed data alone.
