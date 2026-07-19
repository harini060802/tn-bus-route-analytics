# Progress Notes

Working log of what's done and what's next, so a new session can pick up without
re-deriving context. Full project context lives in `CLAUDE.md` — this file just tracks
state and the "gotchas" hit along the way.

## Status: Steps 1–5 of the workflow (CLAUDE.md §5) are done

| Step | Status |
|---|---|
| 1. Scope note | Done |
| 2. GitHub repo structure | Done |
| 3. Bronze ingestion notebook | Done — `notebooks/01_bronze/01_bronze_ingestion.py` |
| 4. Silver cleaning notebook | Done — `notebooks/02_silver/02_silver_cleaning.py` |
| 5. Gold aggregation notebook | Done — `notebooks/03_gold/03_gold_aggregation.py` |
| 6. Power BI connection via SQL Warehouse | Done — Import mode, connected to `gold.route_performance` + `gold.corporation_performance` |
| 7. Dashboard page design | In progress — Executive page built (see below) |

Of the 6 manager-facing deliverables (`CLAUDE.md` §6, tracked in `docs/`):
`docs/project_understanding_doc.md` (plain-language walkthrough of Bronze/Silver/Gold)
and `docs/Data_Quality_Report.md` are done. Charter, PDD, Executive Summary, Dashboard
User Guide, and Final Deck are **not started**.

## What each notebook does (run in this order in Databricks)

1. **`01_bronze_ingestion.py`** — reads all 8 source Excel files from a Volume, tags each
   row with `_source_file`/`_corporation_raw`/`_ingestion_ts`, sanitizes headers just
   enough to be valid Delta column names (`sanitize_delta_column_name`), and writes
   `{catalog}.bronze.bus_routes_raw` (20,497 rows). No business cleaning.
2. **`02_silver_cleaning.py`** — reads Bronze, renames all 57 columns to a snake_case
   schema (`RENAME_MAP`), standardizes corporation/region/branch casing and Yes/No/NA
   flags, fills the 5 non-operation-reason columns (+ `reason_tracked` flag), fixes the
   two known negative-value rows, adds `is_placeholder_route` and
   `invalid_interstate_code` DQ flags. Writes `{catalog}.silver.bus_routes_silver`. Row
   count must stay 20,497 (nothing dropped).
3. **`03_gold_aggregation.py`** — reads Silver, excludes the 87 placeholder rows, and
   writes two rollups: `{catalog}.gold.route_performance` (grain: corporation + Route No)
   and `{catalog}.gold.corporation_performance` (grain: corporation). EPKM/EPBD/OR are
   KM-weighted averages of the corporations' own reported ratios; Revenue/Expenditure/KM
   figures are plain sums. Also derives `revenue_loss_want_of_crew` /
   `_breakdown` / `_want_of_spares` / `_accident` / `_others` by allocating the single
   `revenue_loss_due_to_km_loss` total proportionally by each reason's share of the
   **sum of the 5 reason columns themselves** — NOT `total_km_loss` (see Gotchas below)
   — confirmed with project owner 2026-07-19 as an acceptable estimate, not a
   corporation-reported figure. `NULL` for SALEM/SETC/TIRUNELVELI/KUMBAKONAM, which
   never populate the 5 reason columns. Validation cells reconcile row counts,
   `total_revenue`, and the revenue-loss allocation (wherever tracked) back to
   Silver/itself.

All three notebooks use `dbutils.widgets` for catalog/schema names (defaults:
`workspace` catalog, `bronze`/`silver`/`gold` schemas) — override via widgets if your
workspace uses different names.

## Power BI Executive page — built this session (2026-07-19/20)

Connected via Databricks connector, **Import mode** (see Gotchas — accidentally ended
up in DirectQuery first, causing several confusing connection errors). Both
`route_performance` and `corporation_performance` loaded; almost everything on this
page is built against `route_performance` alone since it already carries
corporation/region/branch/service/category attributes at route grain.

