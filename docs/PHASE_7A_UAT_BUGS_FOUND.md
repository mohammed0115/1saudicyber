# Phase 7A — UAT Bugs Found

**Commit tested:** `794fe0f` (+ Phase 7A UAT additions). Local Django test-client UAT.

## Blocking bugs
**No blocking bugs found during Phase 7A local UAT.**

## Non-blocking observations (not defects — design/scope)
| ID | Severity | Area | Description | Expected | Actual | Status | Recommended phase |
|---|---|---|---|---|---|---|---|
| OBS-1 | Low | Reports | Auditor final verdict is not reflected in report numbers. | Verdict could feed reports. | Reports stay subscription-gated and independent of verdict (by design this phase). | Deferred (documented) | Phase 7B — Report Finalization Integration |
| OBS-2 | Low | Monitoring | Continuous monitoring is a foundation; no real external checks/scheduling. | Real periodic checks/connectors. | Foundation routes/models only. | Deferred (documented) | Later monitoring phase |
| OBS-3 | Info | AI provider | No real AI key wired locally. | Optional real provider. | Safe `skipped` state; fake provider used in tests. | By design | Production wiring phase |
| OBS-4 | Info | Browser smoke | No Playwright/LiveServer browser tooling provisioned. | Optional browser smoke. | Test-client UAT used instead. | Deferred | Optional |

None of the above block the local 90% gate; all are explicitly in-scope deferrals.
