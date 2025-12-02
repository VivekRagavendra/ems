# Lambda Functions with proper packaging
# Use pre-built zip files (with dependencies) from build script
# Run ./build-lambdas.sh before deploying

# Note: VPC configuration is NOT included by default to avoid additional costs
# If your EKS cluster has a private endpoint only, you'll need to either:
# 1. Enable public endpoint on EKS cluster (recommended, no cost)
# 2. Add VPC configuration to Lambda functions (requires NAT Gateway or VPC endpoints, ~$21-32/month)

locals {
  discovery_zip_path      = "${path.module}/../build/discovery.zip"
  controller_zip_path     = "${path.module}/../build/controller.zip"
  health_monitor_zip_path = "${path.module}/../build/health-monitor.zip"
  api_handler_zip_path    = "${path.module}/../build/api-handler.zip"
  cost_tracker_zip_path   = "${path.module}/../build/cost-tracker.zip"
  scheduler_zip_path      = "${path.module}/../build/scheduler.zip"
}

# Discovery Lambda
resource "aws_lambda_function" "discovery" {
  filename         = local.discovery_zip_path
  source_code_hash = filebase64sha256(local.discovery_zip_path)
  function_name    = "${var.project_name}-discovery"
  role             = aws_iam_role.discovery_lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = 300
  memory_size      = 256 # Cost-optimized: 256 MB is sufficient

  environment {
    variables = {
      REGISTRY_TABLE_NAME = aws_dynamodb_table.app_registry.name
      EKS_CLUSTER_NAME    = var.eks_cluster_name
      CONFIG_NAME         = var.config_name
    }
  }

  # VPC configuration removed - using public EKS endpoint (no additional cost)
  # If you need VPC, uncomment and configure:
  # vpc_config {
  #   subnet_ids         = data.aws_eks_cluster.main.vpc_config[0].subnet_ids
  #   security_group_ids = [aws_security_group.lambda_sg.id]
  # }

  depends_on = [
    aws_iam_role_policy.discovery_lambda_policy
  ]
}

# Controller Lambda
resource "aws_lambda_function" "controller" {
  filename         = local.controller_zip_path
  source_code_hash = filebase64sha256(local.controller_zip_path)
  function_name    = "${var.project_name}-controller"
  role             = aws_iam_role.controller_lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = 900  # 15 minutes for complete workflow (EC2 + NodeGroup + K8s + HTTP)
  memory_size      = 512  # Increased for Kubernetes operations

  environment {
    variables = {
      REGISTRY_TABLE_NAME = aws_dynamodb_table.app_registry.name
      EKS_CLUSTER_NAME    = var.eks_cluster_name
      CONFIG_NAME         = var.config_name
    }
  }

  # VPC configuration removed - using public EKS endpoint (no additional cost)

  depends_on = [
    aws_iam_role_policy.controller_lambda_policy
  ]
}

# Health Monitor Lambda
resource "aws_lambda_function" "health_monitor" {
  filename         = local.health_monitor_zip_path
  source_code_hash = filebase64sha256(local.health_monitor_zip_path)
  function_name    = "${var.project_name}-health-monitor"
  role             = aws_iam_role.health_monitor_lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = 300
  memory_size      = 256 # Cost-optimized: 256 MB is sufficient

  environment {
    variables = {
      REGISTRY_TABLE_NAME = aws_dynamodb_table.app_registry.name
      EKS_CLUSTER_NAME    = var.eks_cluster_name
      CONFIG_NAME         = var.config_name
    }
  }

  # VPC configuration removed - using public EKS endpoint (no additional cost)

  depends_on = [
    aws_iam_role_policy.health_monitor_lambda_policy
  ]
}

