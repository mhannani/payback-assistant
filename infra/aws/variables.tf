variable "region" {
  description = "AWS region for ECS, RDS, ECR, and the load balancer."
  type        = string
  default     = "eu-central-1" # Frankfurt — closest to the German market this serves.
}

variable "image" {
  description = "Container image for the API. Defaults to the public GHCR image built by CI; override with an ECR ref for an all-AWS supply chain."
  type        = string
  default     = "ghcr.io/mhannani/payback-assistant:latest"
}

variable "vpc_id" {
  description = "VPC to deploy into (the account's default VPC is fine for the demo)."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets for the ALB and Fargate tasks (≥2 in different AZs)."
  type        = list(string)
}

variable "db_instance_class" {
  description = "RDS instance class. The demo fits the smallest burstable class."
  type        = string
  default     = "db.t3.micro"
}

variable "llm_model" {
  description = "LiteLLM model id for the agent."
  type        = string
  default     = "openai/gpt-4o-mini"
}

variable "embedding_provider" {
  description = "Cloud embedding provider (openai | vertex)."
  type        = string
  default     = "openai"
}

variable "db_password" {
  description = "Password for the Postgres app user. Pass via a .tfvars file (gitignored) or TF_VAR_db_password — never commit it."
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI key the agent uses, stored in Secrets Manager (not baked into the image). Pass via env/tfvars, never commit."
  type        = string
  sensitive   = true
}
