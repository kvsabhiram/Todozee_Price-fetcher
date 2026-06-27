output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Elastic IP — point the domain's A-record here."
  value       = aws_eip.app.public_ip
}

output "domain" {
  description = "Public HTTPS hostname."
  value       = var.domain
}

output "app_url" {
  description = "Public API base URL (after DNS + Caddy cert)."
  value       = "https://${var.domain}"
}

output "dashboard_url" {
  description = "CloudWatch dashboard."
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "sns_topic_arn" {
  description = "Alerts SNS topic."
  value       = aws_sns_topic.alerts.arn
}

output "github_deploy_role_arn" {
  description = "Set this as the AWS_DEPLOY_ROLE_ARN repo secret to enable CI/CD."
  value       = aws_iam_role.github_deploy.arn
}

output "log_groups" {
  description = "CloudWatch log groups."
  value       = [aws_cloudwatch_log_group.app.name, aws_cloudwatch_log_group.boot.name]
}
