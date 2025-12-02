# Dashboard Deployment Checklist

This checklist is for deploying the EKS Application Controller dashboard to a new AWS account. Based on the demo account (480787231313) deployment experience.

## Prerequisites

- [ ] AWS CLI configured with target account credentials
- [ ] EKS cluster exists in the target account
- [ ] kubectl configured to access the EKS cluster
- [ ] Python 3.11+ installed
- [ ] Node.js 18+ installed (for UI build)
- [ ] Terragrunt installed
- [ ] OpenTofu/Terraform installed

## Step 1: Prepare Configuration File

- [ ] Create config file for the new account (e.g., `config.newaccount.yaml`)
- [ ] Update the following in the config file:
  - [ ] `aws.account_id`: Target AWS account ID
  - [ ] `aws.region`: Target AWS region
  - [ ] `eks.cluster_name`: EKS cluster name in target account
  - [ ] `dynamodb.table_name`: DynamoDB table name (usually `eks-app-controller-registry`)
  - [ ] `s3.ui_bucket_name`: S3 bucket name for UI (format: `eks-app-controller-ui-{account-id}`)
  - [ ] `app_namespace_mapping`: Map hostnames to Kubernetes namespaces
  - [ ] `nodegroup_defaults`: NodeGroup scaling defaults for each application
  - [ ] `ui.api_url`: Will be updated after API Gateway deployment

## Step 2: Verify EKS Cluster Configuration

- [ ] Check EKS cluster endpoint access:
  ```bash
  aws eks describe-cluster --name <cluster-name> --region <region> \
    --query 'cluster.resourcesVpcConfig.endpointPublicAccess'
  ```
- [ ] **If `endpointPublicAccess: false`**: Enable public endpoint to avoid VPC costs:
  ```bash
  aws eks update-cluster-config --name <cluster-name> --region <region> \
    --resources-vpc-config endpointPublicAccess=true,endpointPrivateAccess=true
  ```
- [ ] Wait for cluster update to complete (takes 5-10 minutes)

## Step 3: Update Infrastructure Configuration

- [ ] Update `infrastructure/terragrunt.hcl`:
  - [ ] Set `config_name = "config.newaccount.yaml"` in inputs section
  - [ ] Verify `terragrunt.hcl` passes CONFIG_NAME to load-config.py script:
    ```hcl
    config_json = try(
      jsondecode(run_cmd("--terragrunt-quiet", "bash", "-c", 
        "export CONFIG_NAME='${local.config_name}' && python3 ${get_parent_terragrunt_dir()}/scripts/load-config.py")),
      {}
    )
    ```

## Step 4: Build Lambda Packages

- [ ] Rebuild Lambda packages to include all config files:
  ```bash
  ./scripts/deploy-lambdas.sh
  ```
- [ ] Verify all config files are included:
  ```bash
  unzip -l build/discovery.zip | grep "config.*\.yaml"
  ```
- [ ] Should see: `config.yaml`, `config.demo.yaml`, `config.newaccount.yaml`, etc.

## Step 5: Deploy Infrastructure

- [ ] Set CONFIG_NAME environment variable:
  ```bash
  export CONFIG_NAME=config.newaccount.yaml
  ```
- [ ] Initialize Terragrunt:
  ```bash
  cd infrastructure
  terragrunt init
  ```
- [ ] Review plan:
  ```bash
  terragrunt plan
  ```
- [ ] Apply infrastructure:
  ```bash
  terragrunt apply -auto-approve
  ```
- [ ] Note the API Gateway URL from outputs

## Step 6: Update Configuration with API Gateway URL

- [ ] Get API Gateway URL:
  ```bash
  cd infrastructure
  terragrunt output api_gateway_url
  ```
- [ ] Update config file with API Gateway URL:
  - [ ] Edit `config.newaccount.yaml`
  - [ ] Update `ui.api_url` with the API Gateway URL

## Step 7: Configure Lambda Functions

- [ ] Verify Lambda environment variables are correct:
  ```bash
  aws lambda get-function-configuration --function-name eks-app-controller-discovery \
    --region <region> --query 'Environment.Variables'
  ```
