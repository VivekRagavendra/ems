# Infrastructure as Code with OpenTofu and Terragrunt

This directory contains OpenTofu configuration managed by Terragrunt for deploying the EKS Application Controller infrastructure.

## Prerequisites

- **OpenTofu** >= 1.0 (or Terraform >= 1.0)
- **Terragrunt** >= 0.50.0

## Installation

### Install OpenTofu

```bash
# macOS
brew install opentofu/tap/opentofu

# Linux
wget https://github.com/opentofu/opentofu/releases/download/v1.6.0/tofu_1.6.0_linux_amd64.zip
unzip tofu_1.6.0_linux_amd64.zip
sudo mv tofu /usr/local/bin/
```

### Install Terragrunt

```bash
# macOS
brew install terragrunt

# Linux
wget https://github.com/gruntwork-io/terragrunt/releases/download/v0.50.0/terragrunt_linux_amd64
chmod +x terragrunt_linux_amd64
sudo mv terragrunt_linux_amd64 /usr/local/bin/terragrunt
```

Verify installations:
```bash
tofu version
terragrunt --version
```

## Configuration

### Step 1: Configure Terragrunt

Copy the example configuration:

```bash
cp terragrunt.hcl.example terragrunt.hcl
```

Edit `terragrunt.hcl` and update:

```hcl
inputs = {
  aws_region       = "us-east-1"              # Your AWS region
  eks_cluster_name = "your-eks-cluster-name"  # Your EKS cluster name
  project_name     = "eks-app-controller"
  lambda_runtime   = "python3.11"
}
```

### Step 2: Configure Remote State (Optional but Recommended)

For production, configure S3 backend for state management:

```hcl
remote_state {
  backend = "s3"
  config = {
    bucket         = "your-terragrunt-state-bucket"
    key            = "eks-app-controller/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}
```

## Usage

### Initialize

```bash
terragrunt init
```

This will:
- Download OpenTofu if not present
- Initialize providers
- Set up backend (if configured)

### Plan

```bash
terragrunt plan
```

### Apply

```bash
terragrunt apply
```

### Destroy

```bash
terragrunt destroy
```

### Outputs

```bash
terragrunt output
```

Get specific output:
```bash
terragrunt output api_gateway_url
```

## File Structure

```
infrastructure/
├── terragrunt.hcl          # Terragrunt configuration (create from example)
├── terragrunt.hcl.example  # Example configuration
├── main.tf                 # Core infrastructure (DynamoDB, IAM, EventBridge)
├── lambdas.tf              # Lambda functions
├── api_gateway.tf          # API Gateway configuration
├── variables.tf            # Variable definitions
└── outputs.tf              # Output definitions
```

## How It Works

1. **Terragrunt** reads `terragrunt.hcl`
2. Generates `provider.tf` with provider configuration
3. Passes `inputs` as variables to OpenTofu
4. OpenTofu executes the Terraform-compatible code
5. State is managed (locally or in S3 backend)

## Lambda Dependencies

The Lambda functions need Python dependencies installed. You have two options:

### Option A: Pre-package with Dependencies (Recommended)

Before running Terragrunt, package Lambda functions:

```bash
cd ..
./scripts/deploy-lambdas.sh
```

The Terragrunt/OpenTofu configuration will use the pre-built zip files.

### Option B: Use archive_file Data Source

The current configuration uses `archive_file` which packages source code but doesn't install dependencies. You'll need to:
- Install dependencies separately
- Use Lambda Layers
- Or modify the packaging process

## Remote State Backend

For team collaboration and state locking, configure S3 backend:

1. Create S3 bucket for state:
```bash
aws s3 mb s3://your-terragrunt-state-bucket
aws s3api put-bucket-versioning \
  --bucket your-terragrunt-state-bucket \
  --versioning-configuration Status=Enabled
```

2. Create DynamoDB table for locking:
```bash
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

3. Update `terragrunt.hcl` with backend configuration

## Environment-Specific Deployments

You can create multiple environments:

```
infrastructure/
├── environments/
│   ├── dev/
│   │   └── terragrunt.hcl
│   ├── staging/
│   │   └── terragrunt.hcl
│   └── prod/
│       └── terragrunt.hcl
└── [shared .tf files]
```

Each environment's `terragrunt.hcl` can have different inputs.

## Troubleshooting

### OpenTofu not found

Terragrunt will download OpenTofu automatically, or install it manually:
```bash
brew install opentofu/tap/opentofu
```

### Provider initialization fails

Check AWS credentials:
```bash
aws sts get-caller-identity
```

### State lock errors

If using DynamoDB backend, check for stale locks:
```bash
aws dynamodb scan --table-name terraform-locks
```

### Lambda packaging issues

Ensure build directory exists:
```bash
mkdir -p ../build
```

## Migration from Terraform

If migrating from pure Terraform:

1. Install Terragrunt and OpenTofu
2. Create `terragrunt.hcl` from example
3. Remove `terraform.tfvars` (use Terragrunt inputs instead)
4. Run `terragrunt init` (will migrate state)
5. Run `terragrunt plan` to verify

## Additional Resources

- [OpenTofu Documentation](https://opentofu.org/docs)
- [Terragrunt Documentation](https://terragrunt.gruntwork.io/docs)
- [AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
