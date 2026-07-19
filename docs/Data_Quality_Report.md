# Data Quality Report

**Project:** TN State Bus Corporations — Route-Level Analytics
**Reporting period covered by source data:** April 2026
**Profiling date:** 2026-07-14
**Sources profiled:** 8 corporation Excel files — MTC, SALEM, SETC, TIRUNELVELI,
VILLUPURAM, COIMBATORE, KUMBAKONAM, MADURAI (20,497 rows combined)

## 1. Purpose

This report documents every data quality issue identified in the 8 source Excel
files during ingestion and cleaning, and states exactly how each issue was
resolved (or, where a resolution would have required guessing, why it was
deliberately left unresolved and flagged instead). It is the audit trail behind
the Bronze → Silver → Gold pipeline described in the Project Design Document.

## 2. Methodology

Each of the 8 source files was profiled individually before any cleaning logic was
written: schema (column names, order, count), data types per column, null/blank
rates per column, duplicate checks, and outlier/range checks on numeric fields.
Row and column counts were confirmed against expectations before proceeding. Every
issue below was found this way — directly in the source data, not introduced by
the cleaning process.

## 3. Summary of Findings

| # | Issue | Files Affected | Resolution | Status |
|---|---|---|---|---|
| 1 | Unlabeled 54th column with real numeric data (no header, meaning unknown) | SALEM (~21% of rows), SETC (~22% of rows) | Carried through as generic `unlabeled_value_54`; no business meaning assigned | Flagged — unresolved |
| 2 | Inconsistent corporation/region/branch name casing & spacing | All 8 files | Trimmed + uppercased | Resolved |
| 3 | `Route No` mixes string/int/float within the same column | 7 of 8 files (all except SETC) | Forced to single consistent text format; whole-number decimals rendered without `.0` | Resolved |
| 4 | `Service` mixes string/int within the same column | SALEM, TIRUNELVELI, VILLUPURAM, COIMBATORE | Forced to single consistent text format | Resolved |
| 5 | `Inter state route`, `Peak hour service`, `Social Oblicatory Route` are internally consistent per file but a different data type across files, breaking the multi-file combine step | All 8 files | Forced to text type in every file (including fully-blank ones) before combining | Resolved |
| 6 | 87 placeholder rows (`'ADDL'` / `'ADDITIONAL'` in Route No/Service/origin/destination) — not real routes | TIRUNELVELI | Flagged with `is_placeholder_route`; retained in Silver, excluded from Gold rollups | Resolved (flagged + excluded downstream) |
| 7 | Heavy nulls in the 5 "reason trip didn't run" columns — null means "not tracked," not "zero incidents" | SALEM, SETC, TIRUNELVELI, KUMBAKONAM (~93–100% null); VILLUPURAM (~38.6%), MADURAI (~1.8%) | Null filled with 0 for aggregation; `reason_tracked` flag preserves whether the corporation reports this at all | Resolved |
| 8 | Physically impossible negative value: `Total passengers travelled` = -7,876 | SALEM, row No=1840, Route P02 | Absolute value applied (assumed sign error, magnitude correct) | Resolved |
| 9 | Physically impossible negative value: `Route Length` = -158 | COIMBATORE, row No=2080, Route 89 | Absolute value applied (assumed sign error, magnitude correct) | Resolved |
| 10 | Invalid `Inter state route` code `'Y'` — not in AP/KA/KL/PY/TN/NA vocabulary | COIMBATORE, 6 rows (PALANI–GURUVAYOOR, PALANI–PALGHAT ×2, PALANI–MYSURU ×2, TIRUPPUR–TRICHUR) | Value left as-is; flagged with `invalid_interstate_code` rather than guessed at | Flagged — unresolved |
| 11 | `Inter state route` almost entirely null for some corporations | 100% null in MTC, 98.7% null in MADURAI | Null treated as `'NA'`, consistent with the field's existing null convention | Resolved (documented limitation) |
| 12 | `Peak hour service` 75–100% null in every file (worst: SETC/TIRUNELVELI/VILLUPURAM/KUMBAKONAM near 100%) | All 8 files | No fix applied — field is borderline unusable for analysis | Flagged for awareness only |
| 13 | `Average Fare per KM` 100% null | MTC only | No fix applied — MTC-derived EPKM/OR figures cannot rely on this column | Flagged for awareness only |
| 14 | Inconsistent column count across files (53 vs 54) | SALEM/SETC (54) vs. other 6 (53) | Explained by finding #1; handled automatically via `unionByName(allowMissingColumns=True)` | Resolved |
| 15 | Source headers contain typos, embedded newlines, inconsistent wording (e.g. `Esstablishment Cost`, `Total Singles actualy operated`, `Category \n (Enter Town/ Mof / Ghat)`) | All 8 files | Explicit hand-built rename map to clean, consistent snake_case names in Silver | Resolved |

