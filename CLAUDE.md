# TN State Bus Corporations — Route-Level Analytics Project

## 1. Project Context

This is a **portfolio/learning project**, not a production system. A non-IT colleague is building this to demonstrate data engineering + analytics skills to her manager and support a move into an IT role. Scope is intentionally kept **small and clean** rather than "enterprise-grade." Favor simplicity, clarity, and finishing all steps over adding extra complexity.

**Do not introduce technologies, orchestration, or patterns beyond what's listed below unless explicitly asked.**

## 2. Tech Stack (fixed — nothing else)

1. **Databricks** — ingestion, cleaning, transformation, SQL Warehouse for serving
2. **GitHub** — version control / repo structure
3. **Power BI** — dashboarding, connected live to Databricks SQL Warehouse
4. **No orchestration/pipeline** — this is a **one-time manual batch ingestion** of the source Excel files. No Jobs, no Workflows, no scheduling, no streaming.

## 3. Source Data

8 Excel files, one per bus corporation, each with a single sheet (`Sheet1`), no separate header/metadata sheets. Approximate row counts (excluding header):

| File | Corporation | Data Rows | Columns |
|---|---|---|---|
| MTC.xlsx | MTC (Chennai) | 3,847 | 53 |
| SALEM.xlsx | Salem | 1,902 | 54 (incl. 1 trailing blank col) |
| SETC.xlsx | SETC | 612 | 54 (incl. 1 trailing blank col) |
| TIRUNELVELI.xlsx | Tirunelveli | 1,692 | 53 |
| VILLUPURAM.xlsx | Villupuram | 4,234 | 53 |
| coimbatore.xlsx | Coimbatore | 2,559 | 53 |
| kumbakonam.xlsx | Kumbakonam | 3,492 | 53 |
| madurai.xlsx | Madurai | 2,159 | 53 |

### 3.1 Canonical column list (as they appear in source, row 1 headers)

```
No, Corporation (Full Name), Region (Full name), Branch (full name),
Category (Town/Mofussil/Ghat), Schedule/Special (SCH/SPL), Route No, Service,
origin, destination, Type of Service (ORD/EXP/DLX/UD/AC Seater/AC Sleeper/
Non AC sleeper/Multi axle), More than 250 KM Route length (Board route) (Yes/No),
Social Oblicatory Route (Yes/No), Conductor less operation (Yes/No),
Peak hour service (4+4=8hrs)/12hrs/NA, Inter state route (AP/KA/KL/PY/TN),
Average Fare per KM, Seating + Standing Capacity, Route Length,
No. of Schedule Singles per day, Schedule KM per day per bus,
Total Singles actually operated, No. of days actually operated,
Want of Crew, Break down, Want of Spares, Accident, Others,
Total Not run, Total Operated + Not Run days,
Total KM Loss in April-2026 if any, Total Operated KM,
Opern. Revenue without cess, Other Revenue (incl. Reimbursement/Subsidy/Grant),
Total Revenue, HSD Cost, Other V.C, Total VC Cost,
Establishment Cost, Other Establishment Cost, Esst + Other Esst,
Other Cost (incl. depreciation/interest/MV tax etc.), Total Expenditure,
Net Profit / Loss Apr-2026, Total passengers travelled in Apr-2026,
Earning per KM (EPKM) /w, Earning per bus per day (EPBD) /w, OR/w,
Earning per KM (EPKM) /wo, Earning per bus per day (EPBD) /wo, OR/wo,
Revenue loss due to KM loss, sch. km to be operated
```
Note: all data reflects **April 2026** as the reporting month (field names literally say "Apr-2026" / "April-2026" — this is a fixed reporting period, not a rolling one, for this dataset).

### 3.2 Confirmed data quality issues (found directly in source files)

All 8 files were fully profiled (schema, dtypes, nulls, duplicates, outliers) on 2026-07-14. Row/column counts match the table in §3. Findings and their Silver-layer resolution:

