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

variable "llm_model" {
  description = "LiteLLM model id for the agent. Defaults to Vertex Gemini for an all-GCP path."
  type        = string
  default     = "vertex_ai/gemini-2.0-flash"
}

variable "llm_api_key" {
  description = "API key for the provider in llm_model, injected under that provider's env var name (derived automatically). Leave empty for the default all-Vertex path (ADC, no key). Pass via TF_VAR_llm_api_key, never commit."
  type        = string
  sensitive   = true
  default     = ""
}
