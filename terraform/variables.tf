variable "region" {
  description = "AWS region (Mumbai)."
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Resource name prefix."
  type        = string
  default     = "todozee-price"
}

variable "instance_type" {
  description = "EC2 instance type. The app is lightweight; t3.small gives comfortable headroom for Caddy + Python."
  type        = string
  default     = "t3.small"
}

variable "repo_url" {
  description = "Public Git repo cloned onto the instance."
  type        = string
  default     = "https://github.com/kvsabhiram/Todozee_Price-fetcher.git"
}

variable "domain" {
  description = "Public hostname served over HTTPS by Caddy. Point an A-record at the EIP."
  type        = string
  default     = "price.chatbucket.chat"
}

variable "app_port" {
  description = "Port the Flask/Waitress app listens on (must match API_PORT in safe_price_fetcher.py)."
  type        = number
  default     = 5006
}

variable "github_repo" {
  description = "owner/repo allowed to assume the CI/CD deploy role via OIDC."
  type        = string
  default     = "kvsabhiram/Todozee_Price-fetcher"
}

variable "alert_emails" {
  description = "Email addresses subscribed to the SNS alerts topic."
  type        = list(string)
  default     = ["udathak@gmail.com"]
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 30
}
