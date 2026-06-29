output "service_url" {
  description = "Public URL of the deployed assistant API."
  value       = google_cloud_run_v2_service.api.uri
}

output "db_connection_name" {
  description = "Cloud SQL connection name (project:region:instance) for the Cloud SQL proxy."
  value       = google_sql_database_instance.postgres.connection_name
}

output "image_repository" {
  description = "Artifact Registry path to push the API image to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}"
}

output "bigquery_dataset" {
  description = "BigQuery dataset for the vector-search scale path (ADR 0003)."
  value       = google_bigquery_dataset.vectors.dataset_id
}

output "seed_command" {
  description = "Run once after apply to load the catalog + embeddings into Cloud SQL."
  value       = "gcloud run jobs execute ${google_cloud_run_v2_job.seed.name} --region ${var.region} --wait"
}
