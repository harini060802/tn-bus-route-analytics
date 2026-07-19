# Dashboard Understanding Document — TN Bus Route Analytics (Executive Page)

## 1. What This Dashboard Is

This is the first page of the Power BI dashboard built on top of the cleaned,
summarized data from Databricks (`gold.route_performance` and
`gold.corporation_performance`). It's meant to be the page someone opens first — a
single screen that answers "how did the bus network perform this month?" without
needing to dig into spreadsheets or ask anyone for numbers.

It was modeled after a reference dashboard design, adapted to fit what the actual
source data can honestly support (more on that in Section 4).

## 2. How It Connects to the Data, and Why

The dashboard connects to Databricks using **Import mode**, meaning Power BI copies
the Gold tables into its own memory rather than sending a live query to Databricks
every time someone clicks a filter.

**Why Import instead of a live connection (DirectQuery):** the Gold tables are
small — a few thousand rows, not millions — and this is a one-time monthly batch of
data, not something that changes minute-to-minute. Import mode makes every click and
filter feel instant, and doesn't require the Databricks compute (the SQL Warehouse)
to be running every time someone simply wants to look at the dashboard. The tradeoff
is that the dashboard needs a manual "Refresh" whenever the underlying Gold tables
are re-run in Databricks — an acceptable tradeoff for data that only updates once a
month, not something worth paying for constant live compute.

## 3. The Filter Bar

Across the top: Corporation, Region, Branch, Service Type, Category, Schedule Type,
Origin, Destination.

**Why these specific filters:** every one of these already exists as a column on
`gold.route_performance`, meaning any combination can be sliced without needing new
data or extra calculations. This lets whoever's using the dashboard — a manager
comparing regions, an analyst investigating one corporation, someone checking a
specific route — narrow down to exactly what they care about, and every chart and
number on the page reacts to that selection automatically. This is what turns a
static report into something people actually explore instead of just reading once.

## 4. What Was Deliberately Left Out, and Why

The reference dashboard this was modeled on included "vs last month" comparisons and
a 12-month revenue/expenditure trend line. **Those were intentionally left out of
this build.** The source data covers exactly one reporting month — April 2026 — with
no prior months ingested (this project was scoped from the start as a one-time
batch, not an ongoing monthly pipeline). Building a trend chart or a month-over-month
comparison would have meant either leaving those visuals broken, or fabricating
numbers to fill them in — neither of which belongs on a dashboard a manager is
going to make decisions from. If more months of data get ingested later, those
visuals can be added back in honestly at that point.

## 5. The KPI Cards — the "at a glance" row

Total Revenue, Total Expenditure, Net Profit or Loss, Total Operated KM, Total
Passengers, Total Routes, EPKM (Earning per KM), and Occupancy Ratio.

**Why these eight:** together they answer the first three questions anyone asks
about a transport network's performance — *is it making or losing money, is it
running as much as it's supposed to, and is it being used efficiently.* Revenue and
Expenditure set the financial baseline; Net Profit or Loss is the bottom line;
Operated KM and Total Routes describe the scale of operation; Passengers, EPKM, and
Occupancy Ratio describe how effectively that scale is being used. Someone can see
the overall health of the network in about five seconds without reading a single
chart.

## 6. Revenue Breakdown Charts (Region, Branch, Service Type, Service Category)