Built so far, all on one "Executive" page (a `.pbix` file, saved locally by project
owner — not yet in this git repo since it's a binary Power BI file, not source code):
- 13 DAX measures on `route_performance` (Total Revenue, Total Expenditure, Net
  Profit or Loss, Total Operated KM, Total Passengers, Total Routes, Total KM Loss,
  Scheduled KM, Net Profit Margin %, KM Operated %, KM Loss %, EPKM (w) — KM-weighted,
  Occupancy Ratio (w/o) — KM-weighted, EPBD (w) — KM-weighted, Revenue Loss due to KM
  Loss). Weighted-ratio measures use the same
  `SUMX(value*weight)/SUM(weight)` pattern as the Gold notebook so they re-aggregate
  correctly regardless of how a visual groups/filters.
- 8 KPI cards, 8 slicers (Corporation/Region/Branch/Service Type/Category/Schedule
  Type/Origin/Destination, dropdown style).
- Revenue by Region (donut), Top 5 Branches by Revenue (bar), Revenue by Service Type
  (donut), Revenue by Service Category SCH/SPL (bar).
- KM Performance: Scheduled KM + KM Loss cards, plus a gauge on `KM Operated %`
  (min 0 / max 120 — some corporations exceed 100% scheduled KM).
- Top 5 Profit Routes / Top 5 Loss Routes tables — Top N / Bottom N filter on
  `route_no`, ranked by `Net Profit or Loss`. **Known limitation**: `route_no` isn't
  unique across corporations, so these occasionally show a few more than 5 rows when a
  route number ties across corporations (e.g. showed 8 instead of 5 once). Attempted a
  `RANKX(ALL(corporation_code, route_no), ...)` measure + advanced filter to fix this
  properly but abandoned it after repeated Databricks connection errors mid-build
  (see Gotchas) — left as a cosmetic imperfection for now, not a data-correctness issue.
- KM Loss by Reason / Revenue Loss by Reason (2 separate bar charts, not one combined
  table like the original reference dashboard — building a single table needed a
  Power Query merge-queries step across two unpivoted queries, judged not worth the
  complexity for a first build). Built via two new Power Query queries
  (`KM Loss by Reason`, `Revenue Loss by Reason`), each a duplicate of
  `route_performance` trimmed to just the 5 reason columns, unpivoted, and
  relabeled via Replace Values. **Note**: `Revenue Loss by Reason`'s total is smaller
  than the overall revenue-loss figure, since 4 of 8 corporations don't report a
  reason breakdown at all (same gap as the Gold-layer allocation, §3.2).
- Revenue per Bus per Day / Earnings per KM / Operating Ratio — each Top 5 (by branch
  or route) bar charts using the weighted measures above.
- Revenue Loss due to KM Loss by branch — combo chart (bars = `Total KM Loss`, line =
  `Revenue Loss due to KM Loss`), Top 5 branches by KM loss.
- **Dropped from the original reference dashboard**: all "vs Mar 2026" deltas and the
  12-month trend line — source data is a single reporting month (April 2026) only, no
  historical months exist to compare against (confirmed with project owner).

**Still pending on this page**: visual titles (list drafted, not yet applied),
final layout/alignment pass, number formatting (₹ symbol / Crore-style display).
**Not started**: every other nav page from the reference dashboard (Revenue,
Operations, Route Performance, Branch Performance, Financials, Passengers, Fleet &
Efficiency, Loss Analysis, Service Analysis, Insights, Data Dictionary).

## Gotchas hit this session (in case they resurface)

- **`DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES`** at Bronze write: almost every source
  header has a space, which Delta rejects outright. Fixed by replacing forbidden
  characters (` ,;{}()\n\t=`) with `_` in `sanitize_delta_column_name` — see commit
  `a3a81f6`.
- **`is_placeholder_route` matched 0 rows instead of 87**: assumed all 4 columns
  (`route_no`/`service`/`origin`/`destination`) held the exact same string `'ADDL'`.
  CLAUDE.md's wording ("`'ADDL'`/`'ADDITIONAL'`") actually means each column can
  independently be either word — fixed with `.isin(["ADDL", "ADDITIONAL"])` per column.
  See commit `2063243`. **If a future DQ count check fails, suspect a similar
  "columns don't hold the exact same string" issue before assuming the logic is wrong.**
- **`revenue_loss_*` allocation reconciliation `AssertionError` (max diff ~258M)**:
  first version divided each reason's revenue-loss allocation by `total_km_loss`.
  That only works if the 5 reason columns (`km_loss_want_of_crew`, etc.) sum to
  `total_km_loss` — they don't, because 4 of 8 corporations
  (SALEM/SETC/TIRUNELVELI/KUMBAKONAM) never populate those 5 columns at all (§3.2),
  so their 0-filled sum is 0 while `total_km_loss` is still real and large for them.
  Fixed by normalizing against the SUM of the 5 reason columns instead, with `NULL`
  output (not a wrong number) when that sum is 0. **Any "proportional allocation of
  total X across sub-columns" logic must normalize by the sum of those same
  sub-columns, never by a separately-reported total — the two are not guaranteed to
  match, especially where source columns are known to be sparsely populated.**
- **Power BI model silently ended up in DirectQuery mode instead of Import**, despite
  choosing Import at connection time. Symptom: intermittent, confusing Databricks
  errors while building visuals/measures — `[Expression.Error] We couldn't fold the
  expression to the data source`, and later `The operation was cancelled because of
  locking conflicts` — neither of which should happen once data is actually cached
  locally in Import mode. Power Query's Unpivot step then explicitly refused with
  "not supported in DirectQuery mode," which is what surfaced the real cause. Fixed
  via Model view → select each table → Properties pane → **Storage mode** → Import
  (after first using Close & Apply in Power Query Editor to clear any pending query
  changes, otherwise the switch itself errors with "please apply or discard the
  pending query changes"). **If Databricks-connected visuals throw ODBC/fold/locking
  errors that seem to make no sense for cached Import data, check Storage mode first
  before debugging anything else.**
- **Top N filter on `route_no` shows more than N rows**: `route_no` isn't unique
  across corporations (the same route number can exist in different corporations as
  unrelated routes), so Top N ranks by route-number value and lets every corporation
  sharing a top value through — e.g. asked for Top 5, got 8. A `RANKX(ALL(
  corporation_code, route_no), [measure], , DESC)` measure + an advanced ("is less
  than or equal to 5") filter ranks the (corporation, route) combination correctly
  instead, but building/testing it kept triggering the DirectQuery-mode connection
  errors above mid-session, so it was abandoned in favor of the simpler
  (occasionally-over-5-rows) Top N approach for now. Worth retrying now that Storage
  mode is confirmed fixed.

## Next session: pick up here

1. Re-run all 3 notebooks top-to-bottom in Databricks if the workspace/tables were reset,
   and confirm the validation cells all pass (row counts, `is_placeholder_route` = 87,
   `invalid_interstate_code` = 6, revenue reconciliation).
2. Finish polishing the Power BI Executive page: apply visual titles, layout/alignment
   pass, number formatting — see "Power BI Executive page" section above for what's
   built and what's left.
3. Optionally retry the `RANKX`-based exact-Top-5 fix for the profit/loss route tables
   now that Storage mode is confirmed Import (see Gotchas).
4. Design/build the remaining dashboard pages (Revenue, Operations, Route Performance,
   Branch Performance, Financials, Passengers, Fleet & Efficiency, Loss Analysis,
   Service Analysis, Insights, Data Dictionary) from the reference dashboard's left nav.
5. Start on the remaining manager-facing deliverables in `docs/` — Charter, PDD,
   Executive Summary, Dashboard User Guide, Final Deck.
