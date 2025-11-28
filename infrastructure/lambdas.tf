# Lambda Functions with proper packaging
# Use pre-built zip files (with dependencies) from build script
# Run ./build-lambdas.sh before deploying

locals {
  discovery_zip_path      = "${path.module}/../build/discovery.zip"
  controller_zip_path     = "${path.module}/../build/controller.zip"
  health_monitor_zip_path = "${path.module}/../build/health-monitor.zip"
  api_handler_zip_path    = "${path.module}/../build/api-handler.zip"
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
    }
  }

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
    }
  }

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
    }
  }

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
      REGISTRY_TABLE_NAME = aws_dynamodb_table.app_registry.name
      EKS_CLUSTER_NAME    = var.eks_cluster_name
    }
  }

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