- [ ] Should show:
  - `EKS_CLUSTER_NAME`: Correct cluster name
  - `CONFIG_NAME`: `config.newaccount.yaml`
  - `REGISTRY_TABLE_NAME`: DynamoDB table name

- [ ] **If Lambda packages were rebuilt**, update Lambda function code:
  ```bash
  aws lambda update-function-code --function-name eks-app-controller-discovery \
    --region <region> --zip-file fileb://build/discovery.zip
  ```
  (Repeat for all Lambda functions: discovery, controller, health-monitor, api-handler, scheduler, cost-tracker)

## Step 8: Configure EKS Cluster Access for Lambda

- [ ] Get Lambda IAM role ARN:
  ```bash
  aws iam get-role --role-name eks-app-controller-discovery-lambda-role \
    --query 'Role.Arn' --output text
  ```
- [ ] Update kubectl config:
  ```bash
  aws eks update-kubeconfig --name <cluster-name> --region <region>
  ```
- [ ] Add Lambda role to EKS aws-auth ConfigMap:
  ```bash
  DISCOVERY_ROLE_ARN=$(aws iam get-role --role-name eks-app-controller-discovery-lambda-role \
    --query 'Role.Arn' --output text)
  
  kubectl get configmap aws-auth -n kube-system -o json | \
    jq '.data.mapRoles += "\n- rolearn: '"$DISCOVERY_ROLE_ARN"'\n  username: lambda-discovery\n  groups:\n  - system:masters"' | \
    kubectl apply -f -
  ```
- [ ] Verify aws-auth ConfigMap:
  ```bash
  kubectl get configmap aws-auth -n kube-system -o json | \
    jq -r '.data.mapRoles' | grep -A 3 "lambda-discovery"
  ```

## Step 9: Test Discovery Lambda

- [ ] Manually trigger discovery Lambda:
  ```bash
  aws lambda invoke --function-name eks-app-controller-discovery \
    --region <region> --payload '{}' /tmp/discovery-test.json
  cat /tmp/discovery-test.json | jq '.'
  ```
- [ ] Check for errors:
  - [ ] Should return `statusCode: 200`
  - [ ] Should show `apps_discovered: X` (X > 0 if applications exist)
  - [ ] No "Unauthorized" errors
- [ ] Check Lambda logs:
  ```bash
  aws logs tail /aws/lambda/eks-app-controller-discovery --region <region> \
    --since 5m --format short
  ```
- [ ] Verify applications in DynamoDB:
  ```bash
  aws dynamodb scan --table-name eks-app-controller-registry \
    --region <region> --select COUNT
  ```

## Step 10: Deploy UI

- [ ] Set CONFIG_NAME environment variable:
  ```bash
  export CONFIG_NAME=config.newaccount.yaml
  ```
- [ ] Deploy UI:
  ```bash
  ./scripts/deploy-ui.sh
  ```
- [ ] Verify S3 bucket was created and UI deployed:
  ```bash
  aws s3 ls s3://eks-app-controller-ui-<account-id>/
  ```

## Step 11: Configure S3 Bucket for Public Access

- [ ] Disable Block Public Access:
  ```bash
  aws s3api put-public-access-block --bucket eks-app-controller-ui-<account-id> \
    --public-access-block-configuration \
    "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
  ```
- [ ] Set bucket policy for public read access:
  ```bash
  cat > /tmp/bucket-policy.json << EOF
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "PublicReadGetObject",
        "Effect": "Allow",
        "Principal": "*",
        "Action": "s3:GetObject",
        "Resource": "arn:aws:s3:::eks-app-controller-ui-<account-id>/*"
      }
    ]
  }
  EOF
  
  aws s3api put-bucket-policy --bucket eks-app-controller-ui-<account-id> \
    --policy file:///tmp/bucket-policy.json
  ```
- [ ] Configure S3 website hosting:
  ```bash
  aws s3 website s3://eks-app-controller-ui-<account-id> \
    --index-document index.html --error-document index.html
  ```
- [ ] Test S3 website access:
  ```bash
  curl -I http://eks-app-controller-ui-<account-id>.s3-website-<region>.amazonaws.com
  ```
  Should return `HTTP/1.1 200 OK`

