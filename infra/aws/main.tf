# PAYBACK Assistant on AWS — the parallel cloud target (the brief prefers GCP; this proves the
# stack is portable). Same architecture, AWS-native services:
#
#   ECS Fargate   — runs the FastAPI container (serverless containers, no EC2 to manage).
#   RDS Postgres  — the serving DB: real-time /search + catalog rows, with pgvector.
#   ECR           — holds the image ECS runs.
#   Secrets Mgr   — the OpenAI key, injected at runtime (never baked into the image).
#   ALB           — public HTTP entry point, health-checks /health, routes to the tasks.
#
# See README.md for the runbook (init → fmt → validate → plan → apply).

# ── Image registry ──────────────────────────────────────────────────
resource "aws_ecr_repository" "api" {
  name                 = "payback-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# ── Secret: the LLM/embedding provider key (runtime-injected, never in the image) ────
# Provider-agnostic: the value is whatever provider's key, exposed to the container under the env
# var name that provider expects (local.llm_api_key_env) — so switching OpenAI→Anthropic→Gemini is
# config, not an infra change. (Vertex needs no key at all; it uses the task's IAM/ADC.)
resource "aws_secretsmanager_secret" "llm" {
  name = "payback/llm-api-key"
  # Delete immediately on destroy (no 7–30 day recovery window), so a destroy→apply cycle can
  # recreate the same-named secret without colliding with one "scheduled for deletion".
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "llm" {
  secret_id     = aws_secretsmanager_secret.llm.id
  secret_string = var.llm_api_key
}

# ── Networking: security groups ─────────────────────────────────────
resource "aws_security_group" "alb" {
  name        = "payback-alb"
  description = "Public HTTP to the load balancer."
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from anywhere (a shopper-facing API)."
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "service" {
  name        = "payback-service"
  description = "Fargate tasks: accept traffic only from the ALB."
  vpc_id      = var.vpc_id

  ingress {
    description     = "App port from the ALB only."
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "db" {
  name        = "payback-db"
  description = "RDS: accept Postgres only from the Fargate tasks."
  vpc_id      = var.vpc_id

  ingress {
    description     = "Postgres from the service only."
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.service.id]
  }
}

# ── Serving database: Postgres + pgvector ───────────────────────────
# The DB password is internal plumbing (only the app, inside the VPC, uses it), so Terraform
# generates it — the deployer never has to invent or handle it. No special characters RDS rejects.
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "db" {
  name       = "payback-db"
  subnet_ids = var.subnet_ids
}

resource "aws_db_instance" "postgres" {
  identifier     = "payback-postgres"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage = 20
  db_name           = "payback"
  username          = "payback"
  password          = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]

  # pgvector ships with RDS Postgres; the app's init SQL runs `CREATE EXTENSION vector`.
  skip_final_snapshot = true # demo instance — no final snapshot on destroy.
}

# ── Load balancer ───────────────────────────────────────────────────
resource "aws_lb" "api" {
  name               = "payback-api"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.subnet_ids
}

resource "aws_lb_target_group" "api" {
  name        = "payback-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # Fargate tasks register by IP.

  health_check {
    path    = "/health"
    matcher = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ── IAM: execution role (pull image, read secret, write logs) ───────
data "aws_iam_policy_document" "assume_ecs" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "payback-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.assume_ecs.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Let the execution role read the OpenAI secret so ECS can inject it.
data "aws_iam_policy_document" "read_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.llm.arn]
  }
}

resource "aws_iam_role_policy" "execution_read_secret" {
  name   = "read-openai-secret"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_secret.json
}

# ── Logs ────────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/payback-api"
  retention_in_days = 14
}

# ── The service ─────────────────────────────────────────────────────
resource "aws_ecs_cluster" "api" {
  name = "payback"
}

# The API and the one-off seed job share the same image, DB env, secret, and logs — only the
# command differs. Factor the common bits so the two task definitions can't drift apart.
locals {
  # The env var name the provider's key must be exposed as is derived from llm_model's provider
  # prefix (openai/… → OPENAI_API_KEY), so it can't drift from the chosen model. LiteLLM reads it.
  llm_api_key_env = {
    openai    = "OPENAI_API_KEY"
    anthropic = "ANTHROPIC_API_KEY"
    gemini    = "GEMINI_API_KEY"
  }[split("/", var.llm_model)[0]]

  # The app builds its DB URL from POSTGRES_* parts (see app/config.py), so point those at RDS.
  container_env = [
    { name = "POSTGRES_HOST", value = aws_db_instance.postgres.address },
    { name = "POSTGRES_PORT", value = "5432" },
    { name = "POSTGRES_DB", value = aws_db_instance.postgres.db_name },
    { name = "POSTGRES_USER", value = aws_db_instance.postgres.username },
    { name = "POSTGRES_PASSWORD", value = random_password.db.result },
    # OpenAI by default — one key in Secrets Manager, no cross-cloud dependency.
    { name = "EMBEDDING_PROVIDER", value = var.embedding_provider },
    { name = "LLM_MODEL", value = var.llm_model },
  ]

  # The provider key is pulled from Secrets Manager at task start (under the provider's env var
  # name), not stored in the task def.
  container_secrets = [
    { name = local.llm_api_key_env, valueFrom = aws_secretsmanager_secret.llm.arn }
  ]

  log_options = {
    "awslogs-group"         = aws_cloudwatch_log_group.api.name
    "awslogs-region"        = var.region
    "awslogs-stream-prefix" = "api"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "payback-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([
    {
      name         = "api"
      image        = var.image
      essential    = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment  = local.container_env
      secrets      = local.container_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options   = local.log_options
      }
    }
  ])
}

# One-off seed job: same image + network as the service, run inside the VPC so it reaches the
# private RDS with no public exposure. Run it once after apply:
#   aws ecs run-task --cluster payback --task-definition payback-seed --launch-type FARGATE \
#     --network-configuration "awsvpcConfiguration={subnets=[...],securityGroups=[...],assignPublicIp=ENABLED}"
# It loads the catalogs and computes embeddings, then exits.
resource "aws_ecs_task_definition" "seed" {
  family                   = "payback-seed"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([
    {
      name        = "seed"
      image       = var.image
      essential   = true
      command     = ["sh", "-c", "python -m data.init_db && python -m data.seed && python -m data.embed"]
      environment = local.container_env
      secrets     = local.container_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options   = local.log_options
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "payback-api"
  cluster         = aws_ecs_cluster.api.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = true # so the task can pull the image + reach OpenAI without a NAT gateway.
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}
