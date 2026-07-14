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

- **Trailing blank column**: SALEM.xlsx and SETC.xlsx have an extra unnamed 54th column with no header and no data — MTC/TIRUNELVELI/VILLUPURAM/coimbatore/kumbakonam/madurai do not.
- **Inconsistent corporation-name casing/spacing**: e.g. `'VILLUPURAM '` (trailing space) vs `'MTC'`, `'SALEM'`, `'SETC'` — corporation name fields need `.strip()` + uppercase normalization across all 8 files.
- **Mixed data types in `Route No`**: stored as string in some rows (e.g. `'14M'`, `'191A'`, `'110A'`) and as integer in others (e.g. `1`, `504`, `146`) — even within the same file. Must be cast to string consistently in Silver layer.
- **Heavy nulls in operational "reason for non-operation" columns**: `Want of Crew`, `Break down`, `Want of Spares`, `Accident`, `Others` are frequently `None` rather than `0` — needs null-handling logic (treat null as 0 for aggregation, but don't lose the signal that "no reason logged" ≠ "zero loss").
- **Inconsistent header schema across files**: column count varies (53 vs 54) due to the trailing blank column above; column order and names otherwise are consistent across all 8 files.
- **`Inter state route` field**: sometimes `None`/blank where clearly should be `'NA'` — inconsistent null vs explicit "NA" string.

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
