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

# Everything needed to launch the one-off seed task after apply.
output "seed_command" {
  description = "Run once after apply to load the catalog + embeddings into RDS."
  value       = "aws ecs run-task --cluster ${aws_ecs_cluster.api.name} --task-definition ${aws_ecs_task_definition.seed.family} --launch-type FARGATE --network-configuration 'awsvpcConfiguration={subnets=[${join(",", var.subnet_ids)}],securityGroups=[${aws_security_group.service.id}],assignPublicIp=ENABLED}' --region ${var.region}"
}
