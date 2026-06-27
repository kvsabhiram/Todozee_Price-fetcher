terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Reuses the existing shared Todozee state bucket in Mumbai.
  # S3 native locking (use_lockfile) means no DynamoDB table is required.
  backend "s3" {
    bucket       = "todozee-tfstate-637560253183"
    key          = "price-fetcher/main.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
