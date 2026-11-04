terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# BigQuery dataset for the serving layer (separate from the manually created `air_quality` dataset)
resource "google_bigquery_dataset" "air_quality" {
  dataset_id                  = var.dataset_id
  location                    = var.location
  description                 = "Air quality gold tables, managed by Terraform"
  delete_contents_on_destroy  = true
  default_table_expiration_ms = 5184000000 # 60 days, the BigQuery sandbox limit

  labels = {
    project    = "air-quality-lakehouse"
    managed_by = "terraform"
  }
}

# A service account that can only read the dataset (for dashboards or services)
resource "google_service_account" "reader" {
  account_id   = "air-quality-reader"
  display_name = "Air quality read-only"
}

resource "google_bigquery_dataset_iam_member" "reader_view" {
  dataset_id = google_bigquery_dataset.air_quality.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.reader.email}"
}
