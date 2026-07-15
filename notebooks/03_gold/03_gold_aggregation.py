# Databricks notebook source
# MAGIC %md
# MAGIC # Gold Aggregation — TN Bus Route Analytics
# MAGIC
# MAGIC Builds the two business-ready rollups `CLAUDE.md` §4 calls for — **route-level**
# MAGIC and **corporation-level** — covering Revenue, Expenditure, Net Profit/Loss, EPKM,
# MAGIC Occupancy Ratio (OR), and KM Loss due to non-operation (§7 glossary). These are
# MAGIC what Power BI connects to; Silver stays available for row-level drill-through.
# MAGIC
# MAGIC Design notes (confirmed with project owner):
# MAGIC - **Route grain** = corporation + Route No (sums every `Service` scheduled on that
# MAGIC   route). A route number, not an individual service, is the unit a route
# MAGIC   performance dashboard should rank/filter on.
# MAGIC - **Placeholder rows excluded**: TIRUNELVELI's 87 `is_placeholder_route` rows
# MAGIC   (Route No/Service/origin/destination all `'ADDL'`/`'ADDITIONAL'`) are filtered
# MAGIC   out before aggregating — they're not real routes, and summing them in would
# MAGIC   overstate/misattribute revenue, KM, and loss totals.
# MAGIC - **EPKM / EPBD / OR are KM-weighted averages of the corporations' own reported
# MAGIC   per-row figures**, not re-derived from a revenue or capacity formula. `CLAUDE.md`
# MAGIC   §7 itself notes EPKM's `/w` vs `/wo` distinction is "some adjustment" without
# MAGIC   specifying which — we don't know precisely what each corporation's `_with` /
# MAGIC   `_without` variant divides by, so re-deriving risks numbers that don't reconcile
# MAGIC   with anything the corporations actually publish. A KM-weighted average of the
# MAGIC   already-reported ratio avoids that guess while still aggregating correctly
# MAGIC   (a 5km route's ratio doesn't get equal weight to a 500km route's).
# MAGIC - Everything else that's a genuine dollar/count total (Revenue, Expenditure, KM,
# MAGIC   passengers, KM-loss reasons) is a plain `SUM` — those are unambiguous.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
dbutils.widgets.text("silver_schema", "silver", "Silver schema")
dbutils.widgets.text("gold_schema", "gold", "Gold schema")

catalog = dbutils.widgets.get("catalog")
silver_schema = dbutils.widgets.get("silver_schema")
gold_schema = dbutils.widgets.get("gold_schema")

silver_table = f"{catalog}.{silver_schema}.bus_routes_silver"
route_table = f"{catalog}.{gold_schema}.route_performance"
corporation_table = f"{catalog}.{gold_schema}.corporation_performance"
print(f"Reading from: {silver_table}")
print(f"Writing to: {route_table}")
print(f"Writing to: {corporation_table}")

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{gold_schema}")

# COMMAND ----------

from pyspark.sql import functions as F

silver_df = spark.table(silver_table)

