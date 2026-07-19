# Project Understanding Document — TN State Bus Corporations Route Analytics

## 1. What This Project Is About

Tamil Nadu has several government-run bus corporations (MTC/Chennai, SALEM, SETC,
TIRUNELVELI, VILLUPURAM, COIMBATORE, KUMBAKONAM, MADURAI). Each corporation reports
detailed monthly performance data for every bus route it runs — how many kilometres
were scheduled versus actually operated, how much revenue and expenditure each route
generated, how many passengers travelled, and why any scheduled trips didn't run
(crew shortage, breakdown, lack of spares, accident, or other reasons).

This data currently exists as 8 separate Excel files — one per corporation — for the
reporting month of **April 2026**. Each file has its own quirks: inconsistent spelling,
mixed data types in the same column, extra unexplained columns, missing values, and a
few outright data-entry errors.

The goal of this project is to take those 8 raw, messy Excel files and turn them into
a small number of clean, reliable, business-ready tables that can answer questions
like:
- Which routes are profitable, and which are losing money?
- Which corporation gets the best "earning per kilometre" out of its buses?
- How much revenue is being lost because scheduled trips didn't run, and why?
- How does one corporation compare to another on occupancy, cost, and efficiency?

Those clean tables are then meant to be connected to Power BI so the numbers can be
explored visually on a dashboard, without anyone needing to open the original Excel
files or write any code.

## 2. The Overall Approach: Three Layers (Bronze → Silver → Gold)

Rather than trying to clean and analyze the data in one single messy step, the work
is split into three stages, each stored as its own table inside Databricks (a cloud
data platform). This is a widely used pattern called the **medallion architecture**,
and the idea is simple: each stage does one job well, and every stage can always be
traced back to the one before it.

| Layer | Purpose | What changes |
|---|---|---|
| **Bronze** | Land the raw data | Nothing about the actual values is changed — just enough is done so the data can be stored at all |
| **Silver** | Clean and standardize | Column names become readable, values are standardized, errors are fixed, and quality issues are flagged |
| **Gold** | Summarize for reporting | The cleaned, row-per-trip data is rolled up into route-level and corporation-level summary tables |

Each layer is built by one Databricks notebook (a document that mixes explanation
text with runnable code, one step at a time). This document walks through what each
of those three notebooks actually does, and why, in plain terms.

---

## 3. Bronze Layer — Bringing the Raw Files In

**Notebook:** `notebooks/01_bronze/01_bronze_ingestion.py`
**Output table:** `bronze.bus_routes_raw` (20,497 rows)

### What it does, step by step

1. **Reads all 8 Excel files.** Each corporation's file (`MTC.xlsx`, `SALEM.xlsx`,
   `SETC.xlsx`, `TIRUNELVELI.xlsx`, `VILLUPURAM.xlsx`, `coimbatore.xlsx`,
   `kumbakonam.xlsx`, `madurai.xlsx`) is opened and its single sheet (`Sheet1`) is
   read in exactly as it appears — no filtering, no corrections.

2. **Tags every row with where it came from.** Three extra columns are added to
   every row: which file it came from, which corporation it belongs to, and the
   exact date/time it was loaded. This matters because once all 8 files are combined
   into one table, there needs to be a way to trace any given row back to its
   original source — both for troubleshooting and for auditability.

3. **Makes the column headers storage-safe, without changing their wording.**
   The database system used to store this data (Delta Lake) refuses to create a
   column whose name contains spaces or certain punctuation — and nearly every
   column header in these Excel files has a space in it (even something as simple
   as `Route No`). So each header has those problem characters swapped for
   underscores (`Route No` → `Route_No`). Importantly, this step does **not**
   correct typos or reword anything — a header like `Esstablishment Cost` (a typo
   in the original spreadsheet) becomes `Esstablishment_Cost`, typo and all. Fixing
   the wording and typos is deliberately left for the next layer (Silver), so that
   Bronze stays a faithful, literal copy of the source files.

