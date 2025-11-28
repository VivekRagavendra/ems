# Terragrunt configuration
# All values are loaded from config/config.yaml

# Load config using Python script
locals {
  # Try to load config using Python script, fallback to defaults
  config_json = try(
    jsondecode(run_cmd("--terragrunt-quiet", "python3", "${get_parent_terragrunt_dir()}/scripts/load-config.py")),
    {}
  )
  
  # Extract values with defaults
  aws_account_id = try(local.config_json.aws.account_id, "420464349284")
  aws_region = try(local.config_json.aws.region, "us-east-1")
  eks_cluster_name = try(local.config_json.eks.cluster_name, "mi-eks-cluster")
  dynamodb_table_name = try(local.config_json.dynamodb.table_name, "eks-app-controller-registry")
  project_name = try(local.config_json.project.name, "eks-app-controller")
  lambda_runtime = try(local.config_json.lambda.runtime, "python3.11")
  discovery_schedule = try(local.config_json.eventbridge.discovery_schedule, "rate(2 hours)")
  health_check_schedule = try(local.config_json.eventbridge.health_check_schedule, "rate(15 minutes)")
}

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

# Inputs passed to OpenTofu - loaded from config/config.yaml
inputs = {
  aws_region       = local.aws_region
  eks_cluster_name = local.eks_cluster_name
  project_name     = local.project_name
  lambda_runtime   = local.lambda_runtime
  
  # EventBridge schedules (cost-optimized)
  discovery_schedule = local.discovery_schedule
  health_check_schedule = local.health_check_schedule
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
