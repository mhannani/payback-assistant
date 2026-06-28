variable "project_id" {
  description = "GCP project to deploy into."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run, Cloud SQL, Artifact Registry, and BigQuery."
  type        = string
  default     = "europe-west3" # Frankfurt — closest to the German market this serves.
}

variable "image" {
  description = "Container image for the API. Defaults to the public GHCR image built by CI; override with an Artifact Registry ref for an all-GCP supply chain."
  type        = string
  default     = "ghcr.io/mhannani/payback-assistant:latest"
}

variable "db_tier" {
  description = "Cloud SQL machine tier. The demo fits the smallest shared-core tier."
  type        = string
  default     = "db-f1-micro"
}

variable "db_password" {
  description = "Password for the Postgres app user. Pass via a .tfvars file (gitignored) or TF_VAR_db_password — never commit it."
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI key the agent uses, stored in Secret Manager (not baked into the image). Pass via env/tfvars, never commit."
  type        = string
  sensitive   = true
}
