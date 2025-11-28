# Migration Guide: Terraform to OpenTofu + Terragrunt

This guide helps you migrate from the original Terraform setup to OpenTofu with Terragrunt.

## What Changed

- **Terraform** → **OpenTofu** (Terraform-compatible, open-source fork)
- **terraform.tfvars** → **terragrunt.hcl** (Terragrunt configuration)
- **terraform commands** → **terragrunt commands**

## Benefits

1. **OpenTofu**: Open-source, community-driven alternative to Terraform
2. **Terragrunt**: DRY (Don't Repeat Yourself) configuration, better state management
3. **Backward Compatible**: OpenTofu is compatible with Terraform code

## Migration Steps

### Step 1: Install OpenTofu and Terragrunt

```bash
# Install OpenTofu
brew install opentofu/tap/opentofu  # macOS
# or download from https://github.com/opentofu/opentofu/releases

# Install Terragrunt
brew install terragrunt  # macOS
# or download from https://github.com/gruntwork-io/terragrunt/releases
```

Verify:
```bash
tofu version
terragrunt --version
```

### Step 2: Backup Existing State

If you have existing Terraform state:

```bash
cd infrastructure
# Backup state file
cp terraform.tfstate terraform.tfstate.backup
```

### Step 3: Create Terragrunt Configuration

```bash
cd infrastructure
cp terragrunt.hcl.example terragrunt.hcl
```

Edit `terragrunt.hcl` and update the `inputs` section with your values:

```hcl
inputs = {
  aws_region       = "us-east-1"              # Your region
  eks_cluster_name = "your-eks-cluster-name"  # Your cluster
  project_name     = "eks-app-controller"
  lambda_runtime   = "python3.11"
}
```

### Step 4: Remove Old Terraform Files

```bash
# Remove old tfvars file (no longer needed)
rm terraform.tfvars  # if it exists
```

### Step 5: Initialize with Terragrunt

```bash
cd infrastructure
terragrunt init
```

This will:
- Download OpenTofu automatically (if not installed)
- Initialize providers
- Migrate state (if using local state)

### Step 6: Verify Configuration

```bash
terragrunt plan
```

Review the plan to ensure everything looks correct.

### Step 7: Apply Changes

```bash
terragrunt apply
```

## Command Mapping

| Old (Terraform) | New (Terragrunt) |
|-----------------|------------------|
| `terraform init` | `terragrunt init` |
| `terraform plan` | `terragrunt plan` |
| `terraform apply` | `terragrunt apply` |
| `terraform destroy` | `terragrunt destroy` |
| `terraform output` | `terragrunt output` |
| `terraform.tfvars` | `terragrunt.hcl` (inputs section) |

## Remote State (Optional)

If you want to use S3 backend for state management, update `terragrunt.hcl`:

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
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}
```

Then create the S3 bucket and DynamoDB table:

```bash
# Create S3 bucket
aws s3 mb s3://your-terragrunt-state-bucket
aws s3api put-bucket-versioning \
  --bucket your-terragrunt-state-bucket \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for locking
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

## Rollback (If Needed)

If you need to rollback to Terraform:

1. Restore state backup:
   ```bash
   cp terraform.tfstate.backup terraform.tfstate
   ```

2. Use Terraform commands:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

## Troubleshooting

### OpenTofu Not Found

Terragrunt will auto-download OpenTofu, but you can install manually:
```bash
brew install opentofu/tap/opentofu
```

### State Migration Issues

If state migration fails:
1. Check state file permissions
2. Ensure AWS credentials are configured
3. Try `terragrunt init -reconfigure`

### Provider Version Conflicts

If you see provider version issues, update `terragrunt.hcl`:
```hcl
generate "provider" {
  # ... update provider versions in contents block
}
```

## Additional Resources

- [OpenTofu Documentation](https://opentofu.org/docs)
- [Terragrunt Documentation](https://terragrunt.gruntwork.io/docs)
- [OpenTofu vs Terraform](https://opentofu.org/docs/intro/vs-terraform)

## Questions?

- Check `infrastructure/README.md` for Terragrunt usage
- Review `docs/DEPLOYMENT.md` for deployment steps
- See `docs/PREREQUISITES.md` for requirements

