# Databricks notebook source
# MAGIC %md
# MAGIC # Silver Cleaning — TN Bus Route Analytics
# MAGIC
# MAGIC Cleans and conforms the Bronze table into a unified snake_case schema, per
# MAGIC `CLAUDE.md` §3.2 and §4:
# MAGIC - Rename every column from Bronze's Delta-safe-but-literal header to a
# MAGIC   business-readable snake_case name.
# MAGIC - Standardize corporation/region/branch name casing and Yes/No/NA flags.
# MAGIC - Fill nulls on the 5 non-operation-reason columns, keeping a `reason_tracked`
# MAGIC   flag so "not tracked by this corporation" isn't confused with "zero incidents".
# MAGIC - Fix the two known physically-impossible negative values.
# MAGIC - Add DQ flags: `is_placeholder_route` (TIRUNELVELI's `ADDL` rows) and
# MAGIC   `invalid_interstate_code` (COIMBATORE's `'Y'` rows).
# MAGIC
# MAGIC No rows are dropped or added — every fix here is a rename, a value
# MAGIC normalization, or an additive flag column, so the row count must match Bronze
# MAGIC exactly (20,497).

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
dbutils.widgets.text("bronze_schema", "bronze", "Bronze schema")
dbutils.widgets.text("silver_schema", "silver", "Silver schema")

catalog = dbutils.widgets.get("catalog")
bronze_schema = dbutils.widgets.get("bronze_schema")
silver_schema = dbutils.widgets.get("silver_schema")

bronze_table = f"{catalog}.{bronze_schema}.bus_routes_raw"
silver_table = f"{catalog}.{silver_schema}.bus_routes_silver"
print(f"Reading from: {bronze_table}")
print(f"Writing to: {silver_table}")

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{silver_schema}")

# COMMAND ----------

from functools import reduce
from pyspark.sql import functions as F

bronze_df = spark.table(bronze_table)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Rename to a unified snake_case schema
# MAGIC
# MAGIC Bronze columns are only sanitized enough to satisfy Delta's naming rules (see
# MAGIC `01_bronze_ingestion.py`'s `sanitize_delta_column_name`) — they still carry the
# MAGIC source spreadsheets' verbatim wording/typos (e.g. `Esstablishment_Cost`,
# MAGIC `Total_Singles_actualy_operated`). This map is hand-built against `CLAUDE.md`
# MAGIC §3.1's canonical meanings, because turning `Esstablishment_Cost` into
# MAGIC `establishment_cost` is a business rename, not a mechanical transform — unlike
# MAGIC Bronze's sanitization, it can't be derived programmatically from the header text.

# COMMAND ----------

RENAME_MAP = {
    "No": "sl_no",
    "Corporation_Full_Name": "corporation_full_name",
    "Region_Full_name": "region_full_name",
    "Branch_full_name": "branch_full_name",
    "Category_Enter_Town/_Mof_/_Ghat": "category",
    "Schedule_/_Special_Enter_SCH/SPL": "schedule_type",
    "Route_No": "route_no",
    "Service": "service",
    "origin": "origin",
    "destination": "destination",
    "Type_of_Service_ORD_/_EXP_/_DLX_/_UD_/_AC_Seater_/_AC_Sleeper_/_Non_AC_sleeper_/_Multi_axle": "service_type",
    "More_than_250_KM_Route_length_Board_route_Yes_/_No": "is_long_route_250km",
    "Social_Oblicatory_Route_Yes_/_No": "is_social_obligatory_route",
    "Conductor_less_operation_Yes/_No": "is_conductor_less",
    "Peak_hour_service_4+_4_8hrs_/_12hrs_/_NA": "peak_hour_service",
    "Inter_state_route_AP_/_KA_/_KL_/_PY_/_TN": "inter_state_route",
    "Average_Fare_per_KM": "avg_fare_per_km",
    "Seating_+_Standing_Capacity": "seating_standing_capacity",
    "Route_Length": "route_length_km",
    "No._of_Schedule_Singles_per_day": "sch_singles_per_day",
    "Schedule_KM_per_day_per_bus": "sch_km_per_day_per_bus",
    "Total_Singles_actualy_operated": "total_singles_operated",
    "No.of_days_actualy_operated": "days_operated",
    "Want_of_Crew": "km_loss_want_of_crew",
    "Break_down": "km_loss_breakdown",
    "Want_of_Spares": "km_loss_want_of_spares",
    "Accident": "km_loss_accident",
    "Others": "km_loss_others",
    "Total_Not_run": "total_not_run",
    "Total_Operated_+_Not_Run_days": "total_operated_plus_not_run_days",
    "Total_KM_Loss_in_April-2026_if_any": "total_km_loss",
    "Total_Operated_KM": "total_operated_km",
    "Opern._Revenue_with_out_cess": "opern_revenue_without_cess",
    "Other_Revenue_Including_Reimbursement_Subsidy_Grant": "other_revenue",
    "Total_Revenue": "total_revenue",
    "HSD_Cost": "hsd_cost",
    "Other_V.C": "other_vc_cost",
    "Total_VC_Cost": "total_vc_cost",
    "Esstablishment_Cost": "establishment_cost",
    "Other_Esstablishment_Cost": "other_establishment_cost",
    "Esst_+_Other_Esst": "total_establishment_cost",
    "Other_Cost_includes_depreciation_intrest_MV_tax_etc": "other_cost",
    "Total_Expenditure": "total_expenditure",
    "Net_Profit_/_Loss_Apr-2026": "net_profit_loss",
    "Total_passenger_travelled_in_Apr-2026": "total_passengers",
    "Earning_per_KM_EPKM_/w": "epkm_with",
    "Earning_per_bus_per_day_EPBD_/w": "epbd_with",
    "OR/w": "occupancy_ratio_with",
    "Earning_per_KM_EPKM_/wo": "epkm_without",
    "Earning_per_bus_per_day_EPBD_/wo": "epbd_without",
    "OR/wo": "occupancy_ratio_without",
    "REVENUE_LOSS_DUE_TO_KM_LOSS": "revenue_loss_due_to_km_loss",
    "sch.km_to_be_operated": "sch_km_to_be_operated",
    # SALEM/SETC only (~21-22% of rows); NULL for the other 6 corporations because
    # Bronze's unionByName(allowMissingColumns=True) fills it in. No business meaning
    # assigned — carried through as a generic nullable value per CLAUDE.md §3.2.
    "Unnamed:_53": "unlabeled_value_54",
    "_source_file": "source_file",
    "_corporation_raw": "corporation_code",
    "_ingestion_ts": "ingestion_ts",
}

