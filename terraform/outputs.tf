output "dataset" {
  value = google_bigquery_dataset.air_quality.dataset_id
}

output "reader_service_account" {
  value = google_service_account.reader.email
}
