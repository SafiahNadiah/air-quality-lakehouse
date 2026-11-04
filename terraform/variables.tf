variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "air-quality-portfolio"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "US"
}

variable "dataset_id" {
  type    = string
  default = "air_quality_iac"
}
