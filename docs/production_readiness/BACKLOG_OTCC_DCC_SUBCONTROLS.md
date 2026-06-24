# Backlog — OTCC, DCC, and Subcontrol Hierarchy

**Status:** Backlog (not blockers for the MVP workflow).

## OTCC (NCA-OTCC-1-2022) — current status
- **Manual review workspace only**: `compliance/data/official_controls/manual_review/nca_otcc_1_2022_review.json`.
- **47 main-control slots** awaiting curated official statements.
- Not part of the official dataset, **not applied**, not in the 417 official count.

## DCC (NCA-DCC-1-2022) — current status
- **Blocked.** No reliable official text source applied yet (low confidence / no usable raw ids).
- Review placeholder exists; no controls curated or applied.

## Why these are not blockers
- The end-to-end workflow (intake → reports) is fully functional on the **417 applied official
  controls** across 7 frameworks. OTCC/DCC are additional frameworks that can be added later
  without changing the pipeline; nothing in the MVP depends on them.

## What is required to complete OTCC
1. Fill the **47 main control statements** in the manual review file.
2. Approve the review rows.
3. Convert to an **official YAML** dataset (register the `FrameworkVersion`/`SourceDocument`).
4. **Validate** (`validate_official_control_dataset`), dry-run, then **apply** via the official import command.

## What is required to complete DCC
- An **official text source** for the controls, **or** a separately approved **OCR-reviewed** control
  list, followed by the same curate → validate → apply path as OTCC.

## Subcontrol hierarchy (future model)
- Optional `parent_control` relation enabling **level / main-control / subcontrol** structure.
- Would allow nested control numbering and rollups.
- **Not part of the current MVP**; additive and backlog-only. Any such change would be an additive
  model migration, designed separately and not in this documentation phase.
