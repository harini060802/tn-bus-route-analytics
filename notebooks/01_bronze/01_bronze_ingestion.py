# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze Ingestion — TN Bus Route Analytics
# MAGIC
# MAGIC One-time manual batch ingestion of the 8 source Excel files (one per bus corporation)
# MAGIC into a single Bronze Delta table. No business-rule transformation happens here —
# MAGIC see `CLAUDE.md` §4. Each row is tagged with its source file and corporation, plus an
# MAGIC ingestion timestamp, so Silver/Gold can always trace a row back to its origin.
# MAGIC
# MAGIC Source data quality context: `CLAUDE.md` §3.2.

# COMMAND ----------

# MAGIC %pip install openpyxl

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
dbutils.widgets.text("schema", "bronze", "Schema")
dbutils.widgets.text("volume_path", "/Volumes/workspace/bronze/raw_data", "Volume path (raw Excel files)")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume_path = dbutils.widgets.get("volume_path")

bronze_table = f"{catalog}.{schema}.bus_routes_raw"
print(f"Target table: {bronze_table}")
print(f"Reading files from: {volume_path}")

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")

# COMMAND ----------

# Source files: filename -> corporation tag. Corporation tag is deliberately raw here
# (casing/spacing not yet normalized) — that normalization is a Silver-layer step
# (CLAUDE.md §3.2), not a Bronze one.
SOURCE_FILES = {
    "MTC.xlsx": "MTC",
    "SALEM.xlsx": "SALEM",
    "SETC.xlsx": "SETC",
    "TIRUNELVELI.xlsx": "TIRUNELVELI",
    "VILLUPURAM.xlsx": "VILLUPURAM",
    "coimbatore.xlsx": "COIMBATORE",
    "kumbakonam.xlsx": "KUMBAKONAM",
    "madurai.xlsx": "MADURAI",
}

# COMMAND ----------

import pandas as pd
import re
from datetime import datetime, timezone

DELTA_INVALID_CHARS = re.compile(r"[ ,;{}()\n\t=]")

def sanitize_delta_column_name(col: str) -> str:
    """Make a source header safe as a Delta column name, without renaming to canonical names.

    Delta rejects column names containing any of ' ,;{}()\n\t=' (raises
    DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES) unless column mapping is enabled — and
    almost every source header here has at least a space (e.g. even 'Route No' is
    invalid as-is). Each forbidden character is replaced with '_', runs of '_' are
    collapsed, and leading/trailing '_' are stripped. This is a storage-compatibility
    fix only — typos, casing, and wording are preserved verbatim (e.g. 'Esstablishment
    Cost' stays as-is, just with the space swapped for '_'); real renaming to canonical
    §3.1 names happens in Silver.
    """
    collapsed = re.sub(r"\s+", " ", str(col)).strip()
    sanitized = DELTA_INVALID_CHARS.sub("_", collapsed)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized

def safe_to_str(value):
    """Coerce a mixed-type cell (str/int/float) to a single consistent string type.

    Whole-number floats (e.g. 504.0) are rendered as '504', not '504.0', so a
    route logged as an int in one row and a float in another still lands on
    the same string.
    """
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)

# Columns that are unsafe to let Spark/Arrow auto-infer a dtype for, in two
# distinct ways found by profiling every column's Python types across all 8
# files (re-run scratchpad/check_mixed_types.py- and check_all_categorical.py-
# style checks on any new source file before assuming this list is complete):
#
#   1. Mixed str/int/float WITHIN one file: Route No, Service
#      (e.g. Route No has '14M' (str) and 504 (int) side by side)
#   2. Consistent type WITHIN each file, but the type DIFFERS ACROSS files —
#      e.g. Inter state route is 100% null in MTC (pandas/Arrow infers
#      NullType/DoubleType there) but genuine strings ('TN', 'KA'...) in every
#      other file; Peak hour service holds decimal-hour floats in SALEM
#      (9.55, 12.0) but text ('NO', '12hrs') elsewhere. unionByName then tries
#      to widen to a common type and throws
#      [CAST_INVALID_INPUT] "The value 'NO' ... cannot be cast to DOUBLE".
#      Social Oblicatory Route hits the same all-null-in-one-file trap (SETC).
#
# Either failure mode is a PySpark/Arrow type-inference limitation, not a
# business rule — so every column below is force-cast to pandas' nullable
# StringDtype (not just Python str) so Arrow always infers STRING for it, in
# every file, even when a given file's column is 100% null.
# Written as the raw source headers and sanitized the same way the columns themselves
# are (rather than hand-transcribed) so this list can't drift out of sync with the
# actual post-sanitization column names.
FORCE_STRING_COLUMNS = [
    sanitize_delta_column_name(c)
    for c in [
        "Route No",
        "Service",
        "Social Oblicatory Route (Yes / No)",
        "Peak hour service (4+ 4 = 8hrs) / 12hrs / NA",
        "Inter state route (AP / KA / KL / PY / TN)",
    ]
]

ingestion_ts = datetime.now(timezone.utc)
pandas_frames = []

for filename, corporation in SOURCE_FILES.items():
    file_path = f"{volume_path}/{filename}"
    pdf = pd.read_excel(file_path, sheet_name="Sheet1")
    pdf.columns = [sanitize_delta_column_name(c) for c in pdf.columns]
    for col in FORCE_STRING_COLUMNS:
        if col in pdf.columns:
            pdf[col] = pdf[col].map(safe_to_str).astype("string")
    pdf["_source_file"] = filename
    pdf["_corporation_raw"] = corporation
    pdf["_ingestion_ts"] = ingestion_ts
    pandas_frames.append(pdf)
    print(f"{corporation}: {pdf.shape[0]} rows, {pdf.shape[1]} columns read from {filename}")

# COMMAND ----------

# Convert each pandas frame to Spark individually, then union by name allowing
# missing columns — SALEM/SETC have an extra unlabeled 54th column the other
# 6 files don't (CLAUDE.md §3.2); this fills it with NULL for those files
# rather than dropping or renaming it.
bronze_df = None
for pdf in pandas_frames:
    sdf = spark.createDataFrame(pdf)
    bronze_df = sdf if bronze_df is None else bronze_df.unionByName(sdf, allowMissingColumns=True)

print(f"Combined row count: {bronze_df.count()}")
display(bronze_df.groupBy("_corporation_raw").count().orderBy("_corporation_raw"))

# COMMAND ----------

(
    bronze_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(bronze_table)
)

print(f"Wrote {bronze_df.count()} rows to {bronze_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation
# MAGIC Row counts per corporation should match `CLAUDE.md` §3: MTC 3847, SALEM 1902, SETC 612,
# MAGIC TIRUNELVELI 1692, VILLUPURAM 4234, COIMBATORE 2559, KUMBAKONAM 3492, MADURAI 2159.

# COMMAND ----------

display(spark.table(bronze_table).groupBy("_corporation_raw").count().orderBy("_corporation_raw"))

# COMMAND ----------

display(spark.table(bronze_table).limit(5))