## Step 12: Configure Cognito (Optional - if using authentication)

- [ ] Get Cognito details from Terragrunt outputs:
  ```bash
  cd infrastructure
  terragrunt output cognito_user_pool_id
  terragrunt output cognito_client_id
  terragrunt output cognito_domain
  ```
- [ ] Update Cognito callback URLs with S3 website URL:
  ```bash
  S3_URL="http://eks-app-controller-ui-<account-id>.s3-website-<region>.amazonaws.com"
  # Note: Cognito requires HTTPS, so S3 website won't work directly
  # You'll need CloudFront with HTTPS for Cognito to work
  ```

## Step 13: Verify Dashboard Access

- [ ] Open dashboard URL in browser:
  ```
  http://eks-app-controller-ui-<account-id>.s3-website-<region>.amazonaws.com
  ```
- [ ] Verify applications are displayed
- [ ] Test application start/stop functionality
- [ ] Verify schedule information is displayed (read-only)

## Step 14: Post-Deployment Configuration

- [ ] **Disable auto-schedule for all applications** (if needed):
  ```bash
  aws dynamodb scan --table-name eks-app-controller-registry \
    --region <region> --query 'Items[].app_name.S' --output text | \
    tr '\t' '\n' | grep -v '^$' | while read app; do
      aws dynamodb put-item --table-name eks-app-controller-app-schedules \
        --region <region> \
        --item "{\"app\":{\"S\":\"$app\"},\"enabled\":{\"BOOL\":false}}"
    done
  ```
- [ ] Verify schedule status:
  ```bash
  aws dynamodb scan --table-name eks-app-controller-app-schedules \
    --region <region> --query 'Items[].{app:app.S,enabled:enabled.BOOL}'
  ```

## Step 15: Verify Cost Configuration

- [ ] Confirm no VPC costs:
  - [ ] EKS cluster has `endpointPublicAccess: true`
  - [ ] Lambda functions have `VpcConfig: null` or empty
  - [ ] No NAT Gateway created
  - [ ] No VPC endpoints created
- [ ] Expected costs: $0 additional (matches previous deployment)

## Troubleshooting

### Issue: Discovery Lambda returns 401 Unauthorized
**Solution**: Add Lambda IAM role to EKS aws-auth ConfigMap (Step 8)

### Issue: Discovery Lambda can't find cluster
**Solution**: 
- Verify `EKS_CLUSTER_NAME` environment variable is correct
- Verify Lambda package includes `config.newaccount.yaml`
- Rebuild and update Lambda function code

### Issue: S3 bucket returns 403 Forbidden
**Solution**: 
- Disable Block Public Access (Step 11)
- Add bucket policy for public read access (Step 11)

### Issue: Dashboard shows "No applications found"
**Solution**:
- Manually trigger discovery Lambda (Step 9)
- Check Lambda logs for errors
- Verify EKS cluster has Ingress resources

### Issue: Terragrunt can't load config file
**Solution**:
- Verify `CONFIG_NAME` environment variable is set
- Verify `config.newaccount.yaml` exists in `config/` directory
- Check `scripts/load-config.py` respects `CONFIG_NAME` env var

## Deployment Summary Template

After successful deployment, document:

```
Account: <account-id>
Region: <region>
EKS Cluster: <cluster-name>
API Gateway URL: <api-gateway-url>
S3 Website URL: http://eks-app-controller-ui-<account-id>.s3-website-<region>.amazonaws.com
Cognito User Pool ID: <pool-id>
Cognito Client ID: <client-id>
Config File: config.<account>.yaml
Applications Discovered: <count>
Auto-Schedule: Disabled for all applications
Cost: $0 additional (no VPC configuration)
```

## Notes

- **VPC Configuration**: By default, deployment uses public EKS endpoint (no VPC costs). If you need VPC for security, add ~$21-32/month for NAT Gateway or VPC endpoints.
- **Config Files**: All config files are included in Lambda packages for multi-account support.
- **Lambda Updates**: After rebuilding Lambda packages, update function code for all Lambda functions.
- **EKS Access**: Lambda IAM roles must be added to EKS aws-auth ConfigMap for Kubernetes API access.

