# COMMANDS_RUN

Date: 2026-06-09. All commands run from the repo root with the project venv.

## Environment setup
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt openpyxl pdfplumber   # openpyxl now in requirements.txt
```
> `python` was not on PATH; `python3` (3.12.3) was used. Django/openpyxl/python-docx were not
> previously installed system-wide — a venv was required to run anything.

## Source-document extraction (verification step 1)
```bash
pdftotext -layout Docs/SRS/CyberTrust_KSA_SRS.pdf /tmp/extract/SRS.txt
pdftotext -layout Docs/SRS/CyberTrust_KSA_Developer_Prototype_v3.2.pdf /tmp/extract/PROTO.txt  # image-only PDF
.venv/bin/python extract_docx.py   # third-party-cybersecurity-compliance-report-template.docx
.venv/bin/python extract_xlsx.py   # Consolidated_Compliance_Rules_v2, Evidence_Matrix, RTM_v3
```

## Django checks (steps 4)
```bash
.venv/bin/python manage.py check
#   1 WARNING: staticfiles.W004 (no static/ dir) — cosmetic. Otherwise clean.

.venv/bin/python manage.py makemigrations --check --dry-run
#   "No changes detected"  — no model changes, no new migrations needed.

.venv/bin/python manage.py migrate
#   "No migrations to apply."  — schema already current.

.venv/bin/python manage.py test
#   Ran 28 tests ... OK   (baseline was 17)
```

## Verification queries
```bash
.venv/bin/python manage.py shell -c "<count controls per framework>"
#   NCA_ECC: 148 | ARAMCO_SACS002: 92 | SABIC_CT: 94 | TOTAL: 334
```

## Exit status
- `check`: OK (1 cosmetic warning)
- `makemigrations --check`: OK (no changes)
- `migrate`: OK
- `test`: OK (28/28)
