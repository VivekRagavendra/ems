# Deployment Locations - Where Everything Runs

## 🌍 Overview

This system deploys **entirely in your AWS account** using serverless services. Nothing runs on your local machine in production.

## 📍 Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   YOUR AWS ACCOUNT                      │
│                  (Your Chosen Region)                   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │           AWS Lambda Service                   │   │
│  │  - Discovery Lambda                            │   │
│  │  - Controller Lambda                           │   │
│  │  - Health Monitor Lambda                       │   │
│  │  - API Handler Lambda                          │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │         AWS DynamoDB Service                   │   │
│  │  - Application Registry Table                  │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │       AWS API Gateway Service                  │   │
│  │  - HTTP API Endpoint                           │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │       AWS EventBridge Service                  │   │
│  │  - Scheduled Rules (Discovery, Health)         │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │            AWS S3 Service                      │   │
│  │  - UI Static Files (React Dashboard)           │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │   YOUR EXISTING EKS CLUSTER (Not Created)     │   │
│  │  - Applications                                │   │
│  │  - NodeGroups                                  │   │
│  │  - Ingress Resources                           │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │   YOUR EXISTING EC2 (Not Created)             │   │
│  │  - PostgreSQL Instances                        │   │
│  │  - Neo4j Instances                             │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 🎯 Deployment Details

### 1. Lambda Functions → **AWS Lambda Service**

**Where**: AWS Lambda (managed service in your chosen region)
**What**: 4 serverless functions
**Created by**: Terragrunt/OpenTofu
**Runs on**: AWS-managed compute (no servers to manage)

```
Functions deployed:
  - eks-app-controller-discovery
  - eks-app-controller-controller
  - eks-app-controller-health-monitor
  - eks-app-controller-api-handler

Location: AWS Lambda service in us-east-1 (or your region)
```

**You don't manage any servers!** AWS runs the code automatically when triggered.

### 2. DynamoDB Table → **AWS DynamoDB Service**

**Where**: AWS DynamoDB (managed service in your chosen region)
**What**: Application registry database
**Created by**: Terragrunt/OpenTofu
**Runs on**: AWS-managed database

```
Table name: eks-app-controller-registry
Location: AWS DynamoDB in us-east-1 (or your region)
```

**Fully managed** - no database servers to maintain.

### 3. API Gateway → **AWS API Gateway Service**

**Where**: AWS API Gateway (managed service in your chosen region)
**What**: HTTP API for dashboard and automation
**Created by**: Terragrunt/OpenTofu
**Endpoint**: `https://<api-id>.execute-api.<region>.amazonaws.com`

```
API endpoints:
  - GET  /apps   → List applications
  - POST /start  → Start application
  - POST /stop   → Stop application

Location: AWS API Gateway in us-east-1 (or your region)
```

**Public endpoint** - accessible from anywhere (add authentication for production).

### 4. EventBridge Rules → **AWS EventBridge Service**

**Where**: AWS EventBridge (managed service in your chosen region)
**What**: Scheduled triggers for Lambda functions
**Created by**: Terragrunt/OpenTofu

```
Schedules:
  - Discovery: Every 2 hours
  - Health Check: Every 15 minutes

Location: AWS EventBridge in us-east-1 (or your region)
```

### 5. React Dashboard → **AWS S3 Service**

**Where**: AWS S3 bucket (in your chosen region)
**What**: Static website hosting for React UI
**Created by**: Manual deployment (`./scripts/deploy-ui.sh`)
**Access**: `http://<bucket-name>.s3-website-<region>.amazonaws.com`

```
Content:
  - index.html
  - JavaScript bundles
  - CSS files

Location: S3 bucket in us-east-1 (or your region)
```

**Optional**: Add CloudFront for HTTPS and global distribution.

### 6. IAM Roles → **AWS IAM Service**

**Where**: AWS IAM (global service)
**What**: Permissions for Lambda functions
**Created by**: Terragrunt/OpenTofu

```
Roles created:
  - eks-app-controller-discovery-lambda-role
  - eks-app-controller-controller-lambda-role
  - eks-app-controller-health-monitor-lambda-role
  - eks-app-controller-api-handler-lambda-role
```

### 7. CloudWatch Logs → **AWS CloudWatch Service**

**Where**: AWS CloudWatch (in your chosen region)
**What**: Lambda function logs
**Created**: Automatically by Lambda
**Access**: AWS Console → CloudWatch → Log Groups

```
Log groups:
  /aws/lambda/eks-app-controller-discovery
  /aws/lambda/eks-app-controller-controller
  /aws/lambda/eks-app-controller-health-monitor
  /aws/lambda/eks-app-controller-api-handler
```

## 📦 What Runs Where

| Component | Where It Runs | Who Manages It |
|-----------|---------------|----------------|
| Lambda Functions | AWS Lambda Service | AWS (serverless) |
| DynamoDB | AWS DynamoDB Service | AWS (managed) |
| API Gateway | AWS API Gateway Service | AWS (managed) |
| EventBridge | AWS EventBridge Service | AWS (managed) |
| React UI | AWS S3 / CloudFront | AWS (managed) |
| IAM Roles | AWS IAM Service | AWS (global) |
| CloudWatch Logs | AWS CloudWatch Service | AWS (managed) |
| **Your EKS Cluster** | **Your AWS Account** | **You** (not created) |
| **Your EC2 Databases** | **Your AWS Account** | **You** (not created) |

