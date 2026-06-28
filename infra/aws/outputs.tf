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
