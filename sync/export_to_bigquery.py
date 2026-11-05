"""Copy the gold tables from Databricks to BigQuery with one command.

Reads from Databricks through a SQL warehouse and loads each table into a BigQuery
dataset (replacing the previous copy). Credentials come from environment variables,
never from the code.

Setup (once):
    pip install databricks-sql-connector google-cloud-bigquery pandas pyarrow db-dtypes
    gcloud auth application-default login

Environment variables (PowerShell example):
   $env:DATABRICKS_HOST = "dbc-xxxx..."
   $env:DATABRICKS_HTTP_PATH = "/sql/.."
   $env:DATABRICKS_TOKEN = "dap..."
Optional:
    $env:BQ_PROJECT = "air-quality-portfolio"
    $env:BQ_DATASET = "air_quality_auto"

Run:
    python export_to_bigquery.py
"""
import os
import sys

from databricks import sql
from google.cloud import bigquery

CATALOG = "workspace"
SCHEMA = "air_quality"
TABLES = [
    "gold_dim_date",
    "gold_dim_pollutant",
    "gold_fact_air_quality",
    "gold_agg_yearly",
]


def need(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing environment variable: {name}")
    return value


def read_table(cursor, table):
    cursor.execute(f"SELECT * FROM {CATALOG}.{SCHEMA}.{table}")
    return cursor.fetchall_arrow().to_pandas()


def main():
    host = need("DATABRICKS_HOST")
    http_path = need("DATABRICKS_HTTP_PATH")
    token = need("DATABRICKS_TOKEN")
    project = os.environ.get("BQ_PROJECT", "air-quality-portfolio")
    dataset = os.environ.get("BQ_DATASET", "air_quality_auto")

    client = bigquery.Client(project=project)
    ds = bigquery.Dataset(f"{project}.{dataset}")
    ds.location = "US"
    client.create_dataset(ds, exists_ok=True)

    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")

    with sql.connect(server_hostname=host, http_path=http_path, access_token=token) as conn:
        with conn.cursor() as cursor:
            for table in TABLES:
                df = read_table(cursor, table)
                target = f"{project}.{dataset}.{table}"
                client.load_table_from_dataframe(df, target, job_config=job_config).result()
                print(f"{table}: {len(df)} rows loaded to {target}")

    print("Done.")


if __name__ == "__main__":
    main()
