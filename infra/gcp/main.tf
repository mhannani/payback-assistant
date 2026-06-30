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

  # The env var name the provider's key is exposed as, derived from llm_model's provider prefix so
  # it can't drift from the model. The default all-Vertex path (vertex_ai/…) needs no key — ADC
  # authenticates — so it falls back to a harmless name over the (empty) secret.
  llm_api_key_env = lookup({
    openai    = "OPENAI_API_KEY"
    anthropic = "ANTHROPIC_API_KEY"
    gemini    = "GEMINI_API_KEY"
  }, split("/", var.llm_model)[0], "OPENAI_API_KEY")

  # Cloud Run can't pull ghcr.io directly, so it pulls through the AR remote repo (ghcr_remote).
  # Rewrite the GHCR ref to the pull-through path: ghcr.io/<path> →
  # <region>-docker.pkg.dev/<project>/ghcr-remote/<path>. Callers still pass the familiar GHCR ref
  # (var.image) — uniform with AWS — and AR fetches+caches the upstream on first pull. If an
  # explicit AR image is passed (all-GCP supply chain), it's used as-is.
  ghcr_remote_host = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.ghcr_remote.repository_id}"
  container_image = startswith(var.image, "ghcr.io/") ? replace(var.image, "ghcr.io", local.ghcr_remote_host) : var.image
}

resource "google_project_service" "enabled" {
  for_each = toset(local.services)
  service  = each.value

  disable_on_destroy = false
}

# ── Image registry ──────────────────────────────────────────────────
# A standard Docker repo — kept for an all-GCP supply chain (push your own builds here).
resource "google_artifact_registry_repository" "api" {
  location      = var.region
  repository_id = "payback"
  format        = "DOCKER"
  description   = "PAYBACK Assistant container images."

  depends_on = [google_project_service.enabled]
}

# Cloud Run can ONLY pull from Artifact Registry / GCR / Docker Hub — NOT GHCR, where CI publishes
# the image. Rather than hand-mirror the image (a manual, non-reproducible step), we declare a
# REMOTE repository that proxies GHCR: Cloud Run pulls from this AR repo, and AR transparently
# fetches + caches the upstream image from ghcr.io on first pull. This is Google's recommended
# pattern for deploying a non-GCP-registry image (it's exactly what the Cloud Run "use a remote
# repository" error points to) — pure infrastructure, no docker/skopeo in the deploy path.
resource "google_artifact_registry_repository" "ghcr_remote" {
  location      = var.region
  repository_id = "ghcr-remote"
  format        = "DOCKER"
  mode          = "REMOTE_REPOSITORY"
  description   = "Pull-through cache of the public GHCR image (Cloud Run can't pull ghcr.io directly)."

  remote_repository_config {
    description = "ghcr.io (GitHub Container Registry) upstream"
    docker_repository {
      custom_repository {
        uri = "https://ghcr.io"
      }
    }
  }

  depends_on = [google_project_service.enabled]
}