## 🌐 Geographic Location

All resources are deployed in **your chosen AWS region** (default: `us-east-1`).

**Configured in**: `infrastructure/terragrunt.hcl`

```hcl
inputs = {
  aws_region = "us-east-1"  # Change this to your region
  # ...
}
```

**Supported regions**: Any AWS region that supports:
- Lambda
- DynamoDB
- API Gateway
- EventBridge
- S3

(Basically all major AWS regions)

## 🚀 Deployment Process

### Step 1: Deploy Infrastructure (from your machine)

```bash
cd infrastructure
terragrunt apply
```

**What happens:**
- Terragrunt/OpenTofu connects to AWS API
- Creates resources in your AWS account
- Resources run in AWS (not on your machine)

**Your machine**: Only used for running Terragrunt commands
**AWS**: Everything actually runs here

### Step 2: Deploy UI (from your machine)

```bash
./scripts/deploy-ui.sh
```

**What happens:**
- Builds React app on your machine
- Uploads to S3 bucket
- Files served from S3 (not your machine)

**Your machine**: Only used for building and uploading
**AWS S3**: Hosts and serves the UI

### Step 3: Access Dashboard (from anywhere)

```
Users access:
  Browser → S3/CloudFront URL → UI loads
  UI → API Gateway → Lambda functions
```

**Users access from**: Anywhere with internet
**System runs in**: Your AWS account (serverless)

## 💻 Local vs Cloud

### What Runs Locally (Your Computer)

**During deployment only:**
- ✅ Terragrunt/OpenTofu commands
- ✅ npm build commands
- ✅ AWS CLI commands

**During operation:**
- ❌ Nothing runs locally!
- ❌ No local servers needed
- ❌ Can turn off your computer

### What Runs in AWS (Production)

**Always running (serverless):**
- ✅ Lambda functions (on-demand)
- ✅ DynamoDB table
- ✅ API Gateway endpoint
- ✅ EventBridge schedules
- ✅ S3 static website

## 🔒 Network Access

### Lambda → EKS Cluster

**How Lambda accesses Kubernetes:**

**Option 1: VPC Configuration** (recommended)
```
Lambda in VPC → Same VPC as EKS → Access via private networking
```

**Option 2: Public EKS API**
```
Lambda (with IAM) → EKS public endpoint → Kubernetes API
```

**Option 3: Run in EKS**
```
Lambda deployed as Kubernetes Job → Direct cluster access
```

See `docs/DEPLOYMENT.md` for Kubernetes access setup.

### Users → Dashboard

```
User Browser → Internet → S3 URL or CloudFront → React UI
UI → Internet → API Gateway → Lambda functions
```

**Access**: Public internet (add authentication for production)

## 🎯 Region Selection Guide

### Choose Your Region Based On:

1. **EKS Cluster Location**: Deploy in same region as your EKS cluster
   - Lower latency
   - No cross-region data transfer costs

2. **User Location**: Deploy close to users
   - Faster dashboard loading
   - Better user experience

3. **Cost**: Some regions are cheaper
   - `us-east-1` (N. Virginia): Usually cheapest
   - `us-west-2` (Oregon): Also cost-effective

**Recommendation**: Deploy in **same region as your EKS cluster**

## 📍 Multi-Region Deployment (Optional)

To deploy in multiple regions:

1. Create separate directories for each region:
```
infrastructure/
  us-east-1/
    terragrunt.hcl
  eu-west-1/
    terragrunt.hcl
```

2. Configure each with different region:
```hcl
aws_region = "us-east-1"  # or "eu-west-1"
```

3. Deploy separately:
```bash
cd infrastructure/us-east-1 && terragrunt apply
cd infrastructure/eu-west-1 && terragrunt apply
```

## 🏗️ Deployment Environments

### Development
```
Location: Dev AWS account or separate region
Purpose: Testing and development
Cost: Minimal (use cost-optimized settings)
```

### Staging
```
Location: Same region as production
Purpose: Pre-production testing
Cost: Same as production
```

### Production
```
Location: Same region as EKS cluster
Purpose: Live system
Cost: $0-6/month (with optimizations)
```

## ✅ Summary

**Where does it deploy?**
- ✅ **AWS Lambda** - Lambda functions run here
- ✅ **AWS DynamoDB** - Database runs here
- ✅ **AWS API Gateway** - API endpoint runs here
- ✅ **AWS S3** - Dashboard UI runs here
- ✅ **AWS EventBridge** - Schedulers run here

**What doesn't it deploy?**
- ❌ Your EKS cluster (must already exist)
- ❌ Your EC2 databases (must already exist)
- ❌ Your applications (must already exist)

**Where do YOU run commands?**
- 🖥️ Your local machine (for deployment only)
- 🌐 AWS account (where everything runs)
- 🌍 Users access from anywhere

**Key Point**: This is a **100% serverless solution**. Everything runs in AWS managed services. You don't manage any servers!


