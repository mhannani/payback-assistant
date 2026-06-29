# Deploy to AWS (Terraform)

The parallel cloud target. The brief prefers GCP; this proves the stack is cloud-portable on
AWS-native services: **ECS Fargate** (API) + **RDS** Postgres/pgvector (serving DB) + **ECR** +
**Secrets Manager** + an **Application Load Balancer**.

## What it provisions

| Resource | Role |
|---|---|
| ECS Fargate service | Runs the FastAPI container (serverless containers) |
| RDS (Postgres 16) | Serving DB — real-time `/search` + catalog rows, with pgvector |
| ECR | Holds the API image |
| Secrets Manager | Injects `OPENAI_API_KEY` at runtime (never baked into the image) |
| Application Load Balancer | Public entry point, health-checks `/health`, routes to tasks |
| Security groups | ALB → service → DB, each tier reachable only by the one in front |
| IAM execution role | Least-privilege: pull image, read the secret, write logs |

## Required deployer permissions

`terraform apply` creates managed services, so the principal running it (your IAM user, an assumed
role, or CI) needs permission to create them. The application's *runtime* permissions are in the
Terraform (the ECS execution role); these are the *deployer's* permissions — environment setup, not
repo code. Attach these to the deploying principal (or run under `PowerUserAccess` + `IAMFullAccess`):

| Service | Managed policy |
|---|---|
| ECS / Fargate | `AmazonECS_FullAccess` |
| RDS | `AmazonRDSFullAccess` |
| Secrets Manager | `SecretsManagerReadWrite` |
| CloudWatch Logs | `CloudWatchLogsFullAccess` |
| ECR | `AmazonEC2ContainerRegistryFullAccess` |
| VPC / EC2 / ELB | `AmazonVPCFullAccess`, `AmazonEC2FullAccess`, `ElasticLoadBalancingFullAccess` |
| IAM (create the runtime role) | `IAMFullAccess` |

## Runbook

```bash
cp terraform.tfvars.example terraform.tfvars     # fill in vpc/subnets/image; keep secrets out of git
export TF_VAR_db_password=...                     # prefer env over the file for secrets
export TF_VAR_openai_api_key=sk-...

terraform init
terraform fmt -check
terraform validate
terraform plan        # needs AWS credentials (aws configure / a profile)
terraform apply       # provisions the stack
```

Build and push the image to the `image_repository` output before `apply` sets the task image.