# Placeholder rows (TIRUNELVELI's ADDL rows) aren't real routes — exclude from both rollups.
clean_df = silver_df.filter(~F.col("is_placeholder_route"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Shared aggregation building blocks
# MAGIC Column lists + the weighted-average helper are shared by both rollups below so
# MAGIC the "what's additive vs. what's a weighted ratio" decision is made once, not
# MAGIC duplicated per grain.

# COMMAND ----------

# Plain dollar/count totals — safe to SUM at any grain.
SUM_COLUMNS = [
    "total_operated_km", "sch_km_to_be_operated", "total_km_loss",
    "km_loss_want_of_crew", "km_loss_breakdown", "km_loss_want_of_spares",
    "km_loss_accident", "km_loss_others",
    "total_not_run", "total_operated_plus_not_run_days", "days_operated",
    "sch_singles_per_day", "total_singles_operated", "total_passengers",
    "total_revenue", "opern_revenue_without_cess", "other_revenue",
    "hsd_cost", "other_vc_cost", "total_vc_cost",
    "establishment_cost", "other_establishment_cost", "total_establishment_cost",
    "other_cost", "total_expenditure",
    "net_profit_loss", "revenue_loss_due_to_km_loss",
]

# Ratio columns already reported per-row by the corporations — aggregate as a
# KM-weighted average (see notebook intro), not a re-derived formula or a naive AVG.
WEIGHTED_RATIO_COLUMNS = [
    "avg_fare_per_km",
    "epkm_with", "epkm_without",
    "epbd_with", "epbd_without",
    "occupancy_ratio_with", "occupancy_ratio_without",
]
WEIGHT_COLUMN = "total_operated_km"

# Yes/No/NA flags collapsed to a single boolean per group: true if ANY row in the
# group is 'YES'. These describe route characteristics, not values to average.
ANY_YES_COLUMNS = ["is_long_route_250km", "is_social_obligatory_route", "is_conductor_less"]


def weighted_avg_expr(metric_col, weight_col):
    """SUM(metric*weight)/SUM(weight), NULL (not divide-by-zero) when weight sums to 0."""
    total_weight = F.sum(F.col(weight_col))
    return F.when(total_weight == 0, F.lit(None)).otherwise(
        F.sum(F.col(metric_col) * F.col(weight_col)) / total_weight
    )


def any_yes_expr(flag_col):
    return F.max(F.when(F.col(flag_col) == "YES", True).otherwise(False))


def common_agg_exprs():
    """Aggregations identical across both rollups: sums, weighted ratios, any-YES flags,
    plus any-true DQ flags and post-fill non-operation-reason totals are already covered
    by SUM_COLUMNS (km_loss_*) and the reason_tracked/invalid_interstate_code any-flags."""
    exprs = [F.sum(c).alias(c) for c in SUM_COLUMNS]
    exprs += [weighted_avg_expr(c, WEIGHT_COLUMN).alias(c) for c in WEIGHTED_RATIO_COLUMNS]
    exprs += [any_yes_expr(c).alias(c) for c in ANY_YES_COLUMNS]
    exprs += [
        F.avg("route_length_km").alias("avg_route_length_km"),
        F.avg("seating_standing_capacity").alias("avg_seating_standing_capacity"),
        F.max("reason_tracked").alias("reason_tracked"),
        F.max("invalid_interstate_code").alias("invalid_interstate_code"),
        F.count(F.lit(1)).alias("num_silver_rows"),
    ]
    return exprs


def add_derived_kpis(df):
    """Post-aggregation ratios computed from already-summed additive totals — safe,
    unlike averaging pre-computed per-row ratios."""
    return (
        df.withColumn(
            "net_profit_margin_pct",
            F.when(F.col("total_revenue") == 0, None).otherwise(
                F.col("net_profit_loss") / F.col("total_revenue") * 100
            ),
        )
        .withColumn(
            "km_operated_pct",
            F.when(F.col("sch_km_to_be_operated") == 0, None).otherwise(
                F.col("total_operated_km") / F.col("sch_km_to_be_operated") * 100
            ),
        )
        .withColumn(
            "km_loss_pct",
            F.when(F.col("sch_km_to_be_operated") == 0, None).otherwise(
                F.col("total_km_loss") / F.col("sch_km_to_be_operated") * 100
            ),
        )
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## `gold.route_performance` — grain: corporation + Route No

# COMMAND ----------

route_df = clean_df.groupBy("corporation_code", "route_no").agg(
    F.first("corporation_full_name", ignorenulls=True).alias("corporation_full_name"),
    F.first("region_full_name", ignorenulls=True).alias("region_full_name"),
    F.first("branch_full_name", ignorenulls=True).alias("branch_full_name"),
    F.first("origin", ignorenulls=True).alias("origin"),
    F.first("destination", ignorenulls=True).alias("destination"),
    F.first("category", ignorenulls=True).alias("category"),
    F.first("schedule_type", ignorenulls=True).alias("schedule_type"),
    F.first("service_type", ignorenulls=True).alias("service_type"),
    F.first("inter_state_route", ignorenulls=True).alias("inter_state_route"),
    F.first("route_length_km", ignorenulls=True).alias("route_length_km"),
    F.countDistinct("service").alias("num_services"),
    *common_agg_exprs(),
)
route_df = add_derived_kpis(route_df)

(
    route_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(route_table)
)
print(f"Wrote {route_df.count()} rows to {route_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `gold.corporation_performance` — grain: corporation
# MAGIC Region/branch/category/service-type/inter-state-route are route-level attributes
# MAGIC that don't collapse meaningfully to one value per corporation, so they're dropped
# MAGIC here rather than taking an arbitrary `first()`.

# COMMAND ----------

corporation_df = clean_df.groupBy("corporation_code").agg(
    F.first("corporation_full_name", ignorenulls=True).alias("corporation_full_name"),
    F.countDistinct("route_no").alias("num_routes"),
    F.countDistinct(F.concat_ws("|", "route_no", "service")).alias("num_services"),
    *common_agg_exprs(),
)
corporation_df = add_derived_kpis(corporation_df)

(
    corporation_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(corporation_table)
)
print(f"Wrote {corporation_df.count()} rows to {corporation_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation
# MAGIC Gold never drops or double-counts rows beyond the placeholder exclusion — every
# MAGIC dollar/KM figure in Gold must reconcile exactly back to Silver's non-placeholder rows.

# COMMAND ----------

expected_routes = clean_df.select("corporation_code", "route_no").distinct().count()
expected_corporations = clean_df.select("corporation_code").distinct().count()
route_rows = spark.table(route_table).count()
corporation_rows = spark.table(corporation_table).count()

assert route_rows == expected_routes, f"Expected {expected_routes} route rows, got {route_rows}"
assert corporation_rows == expected_corporations, f"Expected {expected_corporations} corporation rows, got {corporation_rows}"
print(f"route_performance rows OK: {route_rows}")
print(f"corporation_performance rows OK: {corporation_rows}")

# COMMAND ----------

silver_total_revenue = clean_df.agg(F.sum("total_revenue")).first()[0]
route_total_revenue = spark.table(route_table).agg(F.sum("total_revenue")).first()[0]
corporation_total_revenue = spark.table(corporation_table).agg(F.sum("total_revenue")).first()[0]

assert abs(silver_total_revenue - route_total_revenue) < 1, "route_performance total_revenue doesn't reconcile with Silver"
assert abs(silver_total_revenue - corporation_total_revenue) < 1, "corporation_performance total_revenue doesn't reconcile with Silver"
print(f"Total revenue reconciles across Silver/Gold: {silver_total_revenue:,.2f}")

# COMMAND ----------

display(
    spark.table(corporation_table)
    .select(
        "corporation_code", "num_routes", "total_revenue", "total_expenditure",
        "net_profit_loss", "net_profit_margin_pct", "epkm_with", "occupancy_ratio_with",
        "km_loss_pct",
    )
    .orderBy("corporation_code")
)

display(
    spark.table(route_table)
    .orderBy(F.col("net_profit_loss").asc())
    .select("corporation_code", "route_no", "origin", "destination", "total_revenue", "net_profit_loss", "net_profit_margin_pct")
    .limit(10)
)
