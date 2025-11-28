# Prerequisites Checklist

Before deploying the EKS Application Start/Stop Controller, ensure you have all the following prerequisites in place.

## 1. Required Software

### AWS CLI
**Version**: 2.x recommended  
**Installation**: 
```bash
# Check if installed
aws --version

# Install if needed (macOS)
brew install awscli

# Install if needed (Linux)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

**Configuration**:
```bash
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Enter default region (e.g., us-east-1)
# Enter default output format (json)
```

**Verify**: `aws sts get-caller-identity` should return your account details

### OpenTofu
**Version**: >= 1.0  
**Installation**:
```bash
# Check if installed
tofu version

# Install if needed (macOS)
brew install opentofu/tap/opentofu

# Install if needed (Linux)
wget https://github.com/opentofu/opentofu/releases/download/v1.6.0/tofu_1.6.0_linux_amd64.zip
unzip tofu_1.6.0_linux_amd64.zip
sudo mv tofu /usr/local/bin/
```

**Verify**: `tofu version` should show >= 1.0

### Terragrunt
**Version**: >= 0.50.0  
**Installation**:
```bash
# Check if installed
terragrunt --version

# Install if needed (macOS)
brew install terragrunt

# Install if needed (Linux)
wget https://github.com/gruntwork-io/terragrunt/releases/download/v0.50.0/terragrunt_linux_amd64
chmod +x terragrunt_linux_amd64
sudo mv terragrunt_linux_amd64 /usr/local/bin/terragrunt
```

**Verify**: `terragrunt --version` should show >= 0.50.0

**Note**: Terragrunt will automatically download OpenTofu if not found, but manual installation is recommended.

### Python
**Version**: 3.11 or higher  
**Installation**:
```bash
# Check if installed
python3 --version

# Install if needed (macOS)
brew install python@3.11

# Install if needed (Linux)
sudo apt-get update
sudo apt-get install python3.11 python3-pip
```

**Verify**: `python3 --version` should show 3.11+

**Install Python dependencies**:
```bash
pip3 install -r requirements.txt
```

### Node.js and npm
**Version**: Node.js 18+ and npm 9+  
**Installation**:
```bash
# Check if installed
node --version
npm --version

# Install if needed (macOS)
brew install node

# Install if needed (Linux)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**Verify**: `node --version` should show v18+ and `npm --version` should show 9+

**Install UI dependencies**:
```bash
cd ui
npm install
cd ..
```

### kubectl
**Version**: Latest stable  
**Installation**:
```bash
# Check if installed
kubectl version --client

# Install if needed (macOS)
brew install kubectl

# Install if needed (Linux)
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

**Configure for EKS**:
```bash
# Update kubeconfig for your cluster
aws eks update-kubeconfig --name your-cluster-name --region us-east-1
```

**Verify**: `kubectl get nodes` should list your EKS nodes

## 2. AWS Account & Permissions

### AWS Account Requirements
- Active AWS account
- Appropriate AWS region selected (where your EKS cluster is located)
- Billing enabled (for resource creation)

### Required IAM Permissions

Your AWS credentials need the following permissions:

#### EKS Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "eks:DescribeCluster",
    "eks:ListClusters",
    "eks:ListNodegroups",
    "eks:DescribeNodegroup",
    "eks:UpdateNodegroupConfig",
    "eks:TagResource"
  ],
  "Resource": "*"
}
```

#### EC2 Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "ec2:DescribeInstances",
    "ec2:DescribeTags",
    "ec2:StartInstances",
    "ec2:StopInstances",
    "ec2:CreateTags"
  ],
  "Resource": "*"
}
```

#### Lambda Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "lambda:CreateFunction",
    "lambda:UpdateFunctionCode",
    "lambda:UpdateFunctionConfiguration",
    "lambda:GetFunction",
    "lambda:ListFunctions",
    "lambda:InvokeFunction",
    "lambda:AddPermission",
    "lambda:CreateAlias",
    "lambda:TagResource"
  ],
  "Resource": "*"
}
```

#### DynamoDB Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:CreateTable",
    "dynamodb:DescribeTable",
    "dynamodb:PutItem",
    "dynamodb:GetItem",
    "dynamodb:UpdateItem",
    "dynamodb:Scan",
    "dynamodb:Query",
    "dynamodb:TagResource"
  ],
  "Resource": "*"
}
```

#### API Gateway Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "apigateway:*",
    "apigatewayv2:*"
  ],
  "Resource": "*"
}
```

#### IAM Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "iam:CreateRole",
    "iam:AttachRolePolicy",
    "iam:PutRolePolicy",
    "iam:GetRole",
    "iam:PassRole",
    "iam:TagRole"
  ],
  "Resource": "*"
}
```

#### EventBridge Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "events:PutRule",
    "events:PutTargets",
    "events:DescribeRule",
    "events:EnableRule",
    "events:DisableRule"
  ],
  "Resource": "*"
}
```

#### CloudWatch Logs Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "logs:CreateLogGroup",
    "logs:CreateLogStream",
    "logs:PutLogEvents"
  ],
  "Resource": "*"
}
```

#### S3 Permissions (for UI deployment)
```json
{
  "Effect": "Allow",
  "Action": [
    "s3:CreateBucket",
    "s3:PutObject",
    "s3:GetObject",
    "s3:ListBucket",
    "s3:PutBucketWebsite"
  ],
  "Resource": "*"
}
```

**Note**: For production, use least-privilege IAM policies. The above is a comprehensive list for deployment.

### Verify AWS Access
```bash
# Test AWS credentials
aws sts get-caller-identity

# Test EKS access
aws eks list-clusters

# Test EC2 access
aws ec2 describe-instances --max-items 1

