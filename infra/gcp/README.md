# Deploy to GCP (Terraform)

The brief's preferred stack: **Cloud Run** (API) + **Cloud SQL** Postgres/pgvector (serving DB) +
**BigQuery** (the vector-search scale path, ADR 0003) + Artifact Registry + Secret Manager.

## What it provisions

| Resource | Role |
|---|---|
| Cloud Run service | Serves the FastAPI container on port 8000 |
| Cloud SQL (Postgres 16) | Serving DB — real-time `/search` + catalog rows, with pgvector |
| BigQuery dataset | Vector-search **scale** seam (ADR 0003); not the real-time store |
| Artifact Registry | Holds the API image |
| Secret Manager | Injects `OPENAI_API_KEY` at runtime (never baked into the image) |
| Service account + IAM | Least-privilege runtime: read the secret, connect to Cloud SQL |

## Required deployer permissions

`terraform apply` enables the APIs and creates managed services, so the deploying principal needs
the rights to do so (the application's *runtime* permissions are the service account in the
Terraform; these are the *deployer's*). Grant the account running Terraform `roles/owner` on the
project, or — for least privilege — `roles/run.admin`, `roles/cloudsql.admin`,
`roles/artifactregistry.admin`, `roles/secretmanager.admin`, `roles/bigquery.admin`,
`roles/iam.serviceAccountAdmin`, and `roles/serviceusage.serviceUsageAdmin`.

## Runbook

```bash
cp terraform.tfvars.example terraform.tfvars     # fill in project/image; keep secrets out of git
export TF_VAR_db_password=...                     # prefer env over the file for secrets
export TF_VAR_openai_api_key=sk-...

terraform init
terraform fmt -check
terraform validate
terraform plan        # needs GCP credentials (gcloud auth application-default login)
terraform apply       # provisions the stack
```

Build and push the image to the `image_repository` output before `apply` sets the Cloud Run image.

> **Vertex AI:** swapping the LLM/embeddings to Vertex is a config change (`LLM_MODEL` →
> `vertex_ai/…`), not an infra change — LiteLLM routes to it. No Terraform edit required.