4. **Fixes two columns that would otherwise break the load entirely.** While
   profiling the files, two technical problems were found that aren't just
   "messy data" — they actively prevent the files from being combined at all:
   - The `Route No` and `Service` columns mix text and numbers within the very same
     column (for example, one row says `2K` and another says `504`, and another
     says `146.0`). The system used to combine the files cannot handle a column that
     mixes types like this — it errors out.
   - Three other columns (`Inter state route`, `Peak hour service`, and
     `Social Oblicatory Route`) are internally consistent within each file, but the
     *type* of data in them differs from file to file — e.g., one corporation's file
     has no data at all in a column (so the system guesses it's a number column),
     while another corporation's file has real text values in that same column. When
     all 8 files are stitched together, the system tries to reconcile these
     different guesses and fails with a type-mismatch error.

   Both problems are fixed the same way: those five columns are explicitly forced
   to be treated as plain text in every file, including files where the column is
   completely empty. A helper function also makes sure a whole number stored as a
   decimal (like `504.0`) is written as plain `504`, not `504.0`, so the same route
   number reads identically no matter which file it came from.

5. **Combines all 8 files into one table.** The files are stacked on top of each
   other, matched up by column name. Two of the files (SALEM and SETC) have an
   extra, unexplained 54th column that the other six don't have — rather than
   dropping it or guessing what it means, that column is kept and simply left blank
   for the six files that don't have it.

6. **Saves the result** as the table `bronze.bus_routes_raw`, and includes a
   validation check at the end confirming the row count for each corporation
   matches what was expected from the original files (e.g., MTC = 3,847 rows,
   SALEM = 1,902 rows, and so on — 20,497 rows in total across all 8 files).

### Why this matters
Bronze is intentionally "dumb" — it doesn't try to be clever or fix anything beyond
what's strictly necessary to get the data stored at all. That's a deliberate safety
net: if something looks wrong three layers later, it's always possible to go back to
Bronze and confirm whether the issue was already present in the original files or was
introduced during cleaning.

---

## 4. Silver Layer — Cleaning and Standardizing

**Notebook:** `notebooks/02_silver/02_silver_cleaning.py`
**Output table:** `silver.bus_routes_silver` (20,497 rows — same row count as Bronze; nothing is deleted or added at this stage, only fixed and flagged)

This is where the real cleanup happens. Every fix below is either a rename, a
standardization of values, a correction of a known error, or the addition of a new
flag column that marks something worth knowing about a row — no rows are ever
removed here.

### 4.1 Renaming every column to a clear, consistent name
The 57 columns coming out of Bronze still carry their original, sometimes-typo'd
wording (`Esstablishment_Cost`, `Total_Singles_actualy_operated`,
`No.of_days_actualy_operated`). Silver renames every single one of them to a clean,
consistent name (e.g., `establishment_cost`, `total_singles_operated`,
`days_operated`). This rename list was built by hand, checking each source header
against its intended business meaning — it's not something that can be done
automatically, because deciding that `Esstablishment_Cost` really means
"Establishment Cost" requires understanding what the column is for, not just
correcting spelling mechanically.

As a safety check, the notebook will stop and raise an error if it ever finds a
column coming from Bronze that isn't in this rename list (or vice versa) — this
prevents a column from silently slipping through un-renamed or a rename rule from
silently referring to a column that no longer exists.

### 4.2 Standardizing corporation, region, and branch names
Some corporation/region/branch names had inconsistent spacing or capitalization in
the original files — for example, `'VILLUPURAM '` (with a trailing space) versus
`'MTC'`. Every one of these text fields is trimmed of extra spaces and converted to
uppercase, so the same corporation is always represented identically no matter which
file it came from.

### 4.3 Standardizing Yes/No/NA fields
Three columns that should only ever contain "Yes," "No," or "Not applicable" are
cleaned up so that any variation in capitalization, spelling, or blank values is
collapsed down to exactly one of three values: `YES`, `NO`, or `NA`. Anything blank,
missing, or unrecognized is treated as `NA` rather than guessed at.

A fourth column, `Inter state route` (which state a route crosses into, if any), is
handled slightly differently: rather than being collapsed to Yes/No, its actual
value (e.g., `TN`, `KA`, `KL`) is preserved as-is; only blank/missing values are
converted to `NA`. A separate check then flags any row where the value isn't one of
the six expected codes (`AP`, `KA`, `KL`, `PY`, `TN`, `NA`) — this catches 6 rows in
the COIMBATORE file that contain the value `'Y'`, which doesn't correspond to any
real state code. Rather than guessing which state was actually meant, those 6 rows
are simply flagged for visibility (`invalid_interstate_code = true`), and the
original value is left untouched.

### 4.4 Handling the "why didn't this trip run" columns
Five columns record *why* a scheduled trip didn't run: want of crew, breakdown, want
of spares, accident, and other reasons. For some corporations, these columns are
almost entirely blank — not because there were no incidents, but because that
corporation simply doesn't track this level of detail. Treating a blank as "zero
incidents" would be misleading, so two things happen:
1. Before anything else, a new flag column (`reason_tracked`) records whether *any*
   of the five reason columns had a real value for that row — this preserves the
   distinction between "this corporation reported zero incidents" and "this
   corporation doesn't report this at all."
2. *After* that flag is captured, the blanks are filled in with `0`, so that later
   summary calculations (which need to add numbers together) don't break or silently
   skip rows because of missing values.

### 4.5 Fixing two known data-entry errors
Two specific rows were found to contain values that are physically impossible:
- A SALEM row (route P02) recorded **-7,876 passengers** for the month — a negative
  passenger count doesn't make sense.
- A COIMBATORE row (route 89) recorded a **route length of -158 km** — a negative
  distance doesn't make sense either.

The assumption made here is that the negative sign was a data-entry mistake and the
actual magnitude of the number is correct — so both the `total_passengers` and
`route_length_km` columns have an "absolute value" fix applied across the board
(turning any negative value in either column positive), not just to these two known
rows, in case the same kind of entry error exists elsewhere undetected.

### 4.6 Flagging placeholder (non-real) routes
The TIRUNELVELI file contains 87 rows where the route number, service, origin, and
destination are all filled in with placeholder text like `'ADDL'` or `'ADDITIONAL'`
instead of real route information — these aren't actual bus routes, just filler
rows in the source spreadsheet. Rather than deleting them (which would lose the
information that they existed at all), a new flag column
(`is_placeholder_route = true`) marks them, so that any later analysis can choose to
exclude them explicitly.

### 4.7 Final output
Once every fix and flag above is applied, the result is written to
`silver.bus_routes_silver`, along with a timestamp of when the cleaning ran. The
notebook then validates itself:
- Confirms the row count still matches Bronze's 20,497 rows exactly (proving nothing
  was accidentally dropped or duplicated).
