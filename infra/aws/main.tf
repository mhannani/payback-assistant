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

# ── Secret: the OpenAI key (runtime-injected, never in the image) ────
resource "aws_secretsmanager_secret" "openai" {
  name = "payback/openai-api-key"
}

resource "aws_secretsmanager_secret_version" "openai" {
  secret_id     = aws_secretsmanager_secret.openai.id
  secret_string = var.openai_api_key
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
  password          = var.db_password

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
    resources = [aws_secretsmanager_secret.openai.arn]
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

resource "aws_ecs_task_definition" "api" {
  family                   = "payback-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.image
      essential = true
      portMappings = [
        { containerPort = 8000, protocol = "tcp" }
      ]
      environment = [
        {
          name  = "DATABASE_URL"
          value = "postgresql+asyncpg://${aws_db_instance.postgres.username}:${var.db_password}@${aws_db_instance.postgres.address}:5432/${aws_db_instance.postgres.db_name}"
        },
        # OpenAI by default — one key in Secrets Manager, no cross-cloud dependency.
        { name = "EMBEDDING_PROVIDER", value = var.embedding_provider },
        { name = "LLM_MODEL", value = var.llm_model },
      ]
      # The OpenAI key is pulled from Secrets Manager at task start, not stored in the task def.
      secrets = [
        { name = "OPENAI_API_KEY", valueFrom = aws_secretsmanager_secret.openai.arn }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "api"
        }
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
