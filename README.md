# TN Bus Route Analytics

Route-level analytics project for 8 Tamil Nadu state bus corporations, built as a portfolio project demonstrating a Databricks medallion pipeline (Bronze → Silver → Gold) with a Power BI dashboard connected live via Databricks SQL Warehouse.

See `CLAUDE.md` for full project context, tech stack, data quality notes, and working agreement.

## Repo Structure

```
data/raw/       — source Excel files (local only, not committed — see data/raw/README.md)
notebooks/      — Bronze / Silver / Gold Databricks notebooks
docs/           — manager-facing deliverables (charter, PDD, DQ report, exec summary, guide, deck)
powerbi/        — Power BI dashboard file(s)
```

## Workflow

1. Scope note — done
2. GitHub repo structure — done
3. Bronze ingestion notebook(s) — done
4. Silver cleaning layer notebook(s) — done
5. Gold aggregation layer notebook(s) — done
6. Power BI connection via Databricks SQL Warehouse
7. Dashboard page design

See `PROGRESS.md` for a working log of what's done, key decisions, and where to pick up next.
