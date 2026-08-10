# DCC (NCA-DCC-1-2022) — Extraction Investigation (Phase 2L, draft only)

**Status: NOT a registered dataset.** No DCC entry exists in `DATASET_FILES`. No apply, no dry-run.
Source: `Docs/SRS/NCA/Data-Cybersecurity-Controls-.pdf` (official). Excel 334 NOT used.

## Findings

- **The control pages are image-based (scanned), not selectable text.** Across 28 pages, only
  ~5 KB of text extracts (~180 chars/page) — and that text is **only** cover/header/footer matter
  (`Document Classification: Public`, `Sharing Indicator: White`, the Arabic disclaimer, the title
  `Data Cybersecurity Controls (DCC-1:2022)`). No control body text comes out.
- **No control-id pattern is recoverable**: zero `x-x-x`, zero `x-x-P/T-x`, zero `DC-` matches in
  either `-raw` or `-layout`.
- **No announced "N Main Controls" line** is extractable (it would live on an image page).

## Conclusion

DCC **cannot** be parsed from this PDF without heavy OCR, which is explicitly forbidden this phase.
Its official count, numbering scheme, and main/subcontrol structure **cannot be determined** from
the available text layer. This matches the Phase 2I "lowest confidence" assessment and triggers the
Phase 2L stop condition ("DCC official count or numbering cannot be determined").

## Recommended approach (for a later phase)

- Obtain a **text-based** official DCC PDF/Word from NCA (preferred), OR
- Run a controlled, reviewed OCR pass (out of scope here; would need explicit approval), OR
- **Manual curated YAML** transcribed by reading the PDF visually.
- Until then, DCC stays unregistered. Do NOT fall back to the legacy 334 Excel.
