# What This Codebase Creates & Where It Runs

This document explains exactly what AWS resources are created and where each component executes.

## 🏗️ AWS Resources Created

When you run `terragrunt apply`, this codebase creates the following AWS resources:

### 1. **DynamoDB Table**
- **Resource**: `aws_dynamodb_table.app_registry`
- **Name**: `eks-app-controller-registry` (or your `project_name`-registry)
- **Purpose**: Central registry storing application metadata
- **Schema**:
  - Partition Key: `app_name` (String)
  - Stores: hostnames, nodegroups, database instances, status, shared resources
- **Billing**: Pay-per-request (auto-scaling)
- **Location**: Runs in your specified AWS region (e.g., us-east-1)

### 2. **Lambda Functions** (4 functions)

All Lambda functions run in **AWS Lambda service** (serverless, managed by AWS):

#### a. Discovery Lambda
- **Name**: `eks-app-controller-discovery`
- **Runtime**: Python 3.11
- **Memory**: 512 MB
- **Timeout**: 300 seconds (5 minutes)
- **Purpose**: Scans Kubernetes Ingress, discovers applications
- **Runs**: 
  - Automatically every hour (via EventBridge)
  - Manually via AWS CLI or API
- **Location**: AWS Lambda service in your region

#### b. Controller Lambda
- **Name**: `eks-app-controller-controller`
- **Runtime**: Python 3.11
- **Memory**: 512 MB
- **Timeout**: 300 seconds
- **Purpose**: Starts/stops applications (NodeGroups, EC2 databases)
- **Runs**: 
  - Triggered by API Gateway when user clicks Start/Stop
  - Can be invoked manually
- **Location**: AWS Lambda service in your region

#### c. Health Monitor Lambda
- **Name**: `eks-app-controller-health-monitor`
- **Runtime**: Python 3.11
- **Memory**: 512 MB
- **Timeout**: 300 seconds
- **Purpose**: Checks application health status
- **Runs**: 
  - Automatically every 5 minutes (via EventBridge)
  - Manually via AWS CLI
- **Location**: AWS Lambda service in your region

#### d. API Handler Lambda
- **Name**: `eks-app-controller-api-handler`
- **Runtime**: Python 3.11
- **Memory**: 256 MB
- **Timeout**: 60 seconds
- **Purpose**: Serves application list API
- **Runs**: 
  - Triggered by API Gateway when UI loads or refreshes
- **Location**: AWS Lambda service in your region

### 3. **IAM Roles & Policies** (4 roles)

All IAM roles are created in **AWS IAM service**:

- `eks-app-controller-discovery-lambda-role`
- `eks-app-controller-controller-lambda-role`
- `eks-app-controller-health-monitor-lambda-role`
- `eks-app-controller-api-handler-lambda-role`

Each role has specific permissions:
- CloudWatch Logs (for logging)
- DynamoDB (read/write to registry)
- EKS (list/describe/update nodegroups)
- EC2 (describe/start/stop instances)

**Location**: AWS IAM (global service, but resources are region-specific)

### 4. **API Gateway** (HTTP API)

- **Resource**: `aws_apigatewayv2_api.main`
- **Name**: `eks-app-controller-api`
- **Type**: HTTP API (not REST API)
- **Endpoints**:
  - `GET /apps` → API Handler Lambda
  - `POST /start` → Controller Lambda
  - `POST /stop` → Controller Lambda
- **CORS**: Enabled for all origins
- **Location**: AWS API Gateway service in your region
- **URL Format**: `https://{api-id}.execute-api.{region}.amazonaws.com`

### 5. **EventBridge Rules** (2 rules)

- **Resource**: `aws_cloudwatch_event_rule.discovery_schedule`
  - **Name**: `eks-app-controller-discovery-schedule`
  - **Schedule**: Every 1 hour
  - **Target**: Discovery Lambda

- **Resource**: `aws_cloudwatch_event_rule.health_check_schedule`
  - **Name**: `eks-app-controller-health-check-schedule`
  - **Schedule**: Every 5 minutes
  - **Target**: Health Monitor Lambda

**Location**: AWS EventBridge service (global, but rules are region-specific)

### 6. **Lambda Permissions** (for API Gateway & EventBridge)

- Permissions allowing API Gateway to invoke Lambda functions
- Permissions allowing EventBridge to invoke scheduled Lambdas

**Location**: AWS Lambda service (attached to functions)

## 📍 Where Components Run

### **AWS-Managed Services** (Serverless)

All these run in **AWS's managed infrastructure** - you don't manage servers:

1. **Lambda Functions** → AWS Lambda service
   - Runs in AWS-managed containers
   - Auto-scales based on invocations
   - No servers to manage

2. **DynamoDB** → AWS DynamoDB service
   - Fully managed NoSQL database
   - Runs in AWS data centers
   - Auto-scales storage and throughput

3. **API Gateway** → AWS API Gateway service
   - Managed HTTP API endpoint
   - Handles routing, CORS, authentication
   - Auto-scales with traffic

4. **EventBridge** → AWS EventBridge service
   - Managed event scheduling
   - Triggers Lambda functions on schedule

### **Your Existing Infrastructure** (Not Created by This Code)

This codebase **does NOT create** these, but **manages** them:

1. **EKS Cluster** → Your existing EKS cluster
   - Must already exist
   - Code reads Ingress resources from it
   - Code scales NodeGroups in it

2. **EC2 Instances** → Your existing PostgreSQL/Neo4j instances
   - Must already exist and be tagged
   - Code starts/stops them
   - Code reads their tags

