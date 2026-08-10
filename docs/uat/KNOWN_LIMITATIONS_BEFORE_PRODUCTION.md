# 1SaudiCyber — Known Limitations Before Production

> Honest scope statement for UAT/demo. These are **known** and intentional for this stage.

## Not implemented (by design, this stage)
- **Real payment gateway** — subscription activation is manual/admin only (no Moyasar/Stripe/Tap).
- **Production server / domain / HTTPS** — not configured in this phase (local/Docker UAT only).
- **Production monitoring / backups / logging** — not configured in this phase.
- **OTCC / DCC** — not officially applied (manual-review workspace / blocked; backlog).
- **Subcontrol hierarchy** — not implemented.
- **Heavy OCR** for PDFs/images — not implemented (advisory analysis is text-based).
- **External auditor public share links** — not implemented (external sharing is manual/off-platform).
- **Auditor marketplace pricing / bidding / payouts** — not implemented.
- **Chat / messaging** between company and auditor — not implemented.

## Intentional product rules (not limitations, but worth stating)
- AI analysis is **advisory only**; it never decides compliance.
- `ControlAssessment` is **auditor/staff-driven**; assigned auditors are read-only.
- Reports/exports and platform-auditor assignment require an **active subscription**.
- Official control library = **417** controls; legacy 334 is a non-authoritative bridge.

## Internal naming
- Public brand/domain: **1SaudiCyber / cyber-5.com**.
- Internal Django package remains `cybertrust_ksa` (technical-only; intentionally unchanged).