- Spot-checks that the two known negative-value rows were actually fixed.
- Confirms the placeholder-route flag caught exactly 87 rows, and the invalid
  inter-state-code flag caught exactly 6 rows — matching what was found during the
  original data investigation.

---

## 5. Gold Layer — Summarizing for Reporting

**Notebook:** `notebooks/03_gold/03_gold_aggregation.py`
**Output tables:** `gold.route_performance` and `gold.corporation_performance`

Silver still has one row per individual scheduled service — useful for detailed
drill-down, but too granular for a dashboard someone wants to glance at and quickly
compare routes or corporations. Gold rolls that detailed data up into two
ready-to-use summary tables. These two tables are what Power BI is meant to connect
to.

Before any summarizing happens, the 87 placeholder rows flagged in Silver (Section
4.6) are excluded — since they're not real routes, including them would inflate or
misattribute totals like revenue and kilometres.

### 5.1 Different kinds of numbers, summarized different ways
Not every column can be combined the same way. The notebook explicitly separates
columns into groups:

1. **Plain totals (summed).** Things like total revenue, total expenditure, total
   kilometres operated, total passengers, and each of the five "reason not
   operated" columns are straightforward — if you're combining multiple rows, you
   add them together. These are unambiguous.

2. **Ratios (KM-weighted average, not a simple average).** Columns like "Earning
   per KM" (EPKM), "Earning per bus per day" (EPBD), and "Occupancy Ratio" (OR) are
   already ratios reported by each corporation for each row — you can't just add two
   ratios together, and a plain average would unfairly give a tiny 5 km route the
   same influence as a busy 500 km route. Instead, these are combined as a
   **weighted average**, where each row's ratio is weighted by how many kilometres
   that route actually operated — so busier routes appropriately influence the
   combined figure more than lightly-used ones.

   One deliberate decision worth noting: rather than trying to *recalculate* EPKM,
   EPBD, or OR from scratch using a revenue/cost formula, the notebook uses the
   ratio values exactly as each corporation already reported them, and just
   aggregates those reported values correctly. This is because the exact difference
   between the "with" and "without" versions of these metrics (`/w` vs `/wo`) isn't
   fully specified in the source data documentation — reconstructing the formula
   from scratch risked producing numbers that wouldn't match anything the
   corporations actually publish. Using their own reported figures and combining
   them correctly avoids that risk.

3. **Yes/No characteristics (collapsed to "true if any row says yes").** Flags like
   "is this a long route over 250km," "is this a socially obligatory route," or "is
   this a conductor-less operation" describe a *characteristic* of the route, not a
   number to average. When multiple individual services on the same route are
   combined, the summary marks the route as "yes" if even one of its underlying
   services was marked yes.

