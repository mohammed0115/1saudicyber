# OTCC (NCA-OTCC-1-2022) — Extraction Investigation (Phase 2L, draft only)

**Status: NOT a registered dataset.** No OTCC entry exists in `DATASET_FILES`. No apply, no dry-run.
Source: `Docs/SRS/NCA/otcc_en.pdf` (official). Excel 334 NOT used.

## Findings

- **Text is extractable** (not image-based): ~1,354 chars/page over 45 pages.
- **Official announced count: 47 Main Controls + 122 Subcontrols.** The 47 main-control ids
  (`x-x-x`) are recoverable cleanly after an Appendices cutoff; the count reconciles.
- **Main controls DO carry real statements** (e.g. `1-1-1` = "With reference to the ECC controls
  1-3-1 and 1-3-2, the organization must document, approve, and implement a customized set of
  cybersecurity policies and procedures for OT/ICS systems or assets.").
- **Subcontrols** use `x-x-x-x` (127 found ≈ 122 declared) and contain most of the detailed
  requirement text.

## Why automated extraction is unreliable today

1. **Narrow two-column layout.** The control id sits in a left column; its statement is in the
   right column and **begins on the line BEFORE the id** (vertical centering).
2. **Hyphenated line breaks** split words across lines (`organi-` / `zation`, `orga-` / `nizational`).
3. **Main statement is visually interleaved with its subcontrols** in the same block (e.g. `1-2-1`'s
   statement is wrapped around `1-2-1-1` / `1-2-1-2`), so a line-order parser cannot separate them.
4. Phase 2K attempts: `pdftotext -raw` → main ids with **empty** statements (30/47); custom
   `-layout` column parser → 41/47 captured with **broken** statements starting mid-sentence.

## Phase 2N extraction attempts (all failed to reach 47 clean statements)

Four methods were tried to auto-curate the 47 main-control statements; none produced reliable text:

| Method | Result |
|--------|--------|
| `pdftotext -raw` | 47 main ids captured, but ~30/47 statements EMPTY (ids sit in a separate left column) |
| `pdftotext -layout` (fixed text column 17) | 47 captured, **4/47 clean** — text broken mid-word / wrong column |
| layout column parser + de-hyphenation + lookahead | 41–47 captured, statements start mid-sentence |
| **pdfplumber** (coordinate-based column split, x0≈106 id vs x0≥138 text) | 47 captured, **21/47 clean** — remainder polluted by page headers/footers, Objective text, and bleed from adjacent controls |

**Root cause confirmed:** for controls WITH subcontrols, the main "umbrella" statement
("In addition to ECC subdomain X, ... must include, at a minimum, the following:") is vertically
separated from its own main id by subcontrol text, and the main id is centered against a subcontrol
line — so neither line-order nor coordinate banding can bind the umbrella statement to the right id
without guessing. Footers/Objective blocks bleed into coordinate bands.

**Phase 2N decision: STOP (per the explicit stop condition "OTCC 47 main controls cannot be curated
cleanly").** No OTCC dataset was built, registered, validated, dry-run, or applied. A polluted
dataset (26/47 wrong statements) would violate "no guessing / every statement must be clean and
traceable".

## Recommended approach (for Phase 2M)

- **Column-aware extraction**: use `pdftotext -layout` plus a geometry-based split (fixed left
  column width for ids vs right column for text), OR `pdftotext -x/-y/-W/-H` per region, then a
  de-hyphenation pass. Validate that all 47 statements are complete and start with a capital.
- OR **manual curated YAML** (47 statements transcribed from the official PDF), like the Aramco/SABIC
  approach.
- Decide subcontrol handling first (see parent/subcontrol recommendation in the Phase 2L report):
  importing OTCC well likely benefits from subcontrol support.
- Only register `NCA-OTCC-1-2022` in `DATASET_FILES` once it validates fully (47/47, clean text).
