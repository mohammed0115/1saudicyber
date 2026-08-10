# 1SaudiCyber — Sample Evidence Files (UAT)

> **UAT only — do not use in production.** Do not commit large binaries, real documents, or
> private/media uploads. Text-only samples are provided under `docs/uat/sample_evidence_text/`.

## Suggested evidence set (per the sample company)
Upload these (as PDF/DOCX/TXT) against the relevant checklist items during UAT:
- `information_security_policy.pdf`
- `access_control_procedure.pdf`
- `incident_response_plan.pdf`
- `cloud_security_controls.pdf`
- `remote_work_policy.pdf`

## What is committed
Small **.txt** source content for each item lives in `docs/uat/sample_evidence_text/`. Use it to:
- paste into a quick `.txt`/`.docx`/`.pdf` you generate locally, then upload via Evidence Upload v2; or
- upload the `.txt` directly (Upload v2 accepts `txt` among its allowed extensions).

## Upload rules (enforced by the app)
- Allowed extensions: `pdf, png, jpg, jpeg, xlsx, docx, csv, txt`.
- Max size: 50 MB (server-validated).
- Each submission records a SHA-256 checksum and a version; no AI/OCR runs on upload.

## Do NOT commit
- Real or large PDF/binary evidence.
- Any user/private uploads or runtime `media/` files (git-ignored).
