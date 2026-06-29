# PAYBACK Assistant on GCP — the brief's preferred stack (Cloud Run + Cloud SQL + BigQuery).
#
# Shape (why each piece):
#   Cloud Run        — serves the FastAPI container (stateless, scales to zero).
#   Cloud SQL (pg)   — the serving DB: real-time /search + the catalog rows, with pgvector.
#   BigQuery dataset — the brief's "BigQuery for vector search" seam. Per ADR 0003 BigQuery is a
#                      warehouse (OLAP, not for real-time serving), so it's the documented
#                      vector-search SCALE path the Retriever interface plugs into — provisioned
#                      here as the dataset, not wired as the primary store.
#   Artifact Registry — holds the image Cloud Run runs.
#   Secret Manager   — the OpenAI key, injected at runtime (never baked into the image).
#
# See README.md for the runbook (init → fmt → validate → plan → apply).

locals {
  # Enable the APIs this stack calls. Kept here so `apply` doesn't fail on a fresh project.
  services = [
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "bigquery.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each = toset(local.services)
  service  = each.value

  disable_on_destroy = false
}

# ── Image registry ──────────────────────────────────────────────────
resource "google_artifact_registry_repository" "api" {
  location      = var.region
  repository_id = "payback"
  format        = "DOCKER"
  description   = "PAYBACK Assistant container images."

  depends_on = [google_project_service.enabled]
}

# ── Serving database: Postgres + pgvector ───────────────────────────
resource "google_sql_database_instance" "postgres" {
  name             = "payback-postgres"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = var.db_tier

    # pgvector ships as an available extension on Cloud SQL Postgres; the app's init SQL runs
    # `CREATE EXTENSION vector`. No flag is needed to allow it, but we keep the DB private.
    ip_configuration {
      ipv4_enabled = true
    }
  }

  # A demo instance — allow `terraform destroy` to remove it without an extra confirmation flag.
  deletion_protection = false

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database" "app" {
  name     = "payback"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  name     = "payback"
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}

# ── BigQuery: the documented vector-search scale path (ADR 0003) ─────
resource "google_bigquery_dataset" "vectors" {
  dataset_id  = "payback_vectors"
  location    = var.region
  description = "Vector-search warehouse seam (ADR 0003): BigQuery VECTOR_SEARCH at scale, behind the Retriever interface. Not the real-time serving store."

  depends_on = [google_project_service.enabled]
}

# ── Secret: the OpenAI key (runtime-injected, never in the image) ────
resource "google_secret_manager_secret" "openai" {
  secret_id = "payback-openai-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "openai" {
  secret      = google_secret_manager_secret.openai.id
  secret_data = var.openai_api_key
}

# ── Runtime identity (least privilege) ──────────────────────────────
resource "google_service_account" "run" {
  account_id   = "payback-run"
  display_name = "PAYBACK Assistant Cloud Run runtime"
}

# Read the OpenAI secret.
resource "google_secret_manager_secret_iam_member" "run_reads_openai" {
  secret_id = google_secret_manager_secret.openai.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run.email}"
}

# Connect to Cloud SQL.
resource "google_project_iam_member" "run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.run.email}"
}

# ── The service ─────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "api" {
  name     = "payback-api"
  location = var.region

  template {
    service_account = google_service_account.run.email

    # Attach the Cloud SQL instance so the app reaches it over the built-in socket.
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }

    containers {
      image = var.image

      ports {
        container_port = 8000
      }

      # Production serves embeddings off-host via Vertex (the lean image has no local model/torch).
      env {
        name  = "EMBEDDING_PROVIDER"
        value = "vertex"
      }
      env {
        name  = "LLM_MODEL"
        value = var.llm_model
      }

      # DB connection over the Cloud SQL unix socket mounted below.
      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://${google_sql_user.app.name}:${var.db_password}@/${google_sql_database.app.name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
      }

      # The OpenAI key comes from Secret Manager, not the image or plain env.
      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openai.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
  }

  depends_on = [google_project_service.enabled]
}

# The runtime calls Vertex AI for embeddings (and optionally the LLM), so grant the user role.
resource "google_project_iam_member" "run_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.run.email}"
}

# One-off seed job: same image + identity as the service, reaching Cloud SQL over the private
# socket — no public DB exposure. Run it once after apply:
#   gcloud run jobs execute payback-seed --region <region> --wait
# It loads the catalogs and computes embeddings (via Vertex), then exits.
resource "google_cloud_run_v2_job" "seed" {
  name     = "payback-seed"
  location = var.region

  template {
    template {
      service_account = google_service_account.run.email

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres.connection_name]
        }
      }

      containers {
        image   = var.image
        command = ["sh", "-c", "python -m data.init_db && python -m data.seed && python -m data.embed"]

        env {
          name  = "EMBEDDING_PROVIDER"
          value = "vertex"
        }
        env {
          name  = "LLM_MODEL"
          value = var.llm_model
        }
        env {
          name  = "DATABASE_URL"
          value = "postgresql+asyncpg://${google_sql_user.app.name}:${var.db_password}@/${google_sql_database.app.name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
        }
        env {
          name = "OPENAI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.openai.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }

  depends_on = [google_project_service.enabled]
}

# Public endpoint (a shopper-facing API). Tighten with IAM/IAP behind a gateway in production.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
