# Silver Layer

Cleaned & conformed data: unified snake_case schema, standardized corporation/region/branch
names, standardized Yes/No/NA flags, null handling (+ `reason_tracked` flag) on the 5
non-operation-reason columns, `abs()` fix for the two known negative-value rows, and DQ flags
`is_placeholder_route` / `invalid_interstate_code`. See `CLAUDE.md` §3.2 and §4.

Run `02_silver_cleaning.py` after Bronze ingestion. Reads `bronze.bus_routes_raw`, writes
`silver.bus_routes_silver`. No rows are dropped or added — output row count must match
Bronze's 20,497 exactly.