- **Trailing 54th column is NOT actually blank**: SALEM.xlsx (~21% of rows) and SETC.xlsx (~22% of rows) have an unnamed/unlabeled 54th column (`Unnamed: 53` in pandas) containing real numeric data — mostly negative values, some zeros (e.g. -3800, -412, -899), no header, meaning unknown. **Resolution**: carry through to Silver as a generic `unlabeled_value_54` column (nullable) for both files; do not assign it business meaning. Note in Data Quality Report as unresolved. MTC/TIRUNELVELI/VILLUPURAM/coimbatore/kumbakonam/madurai do not have this column at all.
- **Inconsistent corporation-name casing/spacing**: e.g. `'VILLUPURAM '` (trailing space) vs `'MTC'`, `'SALEM'`, `'SETC'` — corporation name fields need `.strip()` + uppercase normalization across all 8 files.
- **Mixed data types in `Route No`, and also `Service`**: `Route No` mixes string, integer, **and float** in different rows within the same file (e.g. MADURAI mixes all three: `'2K'`, `504`, `146.0`) — present in every file except SETC. `Service` mixes string/integer within the same file in SALEM, TIRUNELVELI, VILLUPURAM, and COIMBATORE — found only when checking *every* column's Python types, not just `Route No`, so don't assume this list is exhaustive without re-running that check on any new source file. **Technical note**: this isn't just a Silver-layer cleanup preference — PySpark's Arrow-based `pandas.DataFrame` → `spark.createDataFrame()` conversion cannot represent a mixed-dtype column at all and throws `Exception thrown when converting pandas Series ... to Arrow Array`. Both columns must already be a single consistent string type (whole-number floats rendered without `.0`, e.g. `504.0` → `'504'`) **before** the Bronze notebook's `spark.createDataFrame()` call — done in `notebooks/01_bronze/01_bronze_ingestion.py` via `safe_to_str()`.
- **TIRUNELVELI: 87 placeholder rows, not real routes**: rows where `Route No`, `Service`, `origin`, and `destination` are all literally `'ADDL'` / `'ADDITIONAL'`. Also other malformed `Route No` values there: `'1 TO 5'`, `'20/50'`, `'5/14'`, `'RLY'`, `'36/38'`, `'501/569'`, `'11/19'`, `'349/564'` — range/grouped notations that don't cast to a single route identifier. **Resolution**: keep all rows in Silver, add a `is_placeholder_route` (or similar) DQ flag column so Gold-layer route-level analysis can exclude/segregate them as needed.
- **Heavy nulls in operational "reason for non-operation" columns, at the corporation level**: `Want of Crew`, `Break down`, `Want of Spares`, `Accident`, `Others` are ~93–100% null for entire corporations — SALEM, SETC, TIRUNELVELI, KUMBAKONAM essentially never fill these in — vs. MTC and COIMBATORE which consistently 0-fill them, and VILLUPURAM/MADURAI which are mixed (~38.6% / ~1.8% null respectively, mostly 0-filled otherwise). Null here means "not tracked by this corporation," not necessarily "zero incidents." **Resolution**: fill null with `0` for aggregation math, AND add a `reason_tracked` boolean flag (per corporation, or derived from whether any of the 5 reason columns are non-null for that row) so the "not tracked" signal isn't silently lost.
- **Two physically impossible negative values** (data-entry errors, not a systemic pattern): SALEM row No=1840 (Route P02) has `Total passengers travelled in Apr-2026` = -7876; COIMBATORE row No=2080 (Route 89) has `Route Length` = -158. **Resolution**: take absolute value in Silver (assume sign was a data-entry error, magnitude otherwise correct). Note both rows in Data Quality Report.
- **Invalid `Inter state route` code**: COIMBATORE has 6 rows with value `'Y'`, not in the AP/KA/KL/PY/TN/NA vocabulary (routes: PALANI–GURUVAYOOR, PALANI–PALGHAT ×2, PALANI–MYSURU ×2, TIRUPPUR–TRICHUR). **Resolution**: leave value as `'Y'` as-is in Silver, add a DQ flag rather than guessing which state it means.
- **`Inter state route` field mostly/entirely null for some corporations**: 100% null in MTC, 98.7% null in MADURAI (vs. 0% null in SALEM/SETC/TIRUNELVELI/VILLUPURAM/COIMBATORE/KUMBAKONAM, which are predominantly `'TN'`). Treat null as `'NA'` (not inter-state) per existing convention — but be aware MTC/MADURAI essentially don't populate this field at all rather than "occasionally."
- **`Peak hour service` is 75–100% null in every single file** (worst: SETC/TIRUNELVELI/VILLUPURAM/KUMBAKONAM near 100%) — borderline unusable as a field for analysis. Flagged for awareness; no fix applied.
- **`Average Fare per KM` is 100% null in MTC only** (0% null in all other 7 files) — MTC-derived EPKM/OR calculations cannot rely on this column and may need an alternate derivation for MTC specifically.
- **Inconsistent header schema across files**: column count varies (53 vs 54) due to the trailing 54th column above; column order and names otherwise consistent across all 8 files.
- **Source column headers don't match the "canonical" list in §3.1 verbatim**: actual headers contain typos and embedded newlines, e.g. `'Esstablishment Cost'`, `'Total Singles actualy operated'`, `'No.of days actualy operated'`, `'Category \n (Enter Town/ Mof / Ghat)'`, `'Opern. Revenue with out cess'`, `'REVENUE LOSS DUE TO KM LOSS'` (all-caps). §3.1 is a cleaned paraphrase for readability. **Resolution**: Bronze ingestion must build an explicit rename map from real source headers → canonical names; do not assume §3.1 text matches source headers exactly.

