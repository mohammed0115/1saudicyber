# Official Control Library — Status

**Status:** Complete (official set, except OTCC/DCC) · Verified against `compliance/data/official_controls/*.yaml`.

## Source of truth
- **Official YAML datasets** in `compliance/data/official_controls/`, loaded read-only by
  `compliance/official_dataset.py`, registered to **`FrameworkVersion`** + **`SourceDocument`**
  records, are the **new source of truth**.
- The **legacy 334-control Excel** (`LEGACY-334-CONTROLS` framework version) is a **bridge only**
  and is **NOT the source of truth**. Reporting, the control plan, evidence planning, and
  assessments all exclude legacy controls (`is_legacy_import=True`).

## Official controls applied (417 total)
| Framework version | Code | Controls |
|---|---|---:|
| Aramco SACS-002 | `ARAMCO-SACS-002` | 92 |
| SABIC CyberTrust v1.0 | `SABIC-CYBERTRUST-1-0` | 94 |
| NCA ECC 2-2024 | `NCA-ECC-2-2024` | 108 |
| NCA CSCC 1-2019 | `NCA-CSCC-1-2019` | 32 |
| NCA OSMACC 1-2021 | `NCA-OSMACC-1-2021` | 15 |
| NCA TCC 1-2021 | `NCA-TCC-1-2021` | 21 |
| NCA CCC 2-2024 | `NCA-CCC-2-2024` | 55 |
| **Total official** | | **417** |

(Counts verified by control-id entries in each YAML file.)

## Legacy controls
- **334 legacy controls** — bridge/bootstrap only (`LEGACY-334-CONTROLS`).
- **Not** an official authority; never used as a report/assessment source of truth.

## Total controls
- **751** = 417 official + 334 legacy.

## OTCC (NCA-OTCC-1-2022)
- **Status:** Manual review workspace only — `compliance/data/official_controls/manual_review/nca_otcc_1_2022_review.json`.
- **47 main-control slots** awaiting curated official statements.
- **Not** part of the official dataset; **not applied**; not counted in the 417.

## DCC (NCA-DCC-1-2022)
- **Status:** Blocked.
- Requires an official text source **or** a separately approved OCR-reviewed control list before it
  can be curated into an official YAML dataset.
- Review workspace placeholder exists (`nca_dcc_1_2022_review.json`); no controls applied.

## Explicit statements
- The Excel 334 dataset is **not** the official source of truth.
- Official YAML datasets + `FrameworkVersion`/`SourceDocument` records **are** the source of truth.
- No OTCC/DCC controls are imported or applied in this MVP.
