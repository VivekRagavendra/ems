# Cognito User Pool for Authentication
resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-user-pool"

  admin_create_user_config {
    allow_admin_create_user_only = false  # Allow self-registration for initial setup
  }

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }

  auto_verified_attributes = ["email"]

  tags = {
    Name        = "${var.project_name}-user-pool"
    Environment = "production"
  }
}

# Cognito User Pool Client (for web application)
resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project_name}-web-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                = ["email", "openid", "profile"]
  
  # Callback URLs - will be updated after deployment
  # Note: S3 bucket URL should be added manually after deployment
  callback_urls = [
    "http://localhost:5173"  # Vite dev server
    # Add production URL manually: "https://<bucket-name>.s3-website-<region>.amazonaws.com"
  ]
  
  logout_urls = [
    "http://localhost:5173"
    # Add production URL manually: "https://<bucket-name>.s3-website-<region>.amazonaws.com"
  ]

  supported_identity_providers = ["COGNITO"]

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",      # Required for amazon-cognito-identity-js
    "ALLOW_USER_PASSWORD_AUTH",  # Alternative auth flow
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]
}

# Cognito User Pool Domain
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-auth-${substr(var.aws_account_id, -4, 4)}"  # Add account suffix to avoid conflicts
  user_pool_id = aws_cognito_user_pool.main.id
}

# Outputs
output "cognito_user_pool_id" {
  value       = aws_cognito_user_pool.main.id
  description = "Cognito User Pool ID"
}

output "cognito_client_id" {
  value       = aws_cognito_user_pool_client.web.id
  description = "Cognito User Pool Client ID"
}

output "cognito_domain" {
  value       = aws_cognito_user_pool_domain.main.domain
  description = "Cognito User Pool Domain"
}

output "cognito_issuer_url" {
  value       = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  description = "Cognito Issuer URL for JWT validation"
}

output "cognito_hosted_ui_url" {
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${data.aws_region.current.name}.amazoncognito.com"
  description = "Cognito Hosted UI URL (for login redirects)"
}

