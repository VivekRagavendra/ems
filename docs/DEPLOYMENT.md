# Deployment Guide

This guide walks you through deploying the EKS Application Start/Stop Controller system.

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **OpenTofu** >= 1.0 installed (or Terraform >= 1.0)
3. **Terragrunt** >= 0.50.0 installed
4. **Python** 3.11+ for Lambda functions
5. **Node.js** 18+ for UI build
6. **kubectl** configured to access your EKS cluster
7. **AWS Permissions**:
   - EKS cluster access
   - EC2 read/write
   - Lambda create/update
   - DynamoDB create/update
   - API Gateway create/update
   - IAM role creation
   - EventBridge rule creation

## Step 1: Configure Terragrunt

Copy the example Terragrunt configuration and update with your values:

```bash
cd infrastructure
cp terragrunt.hcl.example terragrunt.hcl
```

Edit `terragrunt.hcl` and update the `inputs` section:

```hcl
inputs = {
  aws_region       = "us-east-1"              # Your AWS region
  eks_cluster_name = "your-eks-cluster-name"  # Your EKS cluster name
  project_name     = "eks-app-controller"
  lambda_runtime   = "python3.11"
}
```

## Step 2: Package Lambda Functions

**Important**: The Terraform configuration uses `archive_file` which packages source code but does NOT install Python dependencies. You have two options:

### Option A: Pre-package with Dependencies (Recommended)

Before deploying with Terraform, package the Lambda functions with dependencies:

```bash
chmod +x scripts/deploy-lambdas.sh
./scripts/deploy-lambdas.sh
```

This creates zip files with dependencies in the `build/` directory. Then update `infrastructure/lambdas.tf` to reference these files instead of using `archive_file`.

### Option B: Use Terraform archive_file (Dependencies Not Included)

The current Terraform configuration will package the source code, but you'll need to install dependencies separately or use Lambda Layers. This is simpler but requires additional setup for dependencies.

## Step 4: Deploy Infrastructure

Initialize and apply with Terragrunt:

```bash
cd infrastructure
terragrunt init
terragrunt plan
terragrunt apply
```

This creates:
- DynamoDB table
- Lambda functions
- IAM roles and policies
- API Gateway
- EventBridge rules

**Note**: Terragrunt will automatically download OpenTofu if not installed.

## Step 5: Configure Lambda Access to EKS

The Discovery Lambda needs access to your EKS cluster. You have two options:

### Option A: Run Lambda in EKS (Recommended)

Deploy the Lambda as a Kubernetes Job or use AWS Lambda with VPC configuration to access EKS.

### Option B: Use kubectl from Lambda

Configure the Lambda to use kubectl by:
1. Adding kubectl binary to Lambda package
2. Configuring kubeconfig via environment variables
3. Using AWS IAM roles for EKS access

## Step 6: Tag Your Resources

Ensure all resources are properly tagged:

**EC2 Database Instances:**
```bash
aws ec2 create-tags \
  --resources i-1234567890abcdef0 \
  --tags Key=AppName,Value=mi.dev.mareana.com \
         Key=Component,Value=postgres \
         Key=Shared,Value=false
```

**NodeGroups:**
Tag NodeGroups via EKS console or AWS CLI:
```bash
aws eks tag-resource \
  --resource-arn arn:aws:eks:region:account:nodegroup/cluster/nodegroup-name \
  --tags AppName=mi.dev.mareana.com,Component=nodegroup
```

## Step 7: Run Initial Discovery

Trigger the discovery Lambda manually to populate the registry:

```bash
aws lambda invoke \
  --function-name eks-app-controller-discovery \
  --payload '{}' \
  response.json
```

## Step 8: Deploy UI

Build and deploy the React UI:

```bash
# Get API Gateway URL from Terragrunt output
API_URL=$(terragrunt output -raw api_gateway_url)

# Deploy UI (create S3 bucket first if needed)
S3_BUCKET=eks-app-controller-ui
API_URL=$API_URL ./scripts/deploy-ui.sh
```

## Step 9: Configure CloudFront (Optional)

For production, set up CloudFront distribution:

1. Create CloudFront distribution pointing to S3 bucket
2. Configure custom domain (optional)
3. Set up SSL certificate
4. Update CORS settings in API Gateway if needed

## Step 10: Verify Deployment

1. **Check DynamoDB**: Verify applications are registered
2. **Check Lambda Logs**: Review CloudWatch logs for errors
3. **Test API**: Use curl or Postman to test endpoints
4. **Access UI**: Open the CloudFront/S3 URL

## Troubleshooting

### Lambda can't access EKS

- Verify IAM roles have EKS permissions
- Check VPC configuration if Lambda is in VPC
- Verify kubectl/kubeconfig setup

### Discovery not finding applications

- Verify Ingress resources exist
- Check Lambda logs in CloudWatch
- Ensure proper Kubernetes RBAC permissions

### API Gateway CORS errors

- Verify CORS configuration in `api_gateway.tf`
- Check browser console for specific errors
- Ensure API Gateway stage is deployed

### Shared resources not detected

- Verify EC2 tags are correct
- Check Discovery Lambda logic for shared resource detection
- Review DynamoDB registry entries

## Next Steps

- Set up authentication (Cognito, API Keys, etc.)
- Configure CloudWatch alarms
- Set up backup for DynamoDB
- Review and adjust EventBridge schedules
- Add monitoring and alerting

