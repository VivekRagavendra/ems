# Terragrunt configuration for mi-eks-cluster
# Account: 420464349284
# Region: us-east-1

# Generate OpenTofu provider configuration
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
EOF
}

# Remote state configuration (local for now)
# For production, uncomment and configure S3 backend below

# Inputs passed to OpenTofu
inputs = {
  aws_region       = "us-east-1"           # Your AWS region
  eks_cluster_name = "mi-eks-cluster"      # Your EKS cluster name
  project_name     = "eks-app-controller"  # Project name prefix
  lambda_runtime   = "python3.11"          # Python runtime version
  
  # EventBridge schedules (cost-optimized)
  discovery_schedule = "rate(2 hours)"     # Auto-discover apps every 2 hours
  health_check_schedule = "rate(15 minutes)" # Health checks every 15 minutes
}

# Cost Optimization Settings:
# - Lambda functions: 256 MB memory (cost-optimized)
# - Discovery: every 2 hours (12x/day)
# - Health checks: every 15 minutes (96x/day)
# - Total Lambda invocations: ~10K/month (within 1M free tier)
# - Expected cost: $0-1/month (first year), $1-6/month (after free tier)

# Skip dependency optimization
skip = false

# Prevent accidental destroy (set to true after initial deployment)
prevent_destroy = false
