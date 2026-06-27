provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "todozee-price-fetcher"
      ManagedBy = "terraform"
    }
  }
}
