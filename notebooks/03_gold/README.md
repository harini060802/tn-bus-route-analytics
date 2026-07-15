# Gold Layer

Aggregated, business-ready tables for Power BI: route-level and corporation-level rollups of Revenue, Expenditure, Net Profit/Loss, EPKM, Occupancy Ratio (OR), and KM Loss due to non-operation. See `CLAUDE.md` §4 and §7.

Run `03_gold_aggregation.py` after Silver cleaning. Reads `silver.bus_routes_silver`, writes
two tables:
- `gold.route_performance` — grain: corporation + Route No
- `gold.corporation_performance` — grain: corporation

TIRUNELVELI's 87 `is_placeholder_route` rows are excluded from both (not real routes).
EPKM/EPBD/OR are KM-weighted averages of the corporations' own reported per-row figures,
not re-derived formulas — see the notebook's intro cell for why. Validation cells check
row counts and reconcile `total_revenue` back to Silver.