# API Handler Lambda
resource "aws_lambda_function" "api_handler" {
  filename         = local.api_handler_zip_path
  source_code_hash = filebase64sha256(local.api_handler_zip_path)
  function_name    = "${var.project_name}-api-handler"
  role             = aws_iam_role.api_handler_lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = 90  # Increased to handle EC2 lookups for all apps
  memory_size      = 512  # Increased for better performance with EC2 API calls

  environment {
    variables = {
      REGISTRY_TABLE_NAME    = aws_dynamodb_table.app_registry.name
      COSTS_TABLE_NAME       = aws_dynamodb_table.app_costs.name
      SCHEDULES_TABLE_NAME   = aws_dynamodb_table.app_schedules.name
      EKS_CLUSTER_NAME       = var.eks_cluster_name
      CONFIG_NAME            = var.config_name
    }
  }

  # VPC configuration removed - using public EKS endpoint (no additional cost)

  depends_on = [
    aws_iam_role_policy.api_handler_lambda_policy
  ]
}

# EventBridge Permissions
resource "aws_lambda_permission" "discovery_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.discovery.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.discovery_schedule.arn
}

resource "aws_lambda_permission" "health_monitor_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.health_monitor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.health_check_schedule.arn
}

# EventBridge Targets
resource "aws_cloudwatch_event_target" "discovery_target" {
  rule      = aws_cloudwatch_event_rule.discovery_schedule.name
  target_id = "DiscoveryLambdaTarget"
  arn       = aws_lambda_function.discovery.arn
}

resource "aws_cloudwatch_event_target" "health_check_target" {
  rule      = aws_cloudwatch_event_rule.health_check_schedule.name
  target_id = "HealthMonitorLambdaTarget"
  arn       = aws_lambda_function.health_monitor.arn
}

# Cost Tracker Lambda
resource "aws_lambda_function" "cost_tracker" {
  filename         = local.cost_tracker_zip_path
  source_code_hash = filebase64sha256(local.cost_tracker_zip_path)
  function_name    = "${var.project_name}-cost-tracker"
  role             = aws_iam_role.cost_tracker_lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = 900  # 15 minutes for cost calculations
  memory_size      = 512

  environment {
    variables = {
      REGISTRY_TABLE_NAME    = aws_dynamodb_table.app_registry.name
      COSTS_TABLE_NAME       = aws_dynamodb_table.app_costs.name
      EKS_CLUSTER_NAME       = var.eks_cluster_name
      CONFIG_NAME            = var.config_name
    }
  }

  # VPC configuration removed - using public EKS endpoint (no additional cost)

  depends_on = [
    aws_iam_role_policy.cost_tracker_lambda_policy
  ]
}

# Scheduler Lambda
resource "aws_lambda_function" "scheduler" {
  filename         = local.scheduler_zip_path
  source_code_hash = filebase64sha256(local.scheduler_zip_path)
  function_name    = "${var.project_name}-scheduler"
  role             = aws_iam_role.scheduler_lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = 300  # 5 minutes
  memory_size      = 256

  environment {
    variables = {
      REGISTRY_TABLE_NAME       = aws_dynamodb_table.app_registry.name
      SCHEDULES_TABLE_NAME      = aws_dynamodb_table.app_schedules.name
      OPERATION_LOGS_TABLE_NAME  = aws_dynamodb_table.operation_logs.name
      EKS_CLUSTER_NAME           = var.eks_cluster_name
      API_GATEWAY_URL            = ""  # Will be set after API Gateway deployment
      CONFIG_NAME                = var.config_name
    }
  }

  # VPC configuration removed - using public EKS endpoint (no additional cost)

  depends_on = [
    aws_iam_role_policy.scheduler_lambda_policy
  ]
}

# EventBridge Permissions for new Lambdas
resource "aws_lambda_permission" "cost_tracker_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_tracker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cost_tracker_schedule.arn
}

resource "aws_lambda_permission" "scheduler_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.scheduler_schedule.arn
}

# EventBridge Targets for new Lambdas
resource "aws_cloudwatch_event_target" "cost_tracker_target" {
  rule      = aws_cloudwatch_event_rule.cost_tracker_schedule.name
  target_id = "CostTrackerLambdaTarget"
  arn       = aws_lambda_function.cost_tracker.arn
}

resource "aws_cloudwatch_event_target" "scheduler_target" {
  rule      = aws_cloudwatch_event_rule.scheduler_schedule.name
  target_id = "SchedulerLambdaTarget"
  arn       = aws_lambda_function.scheduler.arn
}