**Business reason:** knowing the total revenue number is useful, but knowing *where*
it's coming from is what actually drives decisions — which regions are carrying the
network, which branches are the strongest performers, whether premium services (AC
Seater/Sleeper) are pulling their weight against Ordinary services, and whether
Special (SPL) services are worth the operational overhead compared to regular
Scheduled (SCH) services. These four views let someone spot concentration (e.g. "one
region is generating a third of all revenue") or imbalance at a glance, which is the
first step toward deciding where to invest or cut back.

## 7. KM Performance (Scheduled KM / Operated KM / KM Loss + Gauge)

**Business reason:** a bus corporation's core promise is running the service it
scheduled. This section shows how much of that promise was actually kept — what
was scheduled, what was actually operated, how much was lost, and a single
percentage (the gauge) summarizing operational reliability. A number meaningfully
below 100% is a direct, quantified signal of service disruption — useful both for
identifying a problem and for tracking improvement over time once more months of
data exist.

## 8. Top 5 Profit Routes / Top 5 Loss Routes

**Business reason:** aggregate numbers hide where the real story is. A corporation
can look profitable overall while individual routes are quietly losing money, and
vice versa. These two tables surface the extremes directly — the routes worth
protecting or expanding, and the routes that need investigation (is it under-priced?
under-used? poorly scheduled?). This is the kind of view that turns into an actual
action item, not just a statistic.

**A known limitation worth being upfront about:** route numbers aren't unique across
corporations — the same route number can exist in two different corporations as
completely unrelated routes. The "Top 5" tables occasionally show a couple of extra
rows when a route number happens to tie across corporations (e.g. showing 8 rows
instead of exactly 5). This doesn't affect the correctness of *which* routes are
shown — it's a minor display quirk, not a data error — and a more precise fix
(ranking by corporation + route number together) was attempted but shelved for now
after repeated Databricks connection interruptions mid-build; it's flagged in
`PROGRESS.md` to revisit.

## 9. KM Loss by Reason / Revenue Loss by Reason

**Business reason:** knowing that KM was lost is step one; knowing *why* is what
lets a corporation actually fix it. Was it crew shortages? Breakdowns? Lack of spare
buses? Accidents? Each reason points to a completely different corrective action —
crew shortages might mean a staffing/scheduling problem, breakdowns might mean a
fleet maintenance problem, and so on. Splitting both the KM lost and the revenue lost
by reason turns a single "we lost money" statistic into a prioritized list of what to
fix first.

**An honest caveat documented here on purpose:** the source data only ever reports
one *total* revenue-loss figure — it doesn't say how much of that loss came from
each reason. To build this view, that total was split proportionally, based on each
reason's share of the kilometres lost (using the same allocation approach as the
Gold-layer data, see `docs/project_understanding_doc.md` §5.1 item 4). It's a
reasonable, transparent estimate, not a number the corporations reported directly —
worth remembering when presenting it. It's also worth noting that 4 of the 8
corporations (SALEM, SETC, TIRUNELVELI, KUMBAKONAM) don't report this reason
breakdown at all, so this view only reflects the other 4.

## 10. Revenue per Bus per Day / Earnings per KM / Operating Ratio — Top 5 (by branch/route)

**Business reason:** these three metrics answer "efficiency," not just "scale" — a
branch or route can run a lot of kilometres without actually being *good* at
generating revenue from them. Ranking the top performers on each of these three
different efficiency measures gives a rounded picture: a branch could be a top
performer on one metric and average on another, and seeing all three side by side
avoids over-crediting a branch based on a single number.

**A design choice worth explaining:** these three metrics (EPKM, EPBD, Occupancy
Ratio) were **not recalculated from scratch** using a revenue/cost formula. Instead,
the dashboard combines each corporation's own already-reported per-route figures
using a *kilometre-weighted average* — meaning a 500km route's number counts more
toward the combined figure than a 5km route's, which is the mathematically correct
way to combine ratios like this (a plain average would treat both routes equally,
which would distort the result). This mirrors exactly how the same metrics were
calculated in the Gold layer in Databricks (see `docs/project_understanding_doc.md`
§5.1), so the dashboard's numbers stay consistent with what's documented there — the
dashboard isn't inventing a new calculation, it's correctly re-aggregating the
corporations' own reported figures at whatever level (branch, route, region) someone
filters down to.

## 11. Revenue Loss due to KM Loss, by Branch

**Business reason:** this closes the loop between operational loss (KM not run) and
financial loss (revenue not earned), at the branch level — the level most people
would actually act on. Seeing both bars (KM lost) and a line (revenue lost) together,
ranked by the worst-affected branches, makes clear where operational problems are
costing the most money, which is the natural place to prioritize an intervention.

## 12. Overall: How This Helps the Business

Put together, this single page moves the conversation from *"what happened this
month"* (a number) to *"why, where, and what should we do about it"* (a set of
prioritized, drillable answers) — without anyone needing to open a spreadsheet,
write a query, or wait on a report request. Every chart on the page can be
cross-filtered by any of the 8 slicers, meaning a manager reviewing a single
region's performance, or a single corporation's, sees the exact same set of
insights scoped down automatically — the same dashboard serves both a
network-wide review and a narrow, specific investigation.

## 13. What's Not Done Yet

- **Visual titles** — a title list has been drafted for every chart/table but not
  yet applied on the canvas.
- **Layout/formatting polish** — final alignment pass, number formatting
  (currency symbol, decimal places, "Crore"-style display for Indian audiences).
- **The exact-Top-5 fix** for the route tables (Section 8's known limitation).
- **Every other page** from the reference dashboard's navigation — Revenue,
  Operations, Route Performance, Branch Performance, Financials, Passengers, Fleet
  & Efficiency, Loss Analysis, Service Analysis, Insights, Data Dictionary — only
  the Executive page exists so far.

See `PROGRESS.md` for the full technical build log, including the Databricks
connection issues hit along the way.
