# Prompt 11 — Risk, Gap Analysis & Remediation Repair

Repair Gap Analysis, Risk Engine, and Remediation Roadmap according to SRS FR-007.

The system must:
1. Calculate compliance score per framework.
2. Calculate score per domain.
3. Identify non-compliant and partially compliant controls.
4. Prioritize gaps by:
   - control criticality
   - mandatory flag
   - remediation effort
   - audit probability
5. Generate risk score 0-100.
6. Estimate audit failure probability.
7. Generate remediation roadmap.
8. Track gap closure.

Create:
- Gap
- RiskRegister
- RemediationTask
- RiskScoringService
- RemediationRoadmapService

Risk fields:
- likelihood 1-5
- impact 1-5
- score
- level: High/Medium/Low
- treatment: Mitigate/Accept/Transfer/Avoid
- owner
- target date

Roadmap buckets:
- Immediate: 0-30 days
- Short-Term: 31-90 days
- Medium-Term: 91-180 days
- Long-Term: 181+ days

Acceptance criteria:
- Gaps are generated from AssessmentControlResult.
- Risk register is created automatically.
- Remediation tasks have owner/status/date.
- Dashboard can display gap and risk summary.
- Tests cover score and roadmap generation.