4. **A total split into an estimated breakdown (allocated proportionally).** The
   source data only reports one **total** "revenue lost due to KM loss" figure per
   row — it doesn't say how much of that loss is attributable to crew shortage
   versus breakdown versus spares versus accident versus other reasons. To support
   a reason-by-reason breakdown on the dashboard, Gold **allocates** that total
   proportionally, based on each reason's share *among the 5 reason columns
   themselves* (e.g., if "breakdown" accounts for 30% of the combined
   crew/breakdown/spares/accident/other total for a route, 30% of that route's
   revenue loss is attributed to breakdown). This produces five new columns —
   `revenue_loss_want_of_crew`, `revenue_loss_breakdown`,
   `revenue_loss_want_of_spares`, `revenue_loss_accident`, `revenue_loss_others` —
   and a validation check confirms the five always add back up to the original
   total, wherever an allocation was actually possible.

   Note this is deliberately normalized against the 5 reason columns' own combined
   total, not against the separately-reported "Total KM Loss" figure — an earlier
   version of this logic used "Total KM Loss" as the divisor and produced badly
   wrong numbers, because 4 of the 8 corporations (SALEM, SETC, TIRUNELVELI,
   KUMBAKONAM) essentially never fill in the 5 reason columns at all (Section 4.4
   above), while still reporting a real, non-zero "Total KM Loss." Dividing by that
   figure allocated almost nothing to any reason for those corporations, while the
   real total stayed large — the parts silently didn't add up to the whole. For
   those same 4 corporations, all five `revenue_loss_*` columns are `NULL` rather
   than a wrong number — there's genuinely no reason breakdown reported for them to
   allocate from, consistent with how `reason_tracked` already handles this same
   gap elsewhere. **This is an estimate, not a figure the corporations directly
   reported** — it's a reasonable, transparent way to split a number that was only
   ever given in total, wherever a reason breakdown exists to split it by.

### 5.2 `gold.route_performance` — one row per route
Grouped by corporation + route number (all the individual scheduled services on a
route are combined into one row for that route). Includes:
- Descriptive info carried over: corporation/region/branch name, origin,
  destination, category, schedule type, service type, inter-state route code, and
  route length.
- All the summed totals, weighted-average ratios, and any-yes flags described above.
- A count of how many distinct scheduled services exist under that route number.
- Three extra calculated metrics, computed *after* summing (not averaged
  beforehand, to keep the math sound):
  - **Net profit margin %** = net profit/loss ÷ total revenue × 100
  - **% of scheduled KM actually operated** = total operated KM ÷ scheduled KM × 100
  - **% of scheduled KM lost** = total KM lost ÷ scheduled KM × 100

### 5.3 `gold.corporation_performance` — one row per corporation
Grouped by corporation only. This uses the same shared totals/ratios/flags logic as
the route table, but drops descriptive fields like region, branch, category, and
service type — because at the whole-corporation level, a single route's origin or
category doesn't mean anything (a corporation runs many different origins,
categories, and service types at once, so picking just one to display would be
arbitrary and misleading). Instead it adds a count of how many distinct routes and
how many distinct services the corporation runs in total.

### 5.4 Validation before trusting the output
The notebook checks itself in two ways before considering the job done:
1. **Row counts.** The number of rows in `route_performance` must exactly match the
   number of distinct corporation+route combinations in the cleaned data, and
   `corporation_performance` must have exactly one row per corporation — proving
   nothing was double-counted or dropped beyond the intentional placeholder
   exclusion.
2. **Revenue reconciliation.** The total revenue summed across all of
   `route_performance` must match the total revenue summed across all of
   `corporation_performance`, which must in turn match the total revenue in the
   cleaned Silver data (minus the excluded placeholder rows). If these three numbers
   don't agree almost exactly, the notebook stops rather than allowing untrustworthy
   numbers to reach the dashboard.

---

## 6. What Ends Up in Databricks, and What Power BI Will See

| Table | Grain (one row = ...) | Purpose |
|---|---|---|
| `bronze.bus_routes_raw` | one scheduled service, exactly as read from Excel | Raw archive / audit trail |
| `silver.bus_routes_silver` | one scheduled service, cleaned | Detailed drill-through, DQ flags visible |
| `gold.route_performance` | one route (all services on it combined) | Route-level dashboard views |
| `gold.corporation_performance` | one corporation (all its routes combined) | Corporation-level comparison dashboard views |

Power BI is intended to connect live to the two Gold tables via Databricks SQL
Warehouse — so the dashboard always reflects whatever is currently in those tables,
without a separate copy of the data being exported anywhere.

---

## 7. Data Quality Issues Found, and How Each Was Resolved

This is a consolidated list of every data quality issue discovered while building
Bronze/Silver/Gold, and exactly what was done about each one.

