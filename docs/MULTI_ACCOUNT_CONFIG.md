# Multi-Account Configuration Support

This document describes how to deploy the same codebase to multiple AWS accounts using different configuration files.

## Overview

The system now supports multiple configuration files, allowing the same codebase to be deployed to different AWS accounts (prod, uat, qa, customer1, etc.) without maintaining separate branches.

## Configuration Files

Configuration files are located in the `config/` directory:

- `config/config.yaml` - Default configuration (used if CONFIG_NAME not set)
- `config/config.prod.yaml` - Production environment
- `config/config.uat.yaml` - UAT environment
- `config/config.qa.yaml` - QA environment
- `config/config.customer1.yaml` - Customer-specific configuration
- etc.

## How It Works

### Lambda Functions

All Lambda functions read the config file name from the `CONFIG_NAME` environment variable:

```python
CONFIG_NAME = os.environ.get("CONFIG_NAME", "config.yaml")
CONFIG_PATH = f"config/{CONFIG_NAME}"
```

If `CONFIG_NAME` is not set, it defaults to `config.yaml`.

### Infrastructure (Terraform/Terragrunt)

1. **Variable Definition** (`infrastructure/main.tf`):
   ```hcl
   variable "config_name" {
     description = "Config file name to use (e.g., config.yaml, config.prod.yaml)"
     type        = string
     default     = "config.yaml"
   }
   ```

2. **Lambda Environment Variables** (`infrastructure/lambdas.tf`):
   All Lambda functions have `CONFIG_NAME` in their environment:
   ```hcl
   environment {
     variables = {
       CONFIG_NAME = var.config_name
       # ... other variables
     }
   }
   ```

3. **Terragrunt Configuration** (`infrastructure/terragrunt.hcl`):
   ```hcl
   inputs = {
     config_name = "config.prod.yaml"  # Override per account
     # ... other inputs
   }
   ```

## Deployment Steps

### For Production Account

1. **Create/Update config file**:
   ```bash
   cp config/config.yaml config/config.prod.yaml
   # Edit config.prod.yaml with production values
   ```

2. **Update terragrunt.hcl**:
   ```hcl
   inputs = {
     config_name = "config.prod.yaml"
     # ... other inputs
   }
   ```

3. **Deploy**:
   ```bash
   cd infrastructure
   terragrunt apply
   ```

### For UAT Account

1. **Create/Update config file**:
   ```bash
   cp config/config.yaml config/config.uat.yaml
   # Edit config.uat.yaml with UAT values
   ```

2. **Update terragrunt.hcl**:
   ```hcl
   inputs = {
     config_name = "config.uat.yaml"
     # ... other inputs
   }
   ```

3. **Deploy**:
   ```bash
   cd infrastructure
   terragrunt apply
   ```

## Build Process

The `scripts/deploy-lambdas.sh` script automatically copies **all** config files to each Lambda package:

```bash
# Copy all config files to Lambda package
cp "$PROJECT_ROOT/config"/config*.yaml "$temp_dir/config/"
```

This ensures that all config files are available in the Lambda package, and the Lambda can load the correct one based on the `CONFIG_NAME` environment variable.

## API Endpoint

A new endpoint is available to check which config file is active:

```bash
GET /config/info

Response:
{
  "config_name": "config.prod.yaml"
}
```

## Fallback Behavior

- If `CONFIG_NAME` environment variable is not set → defaults to `config.yaml`
- If the specified config file is not found → Lambda will fail with a clear error message
- Error message includes the `CONFIG_NAME` value for debugging

## Example: Deploying to Multiple Accounts

### Account 1: Production

```hcl
# infrastructure/terragrunt.hcl
inputs = {
  config_name = "config.prod.yaml"
  # ... other values from config.prod.yaml
}
```

### Account 2: UAT

```hcl
# infrastructure/terragrunt.hcl (in UAT account directory)
inputs = {
  config_name = "config.uat.yaml"
  # ... other values from config.uat.yaml
}
```

### Account 3: Customer1

```hcl
# infrastructure/terragrunt.hcl (in customer1 account directory)
inputs = {
  config_name = "config.customer1.yaml"
  # ... other values from config.customer1.yaml
}
```

## Benefits

1. **Single Codebase**: Same code works for all accounts
2. **No Branch Management**: No need for separate branches per account
3. **Easy Onboarding**: Adding a new account only requires:
   - Creating a new config file: `config/config.<env>.yaml`
   - Setting `config_name` in terragrunt.hcl
4. **Version Control**: All configs in one place, easy to track changes
5. **Consistent Deployment**: Same deployment process for all accounts

## Troubleshooting

### Lambda fails with "Config file not found"

1. Check that the config file exists in `config/` directory
2. Verify `CONFIG_NAME` environment variable is set correctly
3. Ensure the build script copied the config file to the Lambda package
4. Check Lambda logs for the exact error message

### Wrong config being loaded

1. Verify `CONFIG_NAME` environment variable in Lambda function
2. Check terragrunt.hcl `inputs.config_name` value
3. Rebuild and redeploy Lambda functions after changing config_name

## Files Modified

- All `lambdas/*/config/loader.py` - Updated to support CONFIG_NAME
- `scripts/deploy-lambdas.sh` - Updated to copy all config files
- `infrastructure/main.tf` - Added `config_name` variable
- `infrastructure/lambdas.tf` - Added `CONFIG_NAME` to all Lambda environments
- `infrastructure/terragrunt.hcl` - Added `config_name` to inputs
- `infrastructure/api_gateway.tf` - Added `/config/info` route
- `lambdas/api-handler/lambda_function.py` - Added `/config/info` endpoint

