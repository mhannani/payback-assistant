output "service_url" {
  description = "Public URL of the deployed assistant API (the load balancer)."
  value       = "http://${aws_lb.api.dns_name}"
}

output "db_endpoint" {
  description = "RDS Postgres endpoint (host:port)."
  value       = aws_db_instance.postgres.endpoint
}

output "image_repository" {
  description = "ECR repository URL to push the API image to."
  value       = aws_ecr_repository.api.repository_url
}

# Discrete pieces the seed step needs — `make seed-aws` assembles the run-task call from these,
# so the (quoting-sensitive) network config isn't passed through a shell-fragile command string.
output "cluster" {
  description = "ECS cluster name for the one-off seed task."
  value       = aws_ecs_cluster.api.name
}

output "seed_task" {
  description = "Task-definition family for the one-off seed task."
  value       = aws_ecs_task_definition.seed.family
}

output "service_security_group" {
  description = "Security group the seed task runs under (reaches RDS)."
  value       = aws_security_group.service.id
}

output "subnets_csv" {
  description = "Comma-separated subnet ids for the seed task's network config."
  value       = join(",", var.subnet_ids)
}

output "region" {
  description = "Deploy region (for the seed task launch)."
  value       = var.region
}
