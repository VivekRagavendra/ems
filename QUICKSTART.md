# Quick Start Guide

Get the EKS Application Controller up and running in 15 minutes.

## Prerequisites Check

```bash
# Check AWS CLI
aws --version

# Check OpenTofu
tofu version

# Check Terragrunt
terragrunt --version

# Check Python
python3 --version

# Check Node.js
node --version

# Check kubectl access
kubectl get nodes
```

## Step 1: Clone and Setup

```bash
cd /Users/viveks/EMS

# Install Python dependencies (for Lambda packaging)
pip3 install -r requirements.txt

# Install Node dependencies (for UI)
cd ui && npm install && cd ..
```

## Step 2: Configure Terragrunt

```bash
cd infrastructure
cp terragrunt.hcl.example terragrunt.hcl
# Edit terragrunt.hcl with your values (update inputs section)
```

## Step 3: Tag Your Resources

**Tag EC2 Database Instances:**
```bash
# PostgreSQL
aws ec2 create-tags \
  --resources i-1234567890abcdef0 \
  --tags \
    Key=AppName,Value=mi.dev.mareana.com \
    Key=Component,Value=postgres \
    Key=Shared,Value=false

# Neo4j
aws ec2 create-tags \
  --resources i-0987654321fedcba0 \
  --tags \
    Key=AppName,Value=mi.dev.mareana.com \
    Key=Component,Value=neo4j \
    Key=Shared,Value=false
```

**Tag NodeGroups:**
```bash
aws eks tag-resource \
  --resource-arn arn:aws:eks:region:account:nodegroup/cluster/nodegroup-name/... \
  --tags AppName=mi.dev.mareana.com,Component=nodegroup
```

## Step 4: Deploy Infrastructure

```bash
cd infrastructure
terragrunt init
terragrunt plan
terragrunt apply
```

Note: 
- Terragrunt will automatically download OpenTofu if not installed
- The first apply will create zip files automatically via OpenTofu's `archive_file` data source

## Step 5: Configure Lambda EKS Access

The Discovery Lambda needs Kubernetes access. Choose one:

**Option A: Run Lambda in EKS Pod (Recommended)**
- Deploy Lambda as Kubernetes Job
- Use service account with RBAC permissions

**Option B: Configure kubectl in Lambda**
- Package kubectl binary in Lambda
- Set KUBECONFIG environment variable
- Use AWS IAM for EKS authentication

## Step 6: Run Initial Discovery

```bash
# Get Lambda function name from Terragrunt output
DISCOVERY_LAMBDA=$(terragrunt output -raw discovery_lambda_name)

# Invoke discovery
aws lambda invoke \
  --function-name $DISCOVERY_LAMBDA \
  --payload '{}' \
  response.json

cat response.json
```

## Step 7: Deploy UI

```bash
# Get API Gateway URL
API_URL=$(terragrunt output -raw api_gateway_url)

# Create S3 bucket for UI (if not exists)
aws s3 mb s3://eks-app-controller-ui

# Deploy UI
cd ..
S3_BUCKET=eks-app-controller-ui API_URL=$API_URL ./scripts/deploy-ui.sh
```

## Step 8: Access Dashboard

```bash
# Get S3 website URL or CloudFront URL
aws s3 website s3://eks-app-controller-ui --index-document index.html

# Or set up CloudFront distribution
# See docs/DEPLOYMENT.md for CloudFront setup
```

## Verify Everything Works

1. **Check DynamoDB Registry:**
   ```bash
   aws dynamodb scan --table-name eks-app-controller-registry
   ```

2. **Test API:**
   ```bash
   curl $API_URL/apps
   ```

3. **Test Start/Stop:**
   ```bash
   curl -X POST $API_URL/start \
     -H "Content-Type: application/json" \
     -d '{"app_name": "mi.dev.mareana.com"}'
   ```

4. **Check Lambda Logs:**
   ```bash
   aws logs tail /aws/lambda/eks-app-controller-discovery --follow
   ```

## Next Steps

- Review [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment
- Read [docs/RUNBOOK.md](docs/RUNBOOK.md) for operations
- Check [docs/TAGGING.md](docs/TAGGING.md) for tagging requirements
- See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design

## Troubleshooting

**Terragrunt/OpenTofu issues:**
- Ensure Terragrunt is installed: `terragrunt --version`
- Terragrunt will auto-download OpenTofu, or install manually: `brew install opentofu/tap/opentofu`
- Check `terragrunt.hcl` configuration is correct

**No applications discovered:**
- Check Ingress resources exist: `kubectl get ingress -A`
- Verify resource tags are correct
- Check Discovery Lambda logs

**Start/Stop fails:**
- Verify IAM permissions
- Check Controller Lambda logs
- Ensure resources exist and are tagged

**UI shows errors:**
- Verify API Gateway URL is correct
- Check CORS configuration
- Review browser console for errors

## Support

For issues or questions:
1. Check CloudWatch logs for Lambda functions
2. Review Terraform outputs
3. Verify resource tagging
4. Consult documentation in `docs/` directory

