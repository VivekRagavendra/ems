# API Gateway
resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
  description   = "API Gateway for EKS Application Controller"

  cors_configuration {
    allow_origins      = ["*"]
    allow_methods      = ["GET", "POST", "OPTIONS"]
    allow_headers      = ["content-type", "Content-Type", "cache-control", "pragma", "authorization", "Authorization"]
    expose_headers     = ["content-type"]
    max_age            = 300
  }
}

# API Gateway Integration for API Handler (GET /apps)
# Note: API Gateway HTTP API has max 30s timeout
resource "aws_apigatewayv2_integration" "api_handler" {
  api_id = aws_apigatewayv2_api.main.id

  integration_uri    = aws_lambda_function.api_handler.invoke_arn
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  timeout_milliseconds = 29000  # Max allowed: 30 seconds (use 29s to be safe)
}

# API Gateway Route for OPTIONS /apps (CORS preflight)
resource "aws_apigatewayv2_route" "options_apps" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /apps"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

# Cognito JWT Authorizer
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-authorizer"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.web.id]
    # Issuer URL format: https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
    issuer   = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  }
}

# Data source for current region (if not already defined)
data "aws_region" "current" {}

# API Gateway Route for GET / (root - API info, no auth required)
resource "aws_apigatewayv2_route" "get_root" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

# API Gateway Route for GET /config/info (returns active config name)
resource "aws_apigatewayv2_route" "get_config_info" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /config/info"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

# API Gateway Route for OPTIONS /config/info (CORS preflight)
resource "aws_apigatewayv2_route" "options_config_info" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /config/info"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

# API Gateway Route for GET /apps (requires authentication)
resource "aws_apigatewayv2_route" "get_apps" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /apps"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# API Gateway Integration for Controller (POST /start, POST /stop)
# Note: API Gateway HTTP API has max 30s timeout, so operations must be async
resource "aws_apigatewayv2_integration" "controller" {
  api_id = aws_apigatewayv2_api.main.id

  integration_uri    = aws_lambda_function.controller.invoke_arn
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  timeout_milliseconds = 29000  # Max allowed: 30 seconds (use 29s to be safe)
}

# API Gateway Routes for Controller (requires authentication)
resource "aws_apigatewayv2_route" "start_app" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /start"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "stop_app" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /stop"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# Database Control Routes (requires authentication)
resource "aws_apigatewayv2_route" "db_start" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /db/start"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "db_stop" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /db/stop"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "options_db_start" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /db/start"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
}

resource "aws_apigatewayv2_route" "options_db_stop" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /db/stop"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
}

# EC2 Control Routes (requires authentication)
# These routes go to API Handler which then invokes Controller
resource "aws_apigatewayv2_route" "ec2_start" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /ec2/start"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "ec2_stop" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /ec2/stop"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "options_ec2_start" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /ec2/start"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

resource "aws_apigatewayv2_route" "options_ec2_stop" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /ec2/stop"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

# OPTIONS routes for CORS preflight
resource "aws_apigatewayv2_route" "options_start" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /start"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
}

resource "aws_apigatewayv2_route" "options_stop" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /stop"
  target    = "integrations/${aws_apigatewayv2_integration.controller.id}"
}

# API Gateway Route for GET /status/quick (quick-status endpoint for Controller)
# Note: This route was already created manually earlier, so we don't recreate it here
# If you need to manage it via Terraform, import it first:
# terraform import aws_apigatewayv2_route.get_status_quick <api-id>/<route-id>

# API Gateway Routes for Cost endpoints (requires authentication)
resource "aws_apigatewayv2_route" "get_app_cost" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /apps/{app_name}/cost"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "options_app_cost" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /apps/{app_name}/cost"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

# API Gateway Routes for Schedule endpoints (requires authentication)
resource "aws_apigatewayv2_route" "get_app_schedule" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /apps/{app_name}/schedule"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "post_app_schedule" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /apps/{app_name}/schedule"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "post_app_schedule_enable" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /apps/{app_name}/schedule/enable"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
  authorizer_id = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "options_app_schedule" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /apps/{app_name}/schedule"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

resource "aws_apigatewayv2_route" "options_app_schedule_enable" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "OPTIONS /apps/{app_name}/schedule/enable"
  target    = "integrations/${aws_apigatewayv2_integration.api_handler.id}"
}

# API Gateway Stage
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true
}

# Lambda Permissions
resource "aws_lambda_permission" "api_handler" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "controller" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.controller.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

output "api_gateway_url" {
  value       = aws_apigatewayv2_api.main.api_endpoint
  description = "API Gateway endpoint URL"
}