| Issue | Where found | Resolution |
|---|---|---|
| Unexplained 54th column with real numeric data (mostly negative numbers), no header | SALEM (~21% of rows), SETC (~22% of rows) | Kept as a generic `unlabeled_value_54` column; no business meaning assigned; left blank for the other 6 corporations |
| Inconsistent corporation/region/branch name casing and spacing (e.g. `'VILLUPURAM '`) | All files | Trimmed and uppercased |
| `Route No` and `Service` mix text, whole numbers, and decimals within the same column | Every file except SETC (`Route No`); SALEM/TIRUNELVELI/VILLUPURAM/COIMBATORE (`Service`) | Forced to a single consistent text format before combining; whole-number decimals rendered without `.0` |
| `Inter state route`, `Peak hour service`, `Social Oblicatory Route` are consistent within a file but a different data type from file to file (causing a hard failure when combining) | Across all 8 files | Forced to text format in every file, including fully-blank ones, before combining |
| 87 placeholder rows (`'ADDL'`/`'ADDITIONAL'` instead of real route data) | TIRUNELVELI | Flagged with `is_placeholder_route`; excluded from Gold summaries but kept (not deleted) in Silver |
| Heavy blanks in the 5 "reason trip didn't run" columns, meaning "not tracked" rather than "zero incidents" for some corporations | SALEM, SETC, TIRUNELVELI, KUMBAKONAM (almost entirely blank); VILLUPURAM/MADURAI (partially blank) | Blank filled with 0 for calculation purposes, but a `reason_tracked` flag preserves whether the corporation reports this at all |
| Negative value where impossible: -7,876 passengers | SALEM, route P02 | Converted to positive (assumed data-entry sign error) |
| Negative value where impossible: -158 km route length | COIMBATORE, route 89 | Converted to positive (assumed data-entry sign error) |
| Invalid inter-state-route code `'Y'` (not a real state code) | COIMBATORE, 6 rows | Left as-is, flagged with `invalid_interstate_code` rather than guessed at |
| `Inter state route` almost entirely blank for some corporations | 100% blank in MTC, 98.7% blank in MADURAI | Blank treated as `NA` (not inter-state), consistent with how every other blank in this column is handled |
| `Peak hour service` is 75–100% blank in every single file | All 8 files | Noted as an unreliable field; no fix attempted, flagged for awareness only |
| `Average Fare per KM` is completely blank | MTC only | Noted — any MTC-specific fare analysis may need an alternate approach, since this field can't be used for MTC |
| Column count differs between files (53 vs. 54) | SALEM/SETC vs. the other 6 | Explained by the unlabeled 54th column above; handled automatically when files are combined |
| Source column headers contain typos, inconsistent wording, and line breaks, and don't match a clean naming convention | All files | Explicit rename list built by hand in Silver, mapping every original header to a clean, consistent name |

Two items are noted as **unresolved / left as visible limitations** rather than
fixed, because guessing at the correct value would risk introducing an incorrect
assumption: the unlabeled 54th column (SALEM/SETC), and the invalid `'Y'`
inter-state code (COIMBATORE).

---

## 8. Business Terms Used Throughout

- **EPKM (Earning Per KM)** — how much revenue is earned for every kilometre a bus
  travels; reported both "with" and "without" some adjustment by each corporation.
- **EPBD (Earning Per Bus per Day)** — average revenue earned per bus, per day.
- **OR (Occupancy Ratio)** — how full the buses are running, as a ratio.
- **Net Profit/Loss** — total revenue minus total expenditure for a route, for the
  reporting month.
- **KM Loss** — the amount of scheduled kilometres that were not actually operated,
  broken down by the reason (crew shortage, breakdown, spares, accident, other).
- **Revenue Loss due to KM Loss** — the estimated revenue that was missed out on
  because of those non-operated kilometres.

---

## 9. What's Already Done, and What's Still Pending

**Done:** Bronze ingestion, Silver cleaning, Gold aggregation (Steps 1–5 of the
project's 7-step workflow), all validated with row-count and revenue-reconciliation
checks.

**Still pending:**
- Connecting Power BI live to the Databricks SQL Warehouse, pointed at
  `gold.route_performance` and `gold.corporation_performance`.
- Designing the actual dashboard pages.
- The six manager-facing deliverables (Project Charter, PDD, Data Quality Report,
  Executive Summary, Dashboard User Guide, Final Presentation Deck) — none of these
  have been written yet; this document, along with Section 7 above, is intended to
  provide the underlying detail those deliverables can draw from.