# Fail loudly on any mismatch rather than silently leaving a column under its old
# Bronze name (unmapped) or silently no-op'ing a typo'd map key (extra_keys) — either
# would slip through withColumnRenamed without error otherwise.
unmapped = [c for c in bronze_df.columns if c not in RENAME_MAP]
extra_keys = [k for k in RENAME_MAP if k not in bronze_df.columns]
if unmapped or extra_keys:
    raise ValueError(
        f"RENAME_MAP is out of sync with bronze_df.columns. "
        f"Bronze columns missing from RENAME_MAP: {unmapped}. "
        f"RENAME_MAP keys not found in Bronze: {extra_keys}."
    )

silver_df = bronze_df
for bronze_col, silver_col in RENAME_MAP.items():
    silver_df = silver_df.withColumnRenamed(bronze_col, silver_col)

print(f"Renamed {len(RENAME_MAP)} columns to snake_case.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Normalize corporation / region / branch text fields
# MAGIC `CLAUDE.md` §3.2: inconsistent casing/spacing (e.g. `'VILLUPURAM '` with a
# MAGIC trailing space vs `'MTC'`) needs `.strip()` + uppercase normalization.

# COMMAND ----------

for c in ["corporation_full_name", "region_full_name", "branch_full_name", "corporation_code"]:
    silver_df = silver_df.withColumn(c, F.trim(F.upper(F.col(c))))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Standardize Yes/No/NA flag columns
# MAGIC `is_long_route_250km`, `is_social_obligatory_route`, `is_conductor_less` collapse
# MAGIC to exactly `'YES'` / `'NO'` / `'NA'` regardless of source casing/blank/null.
# MAGIC `inter_state_route` only gets null→`'NA'`; its actual values are left as-is per
# MAGIC the DQ resolution (COIMBATORE's invalid `'Y'` rows are flagged, not guessed at).

# COMMAND ----------

def standardize_yes_no_na(col_name):
    normalized = F.trim(F.upper(F.col(col_name)))
    return (
        F.when(normalized == "NA", F.lit("NA"))
        .when(normalized.startswith("Y"), F.lit("YES"))
        .when(normalized.startswith("N"), F.lit("NO"))
        .otherwise(F.lit("NA"))  # covers null, blank, and any unrecognized value
    )

YES_NO_NA_COLUMNS = ["is_long_route_250km", "is_social_obligatory_route", "is_conductor_less"]
for c in YES_NO_NA_COLUMNS:
    silver_df = silver_df.withColumn(c, standardize_yes_no_na(c))

# COMMAND ----------

interstate_trimmed = F.trim(F.col("inter_state_route"))
silver_df = silver_df.withColumn(
    "inter_state_route",
    F.when((interstate_trimmed.isNull()) | (interstate_trimmed == ""), F.lit("NA")).otherwise(interstate_trimmed),
)

# `Inter state route` DQ flag: COIMBATORE has 6 rows with value 'Y', not in the
# AP/KA/KL/PY/TN/NA vocabulary. Leave the value as-is (don't guess which state), just flag it.
VALID_INTERSTATE_CODES = ["AP", "KA", "KL", "PY", "TN", "NA"]
silver_df = silver_df.withColumn(
    "invalid_interstate_code", ~F.col("inter_state_route").isin(VALID_INTERSTATE_CODES)
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Non-operation-reason columns: null handling + `reason_tracked` flag
# MAGIC `CLAUDE.md` §3.2: null in these 5 columns means "not tracked by this
# MAGIC corporation," not "zero incidents" — so the flag is computed from nullability
# MAGIC *before* the fill, then the columns are 0-filled for aggregation math.

# COMMAND ----------

REASON_COLUMNS = [
    "km_loss_want_of_crew",
    "km_loss_breakdown",
    "km_loss_want_of_spares",
    "km_loss_accident",
    "km_loss_others",
]

reason_tracked_expr = reduce(
    lambda acc, c: acc | F.col(c).isNotNull(),
    REASON_COLUMNS[1:],
    F.col(REASON_COLUMNS[0]).isNotNull(),
)
silver_df = silver_df.withColumn("reason_tracked", reason_tracked_expr)
silver_df = silver_df.fillna(0, subset=REASON_COLUMNS)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Fix known physically-impossible negative values
# MAGIC `CLAUDE.md` §3.2: SALEM `sl_no=1840` (route P02) has `total_passengers` = -7876;
# MAGIC COIMBATORE `sl_no=2080` (route 89) has `route_length_km` = -158. Neither metric
# MAGIC can legitimately be negative, so `abs()` is applied column-wide (not just to
# MAGIC these two known rows) — assumes sign was a data-entry error, magnitude correct.

# COMMAND ----------

silver_df = silver_df.withColumn("total_passengers", F.abs(F.col("total_passengers")))
silver_df = silver_df.withColumn("route_length_km", F.abs(F.col("route_length_km")))

# COMMAND ----------

# MAGIC %md
# MAGIC ## `is_placeholder_route` flag
# MAGIC TIRUNELVELI has 87 rows where `Route No`, `Service`, `origin`, and `destination`
# MAGIC are all literally `'ADDL'`/`'ADDITIONAL'` — not real routes. Flagged (not
# MAGIC dropped) so Gold-layer route analysis can exclude/segregate them as needed.

# COMMAND ----------

silver_df = silver_df.withColumn(
    "is_placeholder_route",
    (F.upper(F.trim(F.col("route_no"))) == "ADDL")
    & (F.upper(F.trim(F.col("service"))) == "ADDL")
    & (F.upper(F.trim(F.col("origin"))) == "ADDL")
    & (F.upper(F.trim(F.col("destination"))) == "ADDL"),
)

# COMMAND ----------

silver_df = silver_df.withColumn("silver_processed_ts", F.current_timestamp())

# COMMAND ----------

(
    silver_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(silver_table)
)

print(f"Wrote {silver_df.count()} rows to {silver_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation
# MAGIC Row count must equal Bronze's 20,497 — Silver only renames/normalizes/flags,
# MAGIC it never filters rows.

# COMMAND ----------

row_count = spark.table(silver_table).count()
expected_row_count = 3847 + 1902 + 612 + 1692 + 4234 + 2559 + 3492 + 2159
assert row_count == expected_row_count, f"Expected {expected_row_count} rows, got {row_count}"
print(f"Row count OK: {row_count}")

display(spark.table(silver_table).groupBy("corporation_code").count().orderBy("corporation_code"))

# COMMAND ----------

# MAGIC %md
# MAGIC Spot-check the two negative-value fixes.

# COMMAND ----------

display(
    spark.table(silver_table)
    .filter((F.col("corporation_code") == "SALEM") & (F.col("sl_no") == 1840))
    .select("sl_no", "route_no", "total_passengers")
)

display(
    spark.table(silver_table)
    .filter((F.col("corporation_code") == "COIMBATORE") & (F.col("sl_no") == 2080))
    .select("sl_no", "route_no", "route_length_km")
)

# COMMAND ----------

# MAGIC %md
# MAGIC DQ flag counts should match the known figures from `CLAUDE.md` §3.2:
# MAGIC `is_placeholder_route` → 87 (TIRUNELVELI), `invalid_interstate_code` → 6 (COIMBATORE).

# COMMAND ----------

placeholder_count = spark.table(silver_table).filter(F.col("is_placeholder_route")).count()
invalid_interstate_count = spark.table(silver_table).filter(F.col("invalid_interstate_code")).count()
print(f"is_placeholder_route rows: {placeholder_count} (expect 87)")
print(f"invalid_interstate_code rows: {invalid_interstate_count} (expect 6)")

display(spark.table(silver_table).filter(F.col("is_placeholder_route")).limit(5))
display(spark.table(silver_table).filter(~F.col("reason_tracked")).limit(5))
