# Yearly aggregate table, mirrors gold_agg_yearly in Databricks and the manual BigQuery dataset.
resource "google_bigquery_table" "gold_agg_yearly" {
  dataset_id          = google_bigquery_dataset.air_quality.dataset_id
  table_id            = "gold_agg_yearly"
  description         = "One row per year and pollutant (gold layer)"
  deletion_protection = false

  schema = jsonencode([
    { name = "year",              type = "INT64",   mode = "NULLABLE" },
    { name = "pollutant_code",    type = "STRING",  mode = "NULLABLE" },
    { name = "months_with_data",  type = "INT64",   mode = "NULLABLE" },
    { name = "avg_concentration", type = "FLOAT64", mode = "NULLABLE" },
    { name = "min_concentration", type = "FLOAT64", mode = "NULLABLE" },
    { name = "max_concentration", type = "FLOAT64", mode = "NULLABLE" },
    { name = "yoy_change_pct",    type = "STRING",  mode = "NULLABLE" },
  ])
}
