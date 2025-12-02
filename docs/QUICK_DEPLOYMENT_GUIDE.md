# Quick Deployment Guide - New AWS Account

Quick reference for deploying dashboard to a new AWS account. See `DEPLOYMENT_CHECKLIST.md` for detailed steps.

## Quick Steps

### 1. Create Config File
```bash
cp config/config.demo.yaml config/config.newaccount.yaml
# Edit config.newaccount.yaml with new account details
```

### 2. Update Terragrunt
```bash
# Edit infrastructure/terragrunt.hcl
# Set: config_name = "config.newaccount.yaml"
```

### 3. Enable Public EKS Endpoint (Avoid VPC Costs)
```bash
aws eks update-cluster-config --name <cluster-name> --region <region> \
  --resources-vpc-config endpointPublicAccess=true,endpointPrivateAccess=true
```

### 4. Build & Deploy
```bash
export CONFIG_NAME=config.newaccount.yaml
./scripts/deploy-lambdas.sh
cd infrastructure
terragrunt apply -auto-approve
```

### 5. Update Config with API Gateway URL
```bash
# Get API Gateway URL from terragrunt output
cd infrastructure
terragrunt output api_gateway_url

# Update config.newaccount.yaml: ui.api_url
```

### 6. Add Lambda Role to EKS aws-auth
```bash
DISCOVERY_ROLE_ARN=$(aws iam get-role --role-name eks-app-controller-discovery-lambda-role \
  --query 'Role.Arn' --output text)

kubectl get configmap aws-auth -n kube-system -o json | \
  jq '.data.mapRoles += "\n- rolearn: '"$DISCOVERY_ROLE_ARN"'\n  username: lambda-discovery\n  groups:\n  - system:masters"' | \
  kubectl apply -f -
```

### 7. Deploy UI
```bash
export CONFIG_NAME=config.newaccount.yaml
./scripts/deploy-ui.sh
```

### 8. Configure S3 Public Access
```bash
BUCKET="eks-app-controller-ui-<account-id>"

# Disable Block Public Access
aws s3api put-public-access-block --bucket $BUCKET \
  --public-access-block-configuration \
  "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

# Add bucket policy
cat > /tmp/policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::$BUCKET/*"
  }]
}
EOF
aws s3api put-bucket-policy --bucket $BUCKET --policy file:///tmp/policy.json

# Enable website hosting
aws s3 website s3://$BUCKET --index-document index.html --error-document index.html
```

### 9. Test Discovery
```bash
aws lambda invoke --function-name eks-app-controller-discovery \
  --region <region> --payload '{}' /tmp/test.json
cat /tmp/test.json | jq '.'
```

### 10. Disable Auto-Schedule (Optional)
```bash
aws dynamodb scan --table-name eks-app-controller-registry \
  --region <region> --query 'Items[].app_name.S' --output text | \
  tr '\t' '\n' | while read app; do
    aws dynamodb put-item --table-name eks-app-controller-app-schedules \
      --region <region> \
      --item "{\"app\":{\"S\":\"$app\"},\"enabled\":{\"BOOL\":false}}"
  done
```

## Key Configuration Changes

### Files Modified for Multi-Account Support:
1. **`infrastructure/terragrunt.hcl`**: Set `config_name` in inputs
2. **`scripts/load-config.py`**: Respects `CONFIG_NAME` environment variable
3. **`scripts/deploy-ui.sh`**: Respects `CONFIG_NAME` environment variable
4. **`infrastructure/cognito.tf`**: Domain includes account ID suffix to avoid conflicts
5. **`infrastructure/lambdas.tf`**: VPC configuration commented out (uses public EKS endpoint)

### Environment Variables:
- `CONFIG_NAME`: Set to config file name (e.g., `config.demo.yaml`)
- Must be set before running terragrunt commands and deploy scripts

## Cost Optimization

✅ **No Additional Costs** (matches previous deployment):
- EKS cluster: Public endpoint enabled
- Lambda functions: No VPC configuration
- No NAT Gateway
- No VPC endpoints

## Common Issues & Quick Fixes

| Issue | Quick Fix |
|-------|-----------|
| 401 Unauthorized | Add Lambda role to EKS aws-auth ConfigMap |
| Wrong cluster name | Rebuild Lambda packages, update function code |
| S3 403 Forbidden | Disable Block Public Access, add bucket policy |
| No applications | Trigger discovery Lambda manually |
| Config not loading | Set `CONFIG_NAME` environment variable |

## Verification Commands

```bash
# Check EKS endpoint
aws eks describe-cluster --name <cluster> --query 'cluster.resourcesVpcConfig.endpointPublicAccess'

# Check Lambda VPC
aws lambda get-function-configuration --function-name eks-app-controller-discovery --query 'VpcConfig'

# Check applications
aws dynamodb scan --table-name eks-app-controller-registry --select COUNT

# Check schedules
aws dynamodb scan --table-name eks-app-controller-app-schedules --query 'Items[].{app:app.S,enabled:enabled.BOOL}'
```