# ── Serving database: Postgres + pgvector ───────────────────────────
resource "google_sql_database_instance" "postgres" {
  name             = "payback-postgres"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = var.db_tier
    # Pin the edition: the small shared-core tiers (db-f1-micro) exist ONLY in ENTERPRISE, not the
    # newer ENTERPRISE_PLUS default — leaving this unset makes Cloud SQL pick ENTERPRISE_PLUS and
    # reject db-f1-micro. ENTERPRISE is the right edition for a demo instance anyway.
    edition = "ENTERPRISE"

    # pgvector ships as an available extension on Cloud SQL Postgres; the app's init SQL runs
    # `CREATE EXTENSION vector`. The app reaches Cloud SQL over the Cloud Run socket
    # (DATABASE_URL host=/cloudsql/<conn>), which goes through the Cloud SQL connector — it does NOT
    # use the instance IP. Cloud SQL nonetheless requires SOME connectivity method at creation, so we
    # enable a public IP but authorize NO networks: the IP is unreachable (default-deny), the socket
    # is the only path in. (Private IP would need a whole VPC + Private Service Access — overkill for a
    # demo; the standard Cloud Run + Cloud SQL pattern is socket-over-connector with no authorized nets.)
    ip_configuration {
      ipv4_enabled = true
      # No authorized_networks block → nothing on the internet can connect; only the socket can.
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

# The DB password is internal plumbing (only the app, over the private socket, uses it), so
# Terraform generates it — the deployer never has to invent or handle it.
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  name     = "payback"
  instance = google_sql_database_instance.postgres.name
  password = random_password.db.result
}

# ── BigQuery: the documented vector-search scale path (ADR 0003) ─────
resource "google_bigquery_dataset" "vectors" {
  dataset_id  = "payback_vectors"
  location    = var.region
  description = "GCP vector store (ADR 0003/0007): holds product embeddings; the BigQueryRetriever runs VECTOR_SEARCH here. Catalog rows + the agent checkpointer stay in Cloud SQL."

  depends_on = [google_project_service.enabled]
}

# ── Secret: the LLM/embedding provider key (runtime-injected, never in the image) ────
# Provider-agnostic: exposed to the container under the provider's expected env var name
# (local.llm_api_key_env). With EMBEDDING_PROVIDER=vertex + an LLM via Vertex, no key is needed at
# all (the runtime service account / ADC authenticates) — leave llm_api_key empty in that case.
resource "google_secret_manager_secret" "llm" {
  secret_id = "payback-llm-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

# The secret version, the IAM grant, and the runtime env that reads it exist only when a key is
# given. The default all-Vertex path uses ADC (no key), and Secret Manager rejects an empty value —
# so on that path these are skipped rather than failing the apply.
resource "google_secret_manager_secret_version" "llm" {
  count       = var.llm_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.llm.id
  secret_data = var.llm_api_key
}

# ── Runtime identity (least privilege) ──────────────────────────────
resource "google_service_account" "run" {
  account_id   = "payback-run"
  display_name = "PAYBACK Assistant Cloud Run runtime"
}

# Read the provider key (only when one is configured).
resource "google_secret_manager_secret_iam_member" "run_reads_llm" {
  count     = var.llm_api_key != "" ? 1 : 0
  secret_id = google_secret_manager_secret.llm.id
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
      image = local.container_image

      ports {
        container_port = 8000
      }

      # Production serves embeddings off-host via Vertex (the lean image has no local model/torch).
      env {
        name  = "EMBEDDING_PROVIDER"
        value = "vertex"
      }
      # Vertex and BigQuery need the GCP project + location explicitly; ADC doesn't expose them at runtime.
      env {
        name  = "VERTEX_PROJECT"
        value = var.project_id
      }
      env {
        name  = "VERTEX_LOCATION"
        value = var.region
      }
      env {
        name  = "LLM_MODEL"
        value = var.llm_model
      }

      # GCP serves vector search from BigQuery (the brief's preferred service / warehouse tier);
      # local + AWS stay on pgvector. Catalog rows + the checkpointer remain in Cloud SQL.
      env {
        name  = "RETRIEVER_BACKEND"
        value = "bigquery"
      }
      env {
        name  = "BIGQUERY_DATASET"
        value = google_bigquery_dataset.vectors.dataset_id
      }
      env {
        name  = "BIGQUERY_TABLE"
        value = "products"
      }

      # DB connection over the Cloud SQL unix socket mounted below.
      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://${google_sql_user.app.name}:${random_password.db.result}@/${google_sql_database.app.name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
      }

      # The provider key comes from Secret Manager (under the provider's env var name), injected
      # only when a key is configured — the all-Vertex path authenticates via ADC and needs none.
      dynamic "env" {
        for_each = var.llm_api_key != "" ? [1] : []
        content {
          name = local.llm_api_key_env
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.llm.secret_id
              version = "latest"
            }
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

# BigQuery is the GCP vector backend: run VECTOR_SEARCH jobs (project-level), and write vectors
# into the dataset (dataset-scoped editor — least privilege, not project-wide).
resource "google_project_iam_member" "run_bigquery_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.run.email}"
}

resource "google_bigquery_dataset_iam_member" "run_dataset_editor" {
  dataset_id = google_bigquery_dataset.vectors.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.run.email}"
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
        image = local.container_image
        # init_db (Postgres schema/rows) → init_bq (BigQuery vector table + index) → seed (rows into
        # Postgres) → embed (vectors into BigQuery, routed by RETRIEVER_BACKEND).
        command = ["sh", "-c", "python -m data.init_db && python -m data.init_bq && python -m data.seed && python -m data.embed"]

        env {
          name  = "EMBEDDING_PROVIDER"
          value = "vertex"
        }
        # Vertex and BigQuery need the GCP project + location explicitly; ADC doesn't expose them at runtime.
        env {
          name  = "VERTEX_PROJECT"
          value = var.project_id
        }
        env {
          name  = "VERTEX_LOCATION"
          value = var.region
        }
        env {
          name  = "LLM_MODEL"
          value = var.llm_model
        }
        env {
          name  = "RETRIEVER_BACKEND"
          value = "bigquery"
        }
        env {
          name  = "BIGQUERY_DATASET"
          value = google_bigquery_dataset.vectors.dataset_id
        }
        env {
          name  = "BIGQUERY_TABLE"
          value = "products"
        }
        env {
          name  = "DATABASE_URL"
          value = "postgresql+asyncpg://${google_sql_user.app.name}:${random_password.db.result}@/${google_sql_database.app.name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
        }
        dynamic "env" {
          for_each = var.llm_api_key != "" ? [1] : []
          content {
            name = local.llm_api_key_env
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.llm.secret_id
                version = "latest"
              }
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
