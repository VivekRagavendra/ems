# Configuration Guide

## Overview

The EKS Application Start/Stop Controller uses a **single configuration file** (`config/config.yaml`) for all account-specific settings. This makes it easy to deploy the system to multiple AWS accounts by changing only one file.

## Configuration File Location

- **Production config**: `config/config.yaml`
- **Template**: `config/config.example.yaml`

## Quick Start

1. Copy the example configuration:
   ```bash
   cp config/config.example.yaml config/config.yaml
   ```

2. Edit `config/config.yaml` with your AWS account details:
   ```yaml
   aws:
     account_id: "123456789012"  # Your AWS account ID
     region: "us-east-1"         # Your AWS region
   
   eks:
     cluster_name: "my-eks-cluster"  # Your EKS cluster name
   ```

3. Deploy the system - all components will automatically use these values!

## Configuration Sections

### AWS Configuration

```yaml
aws:
  account_id: "123456789012"  # Your AWS account ID
  region: "us-east-1"         # AWS region for all resources
```

### EKS Configuration

```yaml
eks:
  cluster_name: "my-eks-cluster"  # Name of your EKS cluster
```

### DynamoDB Configuration

```yaml
dynamodb:
  table_name: "eks-app-controller-registry"  # DynamoDB table name
```

### S3 Configuration

```yaml
s3:
  ui_bucket_name: "my-ui-bucket"  # S3 bucket for hosting the UI
```

### Application Mappings

#### Namespace Mapping

Maps application hostnames to Kubernetes namespaces:

```yaml
app_namespace_mapping:
  "app1.example.com": "namespace1"
  "app2.example.com": "namespace2"
```

#### NodeGroup Defaults

Defines NodeGroup scaling defaults for each application:

```yaml
nodegroup_defaults:
  "app1.example.com":
    nodegroup: "nodegroup-name"
    desired: 1
    min: 1
    max: 2
  "app2.example.com": null  # No NodeGroup, only pod scaling
```

### EC2 Tag Configuration

```yaml
ec2_tags:
  app_name_key: "AppName"      # EC2 tag key for application name
  component_key: "Component"    # EC2 tag key for component type
  shared_key: "Shared"          # EC2 tag key for shared resources
```

### EventBridge Schedules

```yaml
eventbridge:
  discovery_schedule: "rate(2 hours)"        # How often to discover apps
  health_check_schedule: "rate(15 minutes)"  # How often to check health
```

### Lambda Configuration

```yaml
lambda:
  runtime: "python3.11"  # Python runtime version
  memory_size: 256       # MB
  timeout: 90           # seconds
```

### UI Configuration

```yaml
ui:
  auto_refresh_interval: 30  # seconds
  api_url: ""              # API Gateway URL (set after deployment)
```

### Project Configuration

```yaml
project:
  name: "eks-app-controller"  # Used for resource naming
```

## How Configuration is Used

### Lambda Functions

All Lambda functions (`api-handler`, `controller`, `discovery`, `health-monitor`) load configuration at runtime using the `config.loader` module:

```python
from config.loader import get_eks_cluster_name, get_dynamodb_table_name

cluster_name = get_eks_cluster_name()
table_name = get_dynamodb_table_name()
```

The config is cached after first load for performance.

### Terraform/Terragrunt

Terragrunt reads configuration using a Python script:

```hcl
locals {
  config_json = jsondecode(run_cmd("python3", "scripts/load-config.py"))
  aws_region = local.config_json.aws.region
  eks_cluster_name = local.config_json.eks.cluster_name
}
```

### Deployment Scripts

Deployment scripts (`deploy-ui.sh`, `deploy-lambdas.sh`) read configuration directly:

```bash
S3_BUCKET=$(python3 -c "import yaml; print(yaml.safe_load(open('config/config.yaml'))['s3']['ui_bucket_name'])")
```

### React UI

The UI loads API URL from a generated `config.json` file (created during build from `config.yaml`).

## Multi-Account Deployment

To deploy to a new AWS account:

1. **Copy the example config**:
   ```bash
   cp config/config.example.yaml config/config.yaml
   ```

2. **Update account-specific values**:
   - AWS account ID
   - AWS region
   - EKS cluster name
   - S3 bucket name
   - Application mappings (namespaces, NodeGroups)
   - EC2 tag keys (if different)

3. **Deploy**:
   ```bash
   ./build-lambdas.sh
   cd infrastructure && terragrunt apply
   ./scripts/deploy-ui.sh
   ```

**That's it!** No code changes required.

## Environment Variable Override

For testing or special cases, you can override config values using environment variables:

- `CONFIG_PATH`: Path to config file (default: `config/config.yaml`)
- `EKS_CLUSTER_NAME`: Override EKS cluster name
- `REGISTRY_TABLE_NAME`: Override DynamoDB table name

Lambda functions will fall back to environment variables if config loading fails.

## Validation

The config loader validates required fields on load. Missing required fields will cause an error:

```
ValueError: Missing required configuration fields: aws.account_id, aws.region, eks.cluster_name
```

## Best Practices

1. **Never commit `config/config.yaml`** - Add it to `.gitignore` (already done)
2. **Use `config/config.example.yaml`** as a template
3. **Document custom mappings** in your team's wiki/docs
4. **Version control** your config separately (e.g., in a private repo or secrets manager)
5. **Test config changes** in a dev environment first

## Troubleshooting

### Config file not found

**Error**: `FileNotFoundError: config/config.yaml not found`

**Solution**: Copy `config/config.example.yaml` to `config/config.yaml` and update values.

### Invalid YAML syntax

**Error**: `Error parsing config.yaml: ...`

**Solution**: Validate your YAML syntax using an online YAML validator or `python3 -c "import yaml; yaml.safe_load(open('config/config.yaml'))"`

### Missing required fields

**Error**: `Missing required configuration fields: ...`

**Solution**: Check `config/config.example.yaml` for all required fields and ensure they're present in your config.

### Lambda can't find config

**Error**: `⚠️ Warning: Could not load config.yaml: ...`

**Solution**: 
- Ensure `config/config.yaml` is copied to each Lambda package during build
- Check that `build-lambdas.sh` is copying the config directory
- Verify the config file is in the Lambda package ZIP

## See Also

- [README.md](../README.md) - Main documentation
- [QUICKSTART.md](../QUICKSTART.md) - Quick start guide
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide

