# Prompt 08 — Evidence Upload, OCR & File Security Repair

Repair evidence upload and OCR according to SRS FR-005.

Supported files:
- PDF
- PNG/JPG/JPEG/TIFF
- DOCX
- XLSX
- TXT

Constraints:
- Max file size 50 MB.
- Store original file.
- Extract text.
- Store extracted text.
- Track uploader, upload date, file metadata.
- Allow multiple evidence files per control.
- Allow deletion with audit trail.

OCR:
- Use Tesseract.
- Support Arabic and English.
- For PDFs use pdf2image + OCR.
- For DOCX/XLSX extract text directly where possible.
- If OCR fails, allow manual text entry.

Security:
- Validate file extension and MIME type.
- Prevent path traversal.
- Store files per company/assessment securely.
- Add optional virus scanning hook.
- Do not expose raw storage paths in templates/API.

Create/repair:
- Evidence model
- EvidenceTextExtractionResult
- OCR service
- upload API/view
- upload UI
- audit log events

Acceptance criteria:
- Upload works for all supported file types.
- OCR extraction stored.
- Arabic/English text extraction supported or failure handled gracefully.
- Invalid files are rejected.
- Audit trail records upload/delete.
- Tests cover file validation and OCR fallback.