3. **EKS NodeGroups** → Your existing NodeGroups
   - Must already exist and be tagged
   - Code scales them up/down

### **UI Deployment** (Optional, Manual)

The React UI is **not automatically deployed** by Terragrunt. You deploy it separately:

- **Option 1**: S3 + CloudFront
  - S3 bucket: Stores static files (HTML, CSS, JS)
  - CloudFront: CDN for global distribution
  - **Location**: S3 in your region, CloudFront globally

- **Option 2**: S3 Website
  - S3 bucket with website hosting enabled
  - **Location**: S3 in your region

## 🔄 Execution Flow

### When User Opens UI:

```
User Browser
    ↓ (HTTPS)
S3/CloudFront (UI files)
    ↓ (API call)
API Gateway (HTTP API)
    ↓ (invokes)
API Handler Lambda
    ↓ (reads)
DynamoDB Registry
    ↓ (returns)
API Gateway → UI (displays apps)
```

### When User Clicks "Start Application":

```
User Browser
    ↓ (POST /start)
API Gateway
    ↓ (invokes)
Controller Lambda
    ↓ (reads)
DynamoDB Registry
    ↓ (executes)
EKS API → Scale NodeGroups
EC2 API → Start PostgreSQL/Neo4j instances
    ↓ (updates)
DynamoDB Registry (status = UP)
    ↓ (returns)
API Gateway → UI (shows success)
```

### Automatic Discovery (Every Hour):

```
EventBridge (scheduled)
    ↓ (triggers)
Discovery Lambda
    ↓ (scans)
Kubernetes API → Get all Ingress resources
EKS API → Get NodeGroups (by tags)
EC2 API → Get database instances (by tags)
    ↓ (processes)
Detects shared resources
    ↓ (writes)
DynamoDB Registry (updates app metadata)
```

### Automatic Health Check (Every 5 Minutes):

```
EventBridge (scheduled)
    ↓ (triggers)
Health Monitor Lambda
    ↓ (checks)
EKS API → NodeGroup status
EC2 API → Instance state
HTTP → Ingress endpoint health
    ↓ (updates)
DynamoDB Registry (status = UP/DOWN/DEGRADED)
```

## 🌍 Geographic Location

All resources are created in **your specified AWS region**:

- Default: `us-east-1` (configurable in `terragrunt.hcl`)
- All resources in the same region for:
  - Lower latency
  - Lower data transfer costs
  - Simpler networking

**Exception**: 
- CloudFront (if used for UI) is global
- IAM roles are global (but attached to region-specific resources)

## 💰 Cost Implications

### What You Pay For:

1. **Lambda**: Pay per invocation + execution time
   - Discovery: ~$0.20/month (runs hourly)
   - Controller: Pay per use (user actions)
   - Health Monitor: ~$0.50/month (runs every 5 min)
   - API Handler: Pay per API call

2. **DynamoDB**: Pay-per-request
   - ~$0.25 per million reads
   - ~$1.25 per million writes
   - Very low cost for typical usage

3. **API Gateway**: Pay per API call
   - $1.00 per million requests
   - First million free (if using HTTP API)

4. **EventBridge**: Free tier includes 1M custom events/month

5. **Data Transfer**: Minimal (all in same region)

**Estimated Monthly Cost**: $5-20 for typical usage (excluding your EKS/EC2 costs)

## 🔐 Security & Access

### Lambda Functions Access:

- **EKS Cluster**: Via AWS SDK (requires IAM permissions)
- **EC2 Instances**: Via AWS SDK (requires IAM permissions)
- **DynamoDB**: Via AWS SDK (requires IAM permissions)
- **Kubernetes API**: 
  - Option 1: Via kubectl (if Lambda has kubeconfig)
  - Option 2: Via EKS API (limited - can't read Ingress easily)
  - Option 3: Run Lambda in EKS cluster (best option)

### API Gateway Access:

- **Public**: Currently open (CORS allows all origins)
- **Recommendation**: Add authentication (API Keys, Cognito, etc.)

### UI Access:

- **Public**: If deployed to S3/CloudFront
- **Recommendation**: Add CloudFront signed URLs or authentication

## 📊 Summary Table

| Component | What It Is | Where It Runs | Created By Code? |
|-----------|------------|---------------|------------------|
| DynamoDB Table | Database | AWS DynamoDB | ✅ Yes |
| Lambda Functions (4) | Serverless functions | AWS Lambda | ✅ Yes |
| IAM Roles (4) | Permissions | AWS IAM | ✅ Yes |
| API Gateway | HTTP API | AWS API Gateway | ✅ Yes |
| EventBridge Rules (2) | Schedulers | AWS EventBridge | ✅ Yes |
| EKS Cluster | Kubernetes cluster | Your AWS account | ❌ No (must exist) |
| EC2 Instances | Databases | Your AWS account | ❌ No (must exist) |
| NodeGroups | EKS node groups | Your AWS account | ❌ No (must exist) |
| React UI | Web dashboard | S3/CloudFront | ❌ No (manual deploy) |

## 🎯 Key Takeaways

1. **This codebase creates a CONTROL SYSTEM** - it doesn't create your applications
2. **Everything runs serverless** - no servers to manage
3. **All in one AWS region** - for simplicity and cost efficiency
4. **Manages existing resources** - your EKS cluster, EC2 instances, NodeGroups
5. **UI is separate** - deploy manually to S3/CloudFront
6. **Low cost** - mostly pay-per-use, very affordable

The system acts as an **orchestration layer** that discovers, monitors, and controls your existing EKS applications and their dependencies.


