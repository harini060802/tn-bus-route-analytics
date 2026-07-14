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

def clean_header_whitespace(col: str) -> str:
    """Collapse embedded newlines/repeated spaces in a source header to single spaces.

    This is the one normalization applied at Bronze, purely because Delta/Parquet
    column names can't contain newline characters. Typos, casing, and wording are
    preserved verbatim (e.g. 'Esstablishment Cost' stays as-is) — real renaming to
    canonical names happens in Silver.
    """
    return re.sub(r"\s+", " ", str(col)).strip()

ingestion_ts = datetime.now(timezone.utc)
pandas_frames = []

for filename, corporation in SOURCE_FILES.items():
    file_path = f"{volume_path}/{filename}"
    pdf = pd.read_excel(file_path, sheet_name="Sheet1")
    pdf.columns = [clean_header_whitespace(c) for c in pdf.columns]
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
