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
| 6. Power BI connection via SQL Warehouse | **Not started** |
| 7. Dashboard page design | **Not started** |

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

## Next session: pick up here

1. Re-run all 3 notebooks top-to-bottom in Databricks if the workspace/tables were reset,
   and confirm the validation cells all pass (row counts, `is_placeholder_route` = 87,
   `invalid_interstate_code` = 6, revenue reconciliation).
2. Step 6: connect Power BI to the Databricks SQL Warehouse, pointing at
   `gold.route_performance` and `gold.corporation_performance` (decide Import vs
   DirectQuery — not yet decided, see `CLAUDE.md` §4 closing note).
3. Step 7: design the dashboard pages.
4. Start on the 6 manager-facing deliverables in `docs/` — the Data Quality Report can
   draw directly from `CLAUDE.md` §3.2 plus the "Gotchas" section above.
