# Multi-Account Deployment Refactoring Summary

## Overview

This refactoring enables the EKS Application Start/Stop Controller to support multi-AWS-account deployments with a **single configuration file** (`config/config.yaml`). All account-specific values have been moved from hard-coded values in the codebase to this centralized configuration file.

## What Changed

### ✅ New Files Created

1. **`config/config.yaml`** - Production configuration file (account-specific)
2. **`config/config.example.yaml`** - Template configuration file
3. **`config/loader.py`** - Python config loader utility for Lambda functions
4. **`config/__init__.py`** - Config module init file
5. **`scripts/load-config.py`** - Script to load and output config as JSON (for Terraform/Terragrunt)
6. **`docs/CONFIGURATION.md`** - Complete configuration guide

### ✅ Files Updated

#### Lambda Functions
- **`lambdas/api-handler/lambda_function.py`** - Now reads from config.yaml
- **`lambdas/controller/lambda_function.py`** - Now reads from config.yaml
- **`lambdas/discovery/lambda_function.py`** - Now reads from config.yaml
- **`lambdas/health-monitor/lambda_function.py`** - Now reads from config.yaml
- **All Lambda `requirements.txt`** - Added `PyYAML>=6.0` dependency

#### Infrastructure
- **`infrastructure/terragrunt.hcl`** - Now reads from config.yaml via Python script
- **`infrastructure/main.tf`** - No changes (already uses variables from Terragrunt)

#### Deployment Scripts
- **`scripts/deploy-ui.sh`** - Reads S3 bucket and API URL from config.yaml
- **`scripts/deploy-lambdas.sh`** - Copies config directory to Lambda packages
- **`build-lambdas.sh`** - Copies config.yaml to Lambda packages

#### UI
- **`ui/src/App.jsx`** - Loads API URL from config.json (generated during build)

#### Documentation
- **`README.md`** - Added multi-account support section
- **`QUICKSTART.md`** - Added configuration step at the beginning
- **`.gitignore`** - Added `config/config.yaml` (but keeps `config/config.example.yaml`)

## Configuration Structure

All account-specific values are now in `config/config.yaml`:

```yaml
aws:
  account_id: "420464349284"
  region: "us-east-1"

eks:
  cluster_name: "mi-eks-cluster"

dynamodb:
  table_name: "eks-app-controller-registry"

s3:
  ui_bucket_name: "eks-app-controller-ui"

app_namespace_mapping:
  "app.example.com": "namespace"

nodegroup_defaults:
  "app.example.com":
    nodegroup: "nodegroup-name"
    desired: 1
    min: 1
    max: 2

# ... and more
```

## How It Works

### Lambda Functions

1. Each Lambda function imports `config.loader` module
2. On first invocation, loads `config/config.yaml` (cached for subsequent calls)
3. Falls back to environment variables if config loading fails
4. All hard-coded mappings replaced with config reads

### Terraform/Terragrunt

1. Terragrunt runs `scripts/load-config.py` to read config.yaml
2. Parses JSON output and extracts values
3. Passes values to Terraform as variables
4. All infrastructure resources use these values

### Deployment Scripts

1. Scripts use Python to read config.yaml directly
2. Extract values (S3 bucket, API URL, etc.)
3. Use values during deployment
4. Generate `config.json` for UI during build

### React UI

1. UI loads `/config.json` on mount (generated from config.yaml during build)
2. Falls back to environment variable `VITE_API_URL`
3. Falls back to default placeholder URL

## Migration Guide

### For Existing Deployments

1. **Backup your current deployment**
2. **Create config file**:
   ```bash
   cp config/config.example.yaml config/config.yaml
   ```
3. **Update config.yaml** with your current values:
   - AWS account ID
   - AWS region
   - EKS cluster name
   - S3 bucket name
   - Application mappings (namespaces, NodeGroups)
4. **Rebuild and redeploy**:
   ```bash
   ./build-lambdas.sh
   cd infrastructure && terragrunt apply
   ./scripts/deploy-ui.sh
   ```

### For New Deployments

1. **Copy example config**:
   ```bash
   cp config/config.example.yaml config/config.yaml
   ```
2. **Edit config.yaml** with your AWS account details
3. **Deploy** - everything uses config.yaml automatically!

## Benefits

✅ **Single Source of Truth** - All account settings in one file  
✅ **No Code Changes** - Deploy to new accounts by editing one file  
✅ **Version Control Safe** - Config file excluded from git (contains secrets)  
✅ **Easy Testing** - Test different configs without code changes  
✅ **Team Collaboration** - Share config.example.yaml, keep config.yaml private  
✅ **Backward Compatible** - Falls back to environment variables if config missing  

## Testing

After refactoring, verify:

1. **Config loading works**:
   ```bash
   python3 scripts/load-config.py
   ```

2. **Lambda functions can load config**:
   - Check CloudWatch logs for config loading messages
   - Verify no "Could not load config.yaml" warnings

3. **Terraform reads config**:
   ```bash
   cd infrastructure
   terragrunt plan  # Should use values from config.yaml
   ```

4. **UI loads API URL**:
   - Check browser console for API URL
   - Verify API calls work

## Troubleshooting

### Config file not found
- Ensure `config/config.yaml` exists
- Check file permissions
- Verify path in Lambda packages

### Invalid YAML
- Validate YAML syntax
- Check indentation (must be spaces, not tabs)
- Use online YAML validator

### Lambda can't import config
- Verify `config/` directory is in Lambda package
- Check `build-lambdas.sh` copies config
- Ensure PyYAML is in requirements.txt

### Terraform can't read config
- Verify Python 3 is available
- Check `scripts/load-config.py` is executable
- Test script manually: `python3 scripts/load-config.py`

## Next Steps

1. **Update config.yaml** with your production values
2. **Test in dev environment** first
3. **Deploy to production**
4. **Document your custom mappings** for your team

## See Also

- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - Complete configuration guide
- [README.md](README.md) - Main documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide

