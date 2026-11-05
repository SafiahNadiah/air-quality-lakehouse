# Malaysia Air Quality Lakehouse

A Databricks medallion pipeline (bronze, silver, gold) that turns Malaysia's monthly air pollution open data into a star schema, validates it with data quality checks, and serves it through BigQuery and a Looker Studio dashboard.

**Dashboard:** [Air Quality Dashboard (PDF)](screenshots/07_Air_Quality_Dashboard.pdf)

## Problem

Monthly air pollution data is published as a flat CSV with missing values and partial years. Analysts need a clean, trustworthy model they can query for trends, worst months and year-over-year changes, and they need to know where the data is incomplete.

## Data source

| | |
|---|---|
| Dataset | Monthly Air Pollution |
| Publisher | Department of Environment Malaysia and Department of Statistics Malaysia, via [data.gov.my](https://data.gov.my/data-catalogue/air_pollution) |
| Download | https://storage.data.gov.my/environment/air_pollution.csv |
| Content | Monthly average concentrations, tabulated from hourly station readings across Malaysia |
| Pollutants | CO, NO2, O3, SO2 (ppm); PM10, PM2.5 (µg/m³) |
| Coverage | Monthly, 2017 to 2024 (data as of 31 Dec 2024) |
| Licence | Creative Commons Attribution 4.0 (CC BY 4.0) |

Known gaps in the source: a small number of 2017 values are null, and all CO values for 2024 are null.

## Architecture

```mermaid
flowchart LR
    A[data.gov.my CSV] --> B[Bronze<br/>raw ingest]
    B --> C[Silver<br/>cleaned, one row per<br/>month and pollutant]
    C --> D[Gold<br/>star schema + aggregate]
    D --> E[Data quality checks]
    D --> F[Analysis queries]
    D -->|Python sync script| G[BigQuery]
    D -->|CSV export| I[SQLite copy]
    I --> J[MCP server]
    G --> H[Looker Studio dashboard]
```

Processing runs on Databricks Free Edition (serverless) using SQL and Python. Tables live in `workspace.air_quality`.

## Notebooks

| Notebook | Purpose |
|---|---|
| `01_bronze_ingest` | Read the raw CSV from a Unity Catalog volume and land it in a Delta table with every column as a string, plus audit columns (`_ingested_at`, `_source_file`). Only change: `date` is renamed `reading_date` |
| `02_silver_clean` | Parse dates, standardise pollutant codes (`PM 10` becomes `PM10`), turn empty values into `NULL` flagged by `is_missing` (no values are invented), and keep one row per month and pollutant (latest ingested) |
| `03_gold_star_schema` | Build dimension, fact and aggregate tables |
| `04_data_quality_checks` | Run 9 validation checks and store the results |
| `05_analysis_queries` | Trend, ranking and rolling-average queries |
| `06_anomaly_detection` | Flag unusual months in the PM2.5 and NO2 series (robust z-score and Isolation Forest) |

Run order is 01 to 06 (notebook 04 reads the gold tables), either by hand or through the Workflows job below.

Record counts: bronze **576** rows (96 months x 6 pollutants), silver **576** rows (the row-count check confirms no rows were lost), gold fact **542** rows (the 576 silver rows minus 34 months without a measurement).

## Orchestration

The six notebooks run as one Databricks Workflows job (`air_quality_pipeline`) with task dependencies: bronze, silver, gold, data quality, analysis, anomaly detection. A critical data quality failure raises an exception, so the downstream tasks do not run. The job is started manually and is not on a schedule.

![Databricks workflow](screenshots/10_databricks_workflow.png)

## Gold layer: star schema

| Table | Type | Grain |
|---|---|---|
| `gold_dim_date` | dimension | one row per month |
| `gold_dim_pollutant` | dimension | one row per pollutant |
| `gold_fact_air_quality` | fact | one row per month and pollutant that has a measurement |
| `gold_agg_yearly` | aggregate | one row per year and pollutant |
| `gold_dq_results` | data quality | one row per check |
| `gold_dq_completeness` | data quality | missing-month report |

```mermaid
erDiagram
    gold_dim_date ||--o{ gold_fact_air_quality : date_key
    gold_dim_pollutant ||--o{ gold_fact_air_quality : pollutant_key
    gold_fact_air_quality {
        int date_key
        int pollutant_key
        double concentration
    }
```

Design decisions:
- **Full monthly calendar** in `gold_dim_date`, so months without data are still visible and can be reported.
- **Missing months are not loaded into the fact table.** They are reported in the data quality notebook instead.
- **`months_with_data`** in the yearly aggregate shows how complete each year is.
- Notebooks use `CREATE OR REPLACE TABLE`, so they can be re-run safely.

![Gold tables](screenshots/02_lakehouse_tables_catalog.png)

## Data quality

`04_data_quality_checks` runs 9 checks. Each check counts the rows that violate a rule, and zero violations means PASS.

- **Critical** checks fail the job (the notebook raises an exception) when violations are found.
- **Warning** checks are recorded but do not stop the pipeline.
- Results are appended to `gold_dq_results`, so every run is kept as history.

All 7 critical checks pass; 2 warnings are raised on purpose for review.

| Check | Severity | Status | What it verifies |
|---|---|---|---|
| `bronze_silver_rowcount_match` | critical | PASS | No rows lost or duplicated between bronze and silver |
| `no_duplicate_month_pollutant` | critical | PASS | One row per month and pollutant |
| `dates_parsed` | critical | PASS | Every date string was parsed |
| `dates_are_first_of_month` | critical | PASS | Monthly data is dated on the 1st |
| `no_negative_concentration` | critical | PASS | A concentration cannot be negative |
| `pollutants_exist_in_dimension` | critical | PASS | Every pollutant is described in `gold_dim_pollutant` |
| `fact_matches_silver` | critical | PASS | Fact table holds exactly the non-missing silver rows |
| `missing_values` | warning | WARN | Months without a measurement (see `gold_dq_completeness`) |
| `extreme_values_z_gt_3` | warning | WARN | Values more than 3 standard deviations from the pollutant mean (could be real events) |

The two warnings reflect properties of the source data (null values, genuine extreme readings), not pipeline errors.

![Data quality checks](screenshots/03_data_quality_checks.png)

## Analysis

Queries are in [`bigquery/`](bigquery/) (BigQuery SQL) and in notebook `05_analysis_queries` (Databricks SQL):

1. `01_pm25_monthly_trend.sql`: PM2.5 monthly trend
2. `02_top5_worst_months_per_pollutant.sql`: five worst months per pollutant
3. `03_no2_april_2020_vs_other_aprils.sql`: NO2 in April 2020 compared with other Aprils
4. `04_pm25_rolling_3m_average.sql`: three-month rolling average of PM2.5

Example findings:
- CO peaked in **September 2019** at 0.888 ppm.
- PM2.5 yearly average rose from 16.25 µg/m³ in 2018 to 20.49 in 2019, then fell to 12.29 in 2020, about **-40%** year over year.

![Top 5 worst months](screenshots/05_top5_worst_months_per_pollutant.png)

## Anomaly detection (learning project)

Notebook `06_anomaly_detection` flags unusual months in the PM2.5 and NO2 series using two simple, unsupervised methods: a **robust z-score** (median and MAD, flag when |z| > 3.5) and an **Isolation Forest** (scikit-learn, most isolated 5% of months). Results are saved to `gold_anomalies`.

Ten months were flagged, and four were flagged by both methods:

| Pollutant | Month | Value | Robust z |
|---|---|---|---|
| PM2.5 | 2019-09 | 52.86 µg/m³ | 14.2 |
| PM2.5 | 2019-08 | 31.74 µg/m³ | 6.5 |
| PM2.5 | 2018-08 | 25.84 µg/m³ | 4.4 |
| NO2 | 2020-04 | 0.0032 ppm | -3.8 |

The PM2.5 peak in August and September 2019 lines up with the CO peak in September 2019 (query 2), and the NO2 low in April 2020 is the lowest value in the series. These may relate to known events (the 2019 regional haze and the 2020 movement control order), but this analysis does not test that.

Limitations: the methods look at the value only and do not remove seasonality or trend, so a flagged month is a prompt to investigate, not proof of an event.

![Anomaly detection](screenshots/08_anomaly_detection.png)

## MCP server

[`mcp_server/`](mcp_server/) exposes the gold tables to AI clients through four read-only MCP tools (yearly averages, worst months, anomalies and data quality results). Inputs are validated, queries are fixed and parameterised, and the database is opened read-only. It reads a SQLite copy of the gold tables exported from Databricks, and was tested with the MCP Inspector. See [`mcp_server/README.md`](mcp_server/README.md).

## Serving layer: BigQuery and Looker Studio

The gold tables were first exported to CSV from Databricks and loaded into a BigQuery dataset (`air_quality`) by hand using the BigQuery sandbox. A Looker Studio dashboard reads `gold_agg_yearly` from that dataset and shows the yearly trend per pollutant, year-over-year change and data completeness.

![BigQuery dataset](screenshots/04_bigquery_dataset.png)

### Databricks to BigQuery sync

[`sync/export_to_bigquery.py`](sync/export_to_bigquery.py) replaces the manual export. It reads the four gold star-schema tables from Databricks through a SQL warehouse and loads them into the BigQuery dataset `air_quality_auto` with one command, replacing the previous copy. Credentials come from environment variables, never from the code. It runs from a local machine, not on a schedule, and the dashboard still reads the original `air_quality` dataset.

![Synced tables in BigQuery](screenshots/11_databricks_to_bigquery.png)

## Infrastructure as code

The BigQuery dataset, a table schema and a read-only service account are defined with Terraform in [`terraform/`](terraform/): `terraform init`, `plan` and `apply` recreate them, and `terraform destroy` removes them. The service account only has read access to that one dataset. This covers the BigQuery part only (the sandbox has no billing), state is kept locally, and the table is created empty. See [`terraform/README.md`](terraform/README.md).

![Terraform apply](screenshots/09_terraform_apply.png)

## How to run

1. Download the CSV from data.gov.my (link above).
2. In Databricks, upload it to the volume `workspace.air_quality.raw` (Catalog, then Upload to this volume) as `air_pollution.csv`.
3. Run notebooks `01` to `06` in order, or create a Databricks Workflows job with one task per notebook. Every notebook can be re-run safely.
4. Optional: to copy the gold tables to BigQuery, set the environment variables described in `sync/export_to_bigquery.py` and run `python sync/export_to_bigquery.py`.

## Limitations

- Built on free tiers. The Databricks to BigQuery sync is a **single local command**, not a scheduled or cloud-hosted job, and the Looker Studio dashboard still reads the original, manually loaded dataset.
- The Workflows job is started manually and has no schedule.
- Year-over-year change is misleading for partial years (2017 and 2024); check `months_with_data`.
- Source data is national monthly averages, so station-level or daily analysis is not possible.

## Next steps

- Put the Workflows job on a schedule and trigger the BigQuery sync as part of it.
- Make the anomaly detection seasonality-aware (for example by comparing each month with the same month in other years).
- Rewrite transformations in PySpark and model the gold layer in dbt.
- Extend Terraform to the remaining tables and use a remote state backend.

## Tech stack

Databricks (serverless, Unity Catalog, Workflows), SQL, Python, scikit-learn, MCP, BigQuery, Looker Studio, Terraform, GitHub.

## Data attribution

Contains data from Department of Environment Malaysia and Department of Statistics Malaysia, published on data.gov.my under CC BY 4.0.