## 4. Detailed Findings

### 4.1 Unlabeled 54th column (SALEM, SETC)
**Description:** SALEM and SETC each have an extra, unnamed trailing column
containing real numeric data (mostly negative values, some zeros — e.g. -3800,
-412, -899), present in roughly a fifth of rows in each file. The other 6 files
don't have this column at all.
**Impact:** Meaning and origin unknown; cannot be assigned a business label without
input from the source corporations.
**Resolution:** Retained in Silver as a generic, nullable `unlabeled_value_54`
column. Not used in any Gold-layer calculation. Recommend follow-up with
SALEM/SETC to determine what this column represents.

### 4.2 Corporation/region/branch name casing & spacing
**Description:** The same corporation appears differently formatted across rows,
e.g. `'VILLUPURAM '` (trailing space) vs. `'MTC'`.
**Resolution:** All four name fields (`corporation_full_name`, `region_full_name`,
`branch_full_name`, `corporation_code`) are trimmed and uppercased in Silver.

### 4.3 Mixed data types in `Route No` and `Service`
**Description:** `Route No` holds string, integer, and float values within the
same file (e.g. MADURAI has `'2K'`, `504`, `146.0` side by side) — present in
every file except SETC. `Service` shows the same string/integer mixing in SALEM,
TIRUNELVELI, VILLUPURAM, and COIMBATORE.
**Impact:** This is not just a cosmetic issue — the tool used to convert the data
into Databricks' storage format cannot represent a column with mixed types at all,
and fails outright with an Arrow conversion error.
**Resolution:** Both columns are forced to a single, consistent text type before
loading, with whole-number floats rendered without a trailing `.0` (e.g. `504.0`
becomes `'504'`), so the same route reads identically regardless of which row or
file it came from.

### 4.4 Cross-file type mismatch on 3 columns
**Description:** `Inter state route`, `Peak hour service`, and `Social Oblicatory
Route` are each internally consistent within any single file, but the underlying
data type differs from file to file — for example, `Inter state route` is 100%
blank in MTC (which the system reads as a numeric-type column by default) but
contains genuine text values (`'TN'`, `'KA'`, etc.) in every other file.
**Impact:** When the 8 files are combined into one table, the system attempts to
reconcile these differing type guesses and fails with a cast error (e.g. trying to
cast the text `'NO'` into a numeric type).
**Resolution:** All three columns are forced to text type in every file — including
files where the column is entirely blank — before the files are combined.

### 4.5 Placeholder rows in TIRUNELVELI
**Description:** 87 rows have `'ADDL'` or `'ADDITIONAL'` (not necessarily the same
word in every column) in place of real values for Route No, Service, origin, and
destination. Other malformed `Route No` entries were also found in TIRUNELVELI
(`'1 TO 5'`, `'20/50'`, `'5/14'`, `'RLY'`, `'36/38'`, `'501/569'`, `'11/19'`,
`'349/564'`) — range/grouped notations rather than single route identifiers.
**Impact:** These rows would overstate or misattribute route-level and
corporation-level totals if included in analysis as if they were real routes.
**Resolution:** Retained in Silver (no data is deleted) but flagged with
`is_placeholder_route = true`. The Gold aggregation layer explicitly excludes
these 87 rows before summarizing.