# Test Lambda access
aws lambda list-functions --max-items 1
```

## 3. EKS Cluster Requirements

### Cluster Must Exist
- EKS cluster already created and running
- Cluster name known (for Terraform configuration)
- Cluster accessible via kubectl

### Kubernetes Access
- kubectl configured to access the cluster
- RBAC permissions to read Ingress resources
- Service account with appropriate permissions (if Lambda runs in cluster)

**Verify**:
```bash
# Should list nodes
kubectl get nodes

# Should list namespaces
kubectl get namespaces

# Should be able to read Ingress (may be empty)
kubectl get ingress -A
```

### Ingress Resources
- At least one Ingress resource exists (or will be created)
- Ingress resources have hostname rules defined

**Check**:
```bash
kubectl get ingress -A -o wide
```

## 4. Resource Tagging Requirements

### EC2 Instances Must Be Tagged
Before discovery can work, EC2 database instances must be tagged:

**PostgreSQL instances**:
- `AppName`: Application identifier (e.g., `mi.dev.mareana.com`)
- `Component`: `postgres`
- `Shared`: `true` or `false`

**Neo4j instances**:
- `AppName`: Application identifier
- `Component`: `neo4j`
- `Shared`: `true` or `false`

**Example**:
```bash
aws ec2 create-tags \
  --resources i-1234567890abcdef0 \
  --tags \
    Key=AppName,Value=mi.dev.mareana.com \
    Key=Component,Value=postgres \
    Key=Shared,Value=false
```

### NodeGroups Must Be Tagged
EKS NodeGroups must be tagged:

- `AppName`: Application identifier
- `Component`: `nodegroup`

**Example**:
```bash
aws eks tag-resource \
  --resource-arn arn:aws:eks:region:account:nodegroup/cluster/nodegroup-name/... \
  --tags AppName=mi.dev.mareana.com,Component=nodegroup
```

**See**: `docs/TAGGING.md` for detailed tagging guide

## 5. Network & VPC Requirements

### Lambda VPC Configuration (Optional)
If your EKS cluster is in a private VPC:
- Lambda functions may need VPC configuration
- Security groups must allow Lambda → EKS communication
- NAT Gateway or VPC endpoints for internet access

### API Gateway
- No special network requirements
- Public endpoint (can be restricted with API keys/auth)

## 6. Optional Prerequisites

### CloudFront (for UI)
- CloudFront distribution (optional, for production)
- SSL certificate (optional, for custom domain)

### S3 Bucket (for UI)
- S3 bucket for hosting UI (can be created during deployment)
- Bucket policy for public read access (or CloudFront OAI)

### Domain Name (Optional)
- Custom domain for UI
- Custom domain for API Gateway
- SSL certificate in ACM

## 7. Pre-Deployment Verification

Run this checklist before starting deployment:

```bash
# 1. Software versions
echo "=== Software Versions ==="
aws --version
terraform version
python3 --version
node --version
npm --version
kubectl version --client

# 2. AWS access
echo -e "\n=== AWS Access ==="
aws sts get-caller-identity
aws eks list-clusters

# 3. Kubernetes access
echo -e "\n=== Kubernetes Access ==="
kubectl get nodes
kubectl get namespaces

# 4. Python dependencies
echo -e "\n=== Python Dependencies ==="
pip3 list | grep -E "boto3|kubernetes|requests"

# 5. Node dependencies (if UI will be built)
echo -e "\n=== Node Dependencies ==="
cd ui && npm list --depth=0 && cd ..

# 6. Resource tagging (sample check)
echo -e "\n=== Sample EC2 Tags ==="
aws ec2 describe-instances \
  --filters "Name=tag:Component,Values=postgres" \
  --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`AppName`].Value|[0]]' \
  --output table
```

## 8. Common Issues & Solutions

### Issue: AWS CLI not configured
**Solution**: Run `aws configure` with your credentials

### Issue: kubectl can't access cluster
**Solution**: Run `aws eks update-kubeconfig --name cluster-name --region region`

### Issue: Terraform version too old
**Solution**: Update Terraform to >= 1.0

### Issue: Python version < 3.11
**Solution**: Install Python 3.11+ and use `python3.11` explicitly

### Issue: Insufficient IAM permissions
**Solution**: Contact AWS administrator to grant required permissions

### Issue: No Ingress resources found
**Solution**: This is OK - discovery will run but find no apps until Ingress resources exist

## 9. Next Steps

Once all prerequisites are met:

1. ✅ Review this checklist
2. ✅ Run verification commands
3. ✅ Tag your resources (see `docs/TAGGING.md`)
4. ✅ Proceed to `QUICKSTART.md` or `docs/DEPLOYMENT.md`

## Quick Prerequisites Test Script

Save this as `scripts/check-prerequisites.sh`:

```bash
#!/bin/bash
set -e

echo "Checking prerequisites..."

# Software
command -v aws >/dev/null 2>&1 || { echo "❌ AWS CLI not found"; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo "❌ Terraform not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python3 not found"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Node.js not found"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }

# Versions
terraform version | grep -q "Terraform v1\." || { echo "❌ Terraform < 1.0"; exit 1; }
python3 --version | grep -q "Python 3\.1[1-9]" || { echo "❌ Python < 3.11"; exit 1; }

# AWS access
aws sts get-caller-identity >/dev/null 2>&1 || { echo "❌ AWS credentials not configured"; exit 1; }

# Kubernetes access
kubectl get nodes >/dev/null 2>&1 || { echo "❌ Cannot access Kubernetes cluster"; exit 1; }

echo "✅ All prerequisites met!"
```

Run: `chmod +x scripts/check-prerequisites.sh && ./scripts/check-prerequisites.sh`