## 4. Architecture — Medallion (Databricks)

- **Bronze**: raw one-time ingestion of all 8 Excel files as-is, tagged with source filename/corporation, no transformation.
- **Silver**: cleaned & conformed — unified schema (drop blank trailing columns), standardized corporation names, `Route No` cast to string, null handling on reason-for-non-operation columns, standardized Yes/No/NA flags.
- **Gold**: aggregated/business-ready tables for Power BI — route-level and corporation-level rollups of Revenue, Expenditure, Net Profit/Loss, EPKM, Occupancy Ratio (OR), KM Loss due to non-operation.

Power BI connects **live** to Databricks via **SQL Warehouse** (no data duplication/export into Power BI's own storage; Import mode or DirectQuery — decide during dashboard step).

## 5. Execution Workflow (7 steps, in order)

1. Scope note (what's in/out of scope) — done
2. GitHub repo structure
3. Bronze ingestion notebook(s)
4. Silver cleaning layer notebook(s)
5. Gold aggregation layer notebook(s)
6. Power BI connection via Databricks SQL Warehouse
7. Dashboard page design

## 6. Manager-Facing Deliverables (6 total)

1. Project Charter / one-pager
2. PDD (Project Design Document) — with architecture diagram + data dictionary
3. Data Quality Report — documenting issues in §3.2 and how they were resolved
4. Executive Summary
5. Dashboard User Guide
6. Final presentation deck

## 7. Key Business Metrics Glossary

- **EPKM** — Earning Per KM (revenue efficiency per kilometre run); reported both "with" (`/w`) and "without" (`/wo`) some adjustment.
- **OR** — Occupancy Ratio.
- **Net Profit/Loss** — Total Revenue − Total Expenditure, per route per month.
- **KM Loss** — Scheduled KM not actually operated, broken down by reason (crew shortage, breakdown, spares, accident, other).
- **Revenue Loss due to KM Loss** — Estimated revenue foregone from non-operated KM.

## 8. Working Agreement for Claude Code

- Treat this as a **finished, one-time batch project** — no pipeline scheduling, no incremental/CDC logic, no streaming.
- Keep notebooks readable and well-commented; this will be reviewed by a manager, not just run.
- Match column names/casing to the canonical list in §3.1 wherever code references them.
- Flag any new data quality issue you find beyond §3.2 rather than silently patching it — it needs to go in the Data Quality Report too.
- Ask before assuming business logic (e.g., how to treat null reason-codes) if it's not explicit above.