### 4.6 Nulls in "reason trip didn't run" columns
**Description:** `Want of Crew`, `Break down`, `Want of Spares`, `Accident`,
`Others` are ~93–100% null for SALEM, SETC, TIRUNELVELI, and KUMBAKONAM — these
corporations essentially never populate these fields — versus MTC and COIMBATORE,
which consistently 0-fill them, and VILLUPURAM/MADURAI, which are mixed (~38.6%
and ~1.8% null respectively, mostly 0-filled otherwise).
**Impact:** A blank does not mean "zero incidents" — it means the corporation
doesn't track this level of detail. Filling blanks with 0 without also preserving
this distinction would make untracked corporations look identical to corporations
that genuinely had no incidents.
**Resolution:** A `reason_tracked` flag is computed first (true if any of the 5
columns had a real value for that row), then all 5 columns are 0-filled for
aggregation math. The flag is carried through to Gold so this distinction remains
visible.

### 4.7 Two data-entry sign errors
**Description:** SALEM row No=1840 (Route P02) reports -7,876 passengers for the
month; COIMBATORE row No=2080 (Route 89) reports a route length of -158 km. Both
values are physically impossible as negatives.
**Resolution:** Absolute value applied to `total_passengers` and `route_length_km`
across all rows (not just these two), on the assumption that the sign was a
data-entry error and the magnitude is otherwise correct. Both source rows are
documented here for traceability.

### 4.8 Invalid inter-state route code
**Description:** COIMBATORE has 6 rows with `Inter state route = 'Y'`, which is
not part of the expected AP/KA/KL/PY/TN/NA vocabulary. Affected routes:
PALANI–GURUVAYOOR, PALANI–PALGHAT (×2), PALANI–MYSURU (×2), TIRUPPUR–TRICHUR.
**Resolution:** Value left unchanged (no state was guessed); flagged with
`invalid_interstate_code = true`. Recommend follow-up with COIMBATORE to confirm
the intended state code.

### 4.9 Sparse/unreliable fields (documented limitations, no fix applied)
- **`Inter state route`** is 100% null in MTC and 98.7% null in MADURAI (vs. 0%
  null and predominantly `'TN'` in the other 6 files). Null is treated as `'NA'`
  per the existing convention, but MTC/MADURAI effectively don't populate this
  field at all rather than occasionally.
- **`Peak hour service`** is 75–100% null in every one of the 8 files (worst in
  SETC, TIRUNELVELI, VILLUPURAM, KUMBAKONAM, which are near 100% null). No fix was
  applied; this field is flagged as borderline unusable for analysis.
- **`Average Fare per KM`** is 100% null in MTC only (0% null everywhere else).
  Any EPKM/Occupancy Ratio analysis specific to MTC cannot rely on this column and
  may need an alternate derivation.

### 4.10 Header/schema inconsistencies
**Description:** Column count varies (53 vs. 54, explained by finding #1). Actual
source headers contain typos and embedded newlines not reflected in the
project's canonical column list, e.g. `'Esstablishment Cost'`, `'Total Singles
actualy operated'`, `'No.of days actualy operated'`, `'Category \n (Enter Town/
Mof / Ghat)'`, `'Opern. Revenue with out cess'`, `'REVENUE LOSS DUE TO KM LOSS'`
(all-caps).
**Resolution:** An explicit, hand-built rename map translates every real source
header to a clean, consistent name in the Silver layer — nothing was assumed to
match the canonical naming without verifying against the actual file headers.

## 5. Items Requiring Follow-Up

Two issues could not be resolved without risking an incorrect assumption, and are
carried forward as open items rather than silently guessed at:

1. **Unlabeled 54th column** (SALEM, SETC) — recommend asking the source
   corporations what this column represents.
2. **Invalid `'Y'` inter-state code** (COIMBATORE, 6 rows) — recommend confirming
   the intended state code with COIMBATORE.

Two fields are flagged as low-reliability for analysis but require no action,
only awareness when interpreting results:
- `Peak hour service` (75–100% null across all files)
- `Average Fare per KM` (100% null for MTC specifically)

## 6. Outcome

After cleaning, every row from the original 8 files (20,497 total) is retained
through the Silver layer with no data loss — issues were fixed, standardized, or
flagged, never silently dropped. The Gold layer's route- and corporation-level
totals were validated to reconcile exactly against Silver's cleaned figures (see
`notebooks/03_gold/03_gold_aggregation.py` validation cells), confirming the
resolutions above did not introduce any calculation discrepancies.
