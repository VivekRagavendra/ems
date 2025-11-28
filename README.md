# EKS Application Start/Stop Controller

An intelligent, self-service system for managing application lifecycle in AWS EKS clusters. Enhances your existing Lambda + Jenkins automation with a web dashboard, auto-discovery, and real-time monitoring. Provides one-click shutdown and startup of applications and their dependent infrastructure components (NodeGroups, PostgreSQL, Neo4j databases).

## 🎯 Overview

**If you already have Lambda functions and Jenkins for start/stop operations:** This system enhances your setup by adding a self-service web dashboard, automatic application discovery, shared resource protection, and real-time health monitoring. You can reuse your existing Lambdas and run both systems in parallel.

**If starting fresh:** This system automatically discovers applications in your EKS cluster and provides a simple web interface to start or stop entire applications with a single click. It intelligently handles shared resources, validates dependencies, and monitors application health in real-time.

**Implementation Time:** 2.5 days (full-time DevOps) - System live by Wednesday if you start Monday!

## ✨ Key Features

- ✅ **One-Click Operations**: Start/stop entire applications (NodeGroups + databases) with a single click
- ✅ **Self-Service Web Dashboard**: Modern React UI with real-time status updates and component-level indicators
- ✅ **Auto-Discovery**: Automatically detects applications by scanning Kubernetes Ingress resources
- ✅ **ConfigMap-Based Database Discovery**: Reads database connection details from Kubernetes ConfigMaps (`common-config`)
- ✅ **Smart Start Workflow**: 
  - **STEP 1**: Check Postgres & Neo4j EC2 states (live)
  - **STEP 2**: Start DB EC2 instances if stopped (wait until running)
  - **STEP 3**: Scale NodeGroup(s) UP to default values (from hard-coded mapping)
  - **STEP 4**: Wait for NodeGroup to be ACTIVE
  - **STEP 5**: Scale Deployments & StatefulSets UP (max(1, current_replicas))
  - Uses NodeGroup defaults mapping (no user input needed)
  - Asynchronous execution (returns 202 Accepted immediately)
- ✅ **Component-Level Status Indicators**: 
  - 🟢 **Postgres Status**: Shows database state (running/stopped) - based on EC2 instance state
  - 🟢 **Neo4j Status**: Shows database state (running/stopped) - based on EC2 instance state
  - 🟢 **NodeGroup Status**: Shows node scaling state (ready/stopped/scaling) - based on EKS NodeGroup status
  - Indicators appear for all applications with component data
  - Application status determined by HTTP check (200 = UP, else = DOWN)
- ✅ **Pod Status Display**: 
  - Live pod counts from Kubernetes API (running, pending, crashloop, total)
  - Expandable dropdowns showing detailed pod information (name, reason, owner, restart count)
  - Requires Kubernetes RBAC configuration (see [docs/POD_RBAC_SETUP.md](docs/POD_RBAC_SETUP.md))
  - Gracefully handles missing RBAC permissions (shows 0 pods with helpful message)
- ✅ **Database Health Checking**: 
  - **EC2 instance state is ONLY source of truth** (running/stopped)
    - If EC2 instance is "running" → Database state = "running" ✅
    - If EC2 instance is "stopped" → Database state = "stopped" ❌
  - **NO port checks** - EC2 state determines DB state
  - **NO TCP tests** - Only EC2 DescribeInstances API call
  - **Live checks** - Every API request performs fresh EC2 API call
  - Supports shared database instances across namespaces
  - **Status reflects actual server state immediately**
- ✅ **Shared Resource Detection & Protection**: 
  - Automatically detects when databases or NodeGroups are shared across multiple applications
  - Shows "🔗 Shared Resource" badge with list of sharing applications
  - **Distributed Lock Mechanism**: Prevents race conditions when stopping shared databases
  - **Intelligent Stop Logic**: Databases only stopped when ALL dependent applications are DOWN
  - **Live Status Checks**: Uses quick-status endpoint to verify sharing apps are actually DOWN
  - **Fail-Safe Design**: UNKNOWN status treated as UP (prevents accidental DB stops)
  - Visual warnings in dashboard for shared resources
- ✅ **Real-Time Live Status Monitoring**: 
  - **NO CACHING** - All status checks are performed live on every API request
  - **Parallel Execution** - Database, NodeGroup, Pod, and HTTP checks run simultaneously for speed
  - Tests actual HTTP endpoints (like `curl`) to verify accessibility
  - Live status updates (🟢 UP, 🔴 DOWN, 🟡 WAITING)
  - **Strict HTTP Rule**: Only HTTP 200 = UP, everything else = DOWN
  - Connection timeout/refused = DOWN
  - Health Monitor runs every 1 minute for background recording
  - API Handler performs fresh checks on every request (no stale data)
- ✅ **Auto-Refresh Dashboard**: Automatically refreshes every 5 seconds for immediate status updates
- ✅ **Live Component Status**: 
  - Database state from live EC2 instance checks
  - NodeGroup state from live EKS API calls
  - Pod counts from live Kubernetes API calls
  - HTTP status from live HTTP HEAD requests
- ✅ **Zero Maintenance**: Automatically adapts when new applications are added
- ✅ **Hard-Coded Application Mappings**: 
  - Namespace mappings: Authoritative source for application → namespace (overrides auto-discovery)
  - NodeGroup mappings: Authoritative source for application → NodeGroup with default scaling values
  - Supports 16 applications with correct namespace and NodeGroup assignments
- ✅ **Lightweight Dashboard**: Optimized React UI (~100KB gzipped)
- ✅ **Serverless Architecture**: Fully managed AWS services, no servers to maintain
- ✅ **Fast Implementation**: 2.5 days to deploy, works with your existing Lambda functions
- ✅ **Comprehensive Testing**: Individual application testing with 9 checks per app
- ✅ **Minimum IAM Permissions**: Controller Lambda uses only essential EC2 permissions (Start/Stop/Describe)

## 🏗️ Architecture

```
┌─────────────────┐
│  React UI       │  ← Web Dashboard (S3/CloudFront)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  API Gateway    │  ← REST API (/apps, /start, /stop)
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────┐
│ API    │ │Controller│  ← Lambda Functions
│Handler │ │ Lambda   │
└───┬────┘ └────┬──────┘
    │          │
    └────┬─────┘
         ▼
┌─────────────────┐
│  DynamoDB       │  ← Application Registry
│  Registry       │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────┐
│Discovery│ │  Health  │  ← Scheduled Lambdas
│ Lambda  │ │ Monitor  │
└────┬────┘ └────┬──────┘
     │          │
     └────┬─────┘
          ▼
    ┌──────────┐
    │   EKS    │  ← Your Existing Cluster
    │  Cluster │
    └──────────┘
```

**Components:**
- **4 Lambda Functions**: Discovery, Controller, Health Monitor, API Handler
- **DynamoDB Table**: Central registry for application metadata + distributed locks (TTL-enabled)
- **API Gateway**: HTTP API for dashboard and automation (includes quick-status endpoint)
- **EventBridge**: Scheduled triggers for discovery and health checks
- **React Dashboard**: Lightweight web UI with real-time live status updates

**Data Flow:**
- **Discovery Lambda**: Scans EKS, updates DynamoDB with metadata (runs every 2 hours)
- **Health Monitor Lambda**: Performs HTTP checks, updates DynamoDB (runs every 1 minute)
- **API Handler Lambda**: Performs LIVE checks on every request (NO caching)
  - EC2 API calls for database state
  - EKS API calls for NodeGroup state
  - Kubernetes API calls for pod counts
  - HTTP HEAD requests for application status
  - Quick-status endpoint (`/status/quick`) for Controller Lambda shared-app checks
- **Controller Lambda**: Start/stop operations with distributed locking
  - Acquires DynamoDB locks before database stop operations
  - Checks sharing app status via quick-status endpoint
  - Prevents race conditions in concurrent stop scenarios
- **Dashboard**: Auto-refreshes every 5 seconds, fetches fresh data from API Handler

## 🚀 Quick Start

**Implementation Time:** 2.5 days (full-time) = 19 hours
- Day 1: Setup & tagging (8 hours)
- Day 2: Deploy infrastructure & dashboard (8 hours)
- Day 3: Training & go-live (3 hours)
- **Result:** System operational by Wednesday noon if you start Monday!

### Prerequisites

- AWS CLI configured with appropriate permissions
- OpenTofu >= 1.0 (or Terraform >= 1.0)
- Terragrunt >= 0.50.0
- Python 3.11+
- Node.js 18+
- kubectl configured for your EKS cluster
- Existing EKS cluster with applications

**Quick Check:**
```bash
./scripts/check-prerequisites.sh
```

See [docs/PREREQUISITES.md](docs/PREREQUISITES.md) for detailed setup instructions.

### Installation

1. **Configure Terragrunt:**
   ```bash
   cd infrastructure
   cp terragrunt.hcl.example terragrunt.hcl
   # Edit terragrunt.hcl with your EKS cluster name and region
   ```

2. **Tag Your Resources:**
   - Tag EC2 database instances: `AppName`, `Component` (postgres/neo4j), `Shared`
   - Tag EKS NodeGroups: `AppName`, `Component` (nodegroup)
   
   See [docs/TAGGING.md](docs/TAGGING.md) for detailed tagging guide.

3. **Deploy Infrastructure:**
   ```bash
   cd infrastructure
   terragrunt init
   terragrunt plan
   terragrunt apply
   ```

4. **Run Initial Discovery:**
   ```bash
   aws lambda invoke \
     --function-name eks-app-controller-discovery \
     --payload '{}' \
     response.json
   ```

5. **Trigger Health Check:**
   ```bash
   # Health monitor tests actual HTTP endpoints
   aws lambda invoke \
     --function-name eks-app-controller-health-monitor \
     --region us-east-1 \
     /tmp/health.json
   ```

6. **Test Applications:**
   ```bash
   # Test one application (9 comprehensive checks)
   ./scripts/test-each-application.sh mi.dev.mareana.com
   
   # Test all applications
   ./scripts/test-all-apps-batch.sh
   ```

7. **Deploy Dashboard:**
   ```bash
   API_URL=$(terragrunt output -raw api_gateway_url)
   S3_BUCKET=eks-app-controller-ui-420464349284 API_URL=$API_URL ../scripts/deploy-ui.sh
   ```
   
   **Dashboard URL**: http://eks-app-controller-ui-420464349284.s3-website-us-east-1.amazonaws.com/
   **API Gateway URL**: https://6rgavd4jt7.execute-api.us-east-1.amazonaws.com

**Full Guide:** See [QUICKSTART.md](QUICKSTART.md) for step-by-step instructions.

## 📁 Project Structure

```
EMS/
├── lambdas/              # Lambda function code
│   ├── discovery/       # Auto-discovery of applications
│   ├── controller/       # Start/stop operations
│   ├── health-monitor/   # Health checking
│   └── api-handler/     # API endpoints
├── ui/                   # React dashboard
│   └── src/             # React components
├── infrastructure/       # Infrastructure as Code (OpenTofu + Terragrunt)
│   ├── main.tf          # Core infrastructure
│   ├── lambdas.tf       # Lambda functions
│   ├── api_gateway.tf   # API Gateway
│   └── terragrunt.hcl   # Terragrunt configuration
├── scripts/             # Deployment and utility scripts
│   ├── lint.sh          # Code linting
│   ├── deploy-lambdas.sh
│   └── deploy-ui.sh
└── docs/                # Comprehensive documentation
    ├── DEPLOYMENT.md
    ├── ARCHITECTURE.md
    ├── RUNBOOK.md
    └── ...
```

## 📋 For Managers & Decision Makers

**📊 Executive Proposal**: [docs/management/EXECUTIVE_PROPOSAL.md](docs/management/EXECUTIVE_PROPOSAL.md)

This comprehensive 1,127-line proposal document is designed for management review and includes:
- **Business Case**: Problem statement, solution overview, and business impact
- **Cost Analysis**: Detailed cost breakdown, ROI of 7,660%+, annual savings of $41K-125K
- **Risk Assessment**: All potential risks identified with mitigation strategies
- **Implementation Plan**: 2.5-day timeline with hour-by-hour breakdown
- **Success Metrics**: KPIs, monitoring, and reporting framework
- **Long-Term Vision**: Future enhancements and strategic benefits
- **Approval Section**: Ready-to-sign approval form

**Perfect for**: Presenting to management, securing budget approval, justifying the investment.

**🆚 Existing Setup Comparison**: [docs/management/COMPARISON_EXISTING_VS_NEW.md](docs/management/COMPARISON_EXISTING_VS_NEW.md)

If you already have Lambda + Jenkins automation, this 827-line document compares:
- Feature-by-feature comparison (what's new vs. what you have)
- 10 key advantages of upgrading
- Migration strategies (parallel operation recommended)
- ROI analysis specific to enhancement scenario
- Decision matrix to help you decide

**⏱️ Implementation Timeline**: [docs/management/IMPLEMENTATION_TIMELINE_SUMMARY.md](docs/management/IMPLEMENTATION_TIMELINE_SUMMARY.md)

Quick 297-line reference for the 2.5-day implementation:
- Hour-by-hour breakdown for each day
- Checklists and prerequisites
- Fast-track options (2 days) and conservative options (3 days)
- Tips for success during deployment

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART.md](QUICKSTART.md) | Quick setup guide |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Detailed deployment instructions |
| [docs/PREREQUISITES.md](docs/PREREQUISITES.md) | Prerequisites checklist |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and design |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Operations and troubleshooting |
| [docs/TAGGING.md](docs/TAGGING.md) | Resource tagging requirements |
| [docs/WHAT_GETS_CREATED.md](docs/WHAT_GETS_CREATED.md) | What AWS resources are created |
| [docs/DEPLOYMENT_LOCATIONS.md](docs/DEPLOYMENT_LOCATIONS.md) | Where everything is deployed |
| [docs/USER_ACCESS.md](docs/USER_ACCESS.md) | How users access the dashboard & permissions |
| [docs/DASHBOARD_INFO.md](docs/DASHBOARD_INFO.md) | Dashboard features and deployment |
| [docs/LIGHTWEIGHT_DASHBOARD.md](docs/LIGHTWEIGHT_DASHBOARD.md) | Dashboard optimization details |
| [docs/LINTING.md](docs/LINTING.md) | Code quality and linting guide |
| [docs/APP_STATUS_VERIFICATION_CHECKLIST.md](docs/APP_STATUS_VERIFICATION_CHECKLIST.md) | **CLI checklist to verify if apps are UP/DOWN** |
| [docs/APP_STATUS_QUICK_CHEAT_SHEET.md](docs/APP_STATUS_QUICK_CHEAT_SHEET.md) | **1-page cheat sheet for quick status checks** |

**Management Documents:**
| [docs/management/EXECUTIVE_PROPOSAL.md](docs/management/EXECUTIVE_PROPOSAL.md) | **Management proposal with 2.5-day timeline and ROI** |
| [docs/management/COMPARISON_EXISTING_VS_NEW.md](docs/management/COMPARISON_EXISTING_VS_NEW.md) | **Compare with existing Jenkins + Lambda setup** |
| [docs/management/IMPLEMENTATION_TIMELINE_SUMMARY.md](docs/management/IMPLEMENTATION_TIMELINE_SUMMARY.md) | **2.5-day implementation quick reference** |
| [docs/management/PROJECT_SUMMARY.md](docs/management/PROJECT_SUMMARY.md) | **Complete project overview & achievements** |

**Implementation Guides:**
| [SHARED_DB_LOCK_IMPLEMENTATION.md](SHARED_DB_LOCK_IMPLEMENTATION.md) | **Distributed locking for shared database protection** |
| [SHARED_DATABASE_PROTECTION.md](SHARED_DATABASE_PROTECTION.md) | **Shared database protection with live HTTP checks** |
| [POD_STATUS_FIX.md](POD_STATUS_FIX.md) | **Pod status display fixes and RBAC setup** |

**User Guides:**
| [docs/guides/TEST_GUIDE.md](docs/guides/TEST_GUIDE.md) | How to test and use the system |
| [docs/guides/TEST_ALL_APPLICATIONS.md](docs/guides/TEST_ALL_APPLICATIONS.md) | **Test all apps one-by-one (9 checks each)** |
| [docs/guides/REDEPLOY_AND_VERIFY.md](docs/guides/REDEPLOY_AND_VERIFY.md) | **Redeploy & verify application status checks** |
| [docs/guides/NEXT_STEPS.md](docs/guides/NEXT_STEPS.md) | **Complete roadmap: what to do next** |
| [docs/guides/MIGRATION_GUIDE.md](docs/guides/MIGRATION_GUIDE.md) | Terraform to OpenTofu migration |

**Reference:**
| [docs/reference/COST_SUMMARY.md](docs/reference/COST_SUMMARY.md) | Cost breakdown and estimates |
| [docs/reference/COST_FAQ.md](docs/reference/COST_FAQ.md) | Cost-related frequently asked questions |
| [docs/reference/DISCOVERY_LAMBDA_FIXES.md](docs/reference/DISCOVERY_LAMBDA_FIXES.md) | Discovery Lambda bug fixes documentation |

## 🏷️ Resource Tagging & Database Discovery

**Critical:** Resources can be discovered via tags OR ConfigMaps.

### Database Discovery Methods

**Method 1: EC2 Tags (Primary)**
Tag EC2 database instances with:
```bash
aws ec2 create-tags \
  --resources i-1234567890abcdef0 \
  --tags \
    Key=AppName,Value=mi.dev.mareana.com \
    Key=Component,Value=postgres \
    Key=Shared,Value=false
```

**Method 2: ConfigMap Discovery (Automatic)**
The system automatically reads database connection details from Kubernetes ConfigMaps:
- **ConfigMap Name**: `common-config` (in each application namespace)
- **Postgres Fields**: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`
- **Neo4j Fields**: `NEO4J_URI`, `NEO4J_USERNAME`
- **Legacy Support**: Also supports `POSTGRES_IP`, `NEO4J_USER`, `POSTGRES_SSLMODE`

The Discovery Lambda automatically:
1. Reads `common-config` ConfigMap from each namespace
2. Extracts database host/IP and port information
3. Matches IPs to running EC2 instances
4. Updates the registry with database details

### EKS NodeGroups
```bash
aws eks tag-resource \
  --resource-arn arn:aws:eks:...:nodegroup/... \
  --tags AppName=mi.dev.mareana.com,Component=nodegroup
```

**Required Tags:**
- `AppName`: Application identifier (matches Ingress hostname)
- `Component`: `nodegroup`, `postgres`, or `neo4j`
- `Shared`: `true` or `false` (for databases)

**Note**: If databases are not tagged but exist in ConfigMaps, they will still be discovered automatically.

### Application → Namespace & NodeGroup Mappings

The system uses **hard-coded authoritative mappings** for application namespaces and NodeGroups:

**Namespace Mappings** (Discovery Lambda):
- Ensures correct namespace assignment for each application
- Overrides any auto-discovered or inferred namespaces
- Supports 16 applications with correct namespace assignments

**NodeGroup Mappings** (API Handler & Controller Lambdas):
- Authoritative source for application → NodeGroup assignment
- Includes default scaling values (desired, min, max)
- Applications without NodeGroups: `None` (pods only)

**Current Mappings:**
- `ai360.dev.mareana.com` → Namespace: `ai360`, NodeGroup: `ai360-ondemand`
- `ebr.dev.mareana.com` → Namespace: `ebr-dev`, NodeGroup: `vsm-dev`
- `flux.dev.mareana.com` → Namespace: `flux-system`, NodeGroup: `flux`
- `grafana.dev.mareana.com` → Namespace: `monitoring`, NodeGroup: `flux`
- `k8s-dashboard.dev.mareana.com` → Namespace: `kubernetes-dashboard`, NodeGroup: `flux`
- `prometheus.dev.mareana.com` → Namespace: `monitoring`, NodeGroup: `flux`
- `gtag.dev.mareana.com` → Namespace: `gtag-dev`, NodeGroup: `gtag-dev`
- `lab.dev.mareana.com` → Namespace: `lab-dev`, NodeGroup: `lab-dev`
- `mi-app-airflow.cloud.mareana.com` → Namespace: `mi-app`, NodeGroup: `mi-app-new`
- `mi-r1-airflow.dev.mareana.com` → Namespace: `mi-r1-dev`, NodeGroup: `mi-r1-dev`
- `mi-r1-spark.dev.mareana.com` → Namespace: `mi-r1-dev`, NodeGroup: `mi-r1-dev`
- `mi-r1.dev.mareana.com` → Namespace: `mi-r1-dev`, NodeGroup: `mi-r1-dev`
- `mi-spark.dev.mareana.com` → Namespace: `mi-app`, NodeGroup: `mi-app-new`
- `mi.dev.mareana.com` → Namespace: `mi-app`, NodeGroup: `mi-app-new`
- `vsm.dev.mareana.com` → Namespace: `vsm-dev`, NodeGroup: `vsm-dev-ng`
- `vsm-bms.dev.mareana.com` → Namespace: `vsm-bms`, NodeGroup: `None` (pods only)

See [docs/TAGGING.md](docs/TAGGING.md) for complete tagging guide.

## 🔍 Code Quality

Before deployment, run linting:

```bash
./scripts/lint.sh
```

This checks:
- Python code (Lambda functions)
- JavaScript/React code (UI)
- Terraform/OpenTofu formatting
- Shell scripts

See [docs/LINTING.md](docs/LINTING.md) for details and [LINTING_REPORT.md](LINTING_REPORT.md) for current status.

## 💰 Cost Estimate (Minimal Cost Design)

This system is designed to be **extremely cost-effective**, staying mostly within AWS free tier:

**First 12 months (with free tier):**
- **Lambda**: $0 (1M requests free/month)
- **DynamoDB**: $0 (25 GB storage + 25 RCU/WCU free)
- **API Gateway**: $0 (1M HTTP API requests free first year)
- **EventBridge**: $0 (1M events free)
- **S3**: $0-1 (5 GB + 20K requests free)

**Total: $0-1/month** ☕ (less than a cup of coffee!)

**After free tier expires (month 13+):**
- **Lambda**: $0-2 (~50K invocations/month)
- **DynamoDB**: $0-1 (minimal storage and requests)
- **API Gateway**: $1-2 (~10K requests/month)
- **S3**: $0-1 (UI hosting)

**Total: $1-6/month** (still very affordable!)

**Cost Optimization:**
- ✅ Uses HTTP API (70% cheaper than REST API)
- ✅ Pay-per-request DynamoDB (no provisioned capacity)
- ✅ Reduced polling frequency (2 hours for discovery, 1 minute for health checks)
- ✅ Optimized Lambda memory (256-512 MB based on function)
- ✅ Same-region deployment (no data transfer costs)
- ✅ Parallel execution in API Handler (faster responses, same cost)

**Quick Answers:**
- **Daily cost:** $0.00 (first year), $0.03-0.06 after
- **Monthly cost:** $0-1 (first year), $1-6 after  
- **Less than 2 coffees per month!** ☕☕

See [COST_FAQ.md](COST_FAQ.md) for quick answers, [COST_SUMMARY.md](COST_SUMMARY.md) for detailed breakdown, and [docs/COST_OPTIMIZATION.md](docs/COST_OPTIMIZATION.md) for optimization strategies.

**Key Cost Features:**
- Stays within AWS free tier for typical usage
- No provisioned capacity (pay only for actual use)
- Auto-scales to zero when idle
- No servers to maintain

## 🔐 Security Considerations

- **IAM Roles**: Least-privilege permissions for all Lambda functions
  - Controller Lambda: 
    - `ec2:StartInstances`, `ec2:StopInstances`, `ec2:DescribeInstances` (minimum required)
    - `dynamodb:PutItem`, `dynamodb:DeleteItem`, `dynamodb:Scan` (for distributed locks)
    - `dynamodb:GetItem`, `dynamodb:UpdateItem` (for registry access)
  - Discovery Lambda: Read-only permissions for EKS, EC2, Kubernetes
  - Health Monitor: Read-only permissions for health checks
  - API Handler: 
    - Read-only DynamoDB access
    - `eks:DescribeCluster`, `eks:DescribeNodegroup` for live NodeGroup checks
    - `ec2:DescribeInstances` for live database state checks
    - `autoscaling:DescribeAutoScalingGroups` for current node counts
    - Kubernetes API access for pod counts (requires RBAC - see [docs/POD_RBAC_SETUP.md](docs/POD_RBAC_SETUP.md))
- **API Gateway**: Currently public (add authentication for production)
- **Dashboard**: Public access (add CloudFront signed URLs or authentication)
- **Secrets**: No hardcoded credentials (uses IAM roles)
- **ConfigMap Access**: Discovery Lambda reads ConfigMaps using Kubernetes RBAC (read-only)

**Production Recommendations:**
- Add AWS Cognito or API Keys for API Gateway
- Use CloudFront signed URLs for dashboard
- Enable CloudTrail for audit logging
- Review and restrict IAM policies
- Consider VPC endpoints for Lambda functions accessing EKS

## 🛠️ Technology Stack

- **Infrastructure**: OpenTofu + Terragrunt
- **Lambda Runtime**: Python 3.11
- **UI Framework**: React 18
- **Build Tool**: Vite
- **API**: AWS API Gateway (HTTP API)
- **Database**: DynamoDB
- **Scheduling**: AWS EventBridge

## 📊 What Gets Created?

**Scope - Phase 1:**
- **Single AWS Account**: Manages one AWS account
- **Single EKS Cluster**: Controls one EKS cluster and its applications
- **All Applications Equal**: All apps treated the same way (no special handling)
- **User Control**: Users decide when to start/stop applications

This codebase creates a **control system** that manages your existing EKS applications. It does NOT create:
- ❌ Your EKS cluster (must exist)
- ❌ Your EC2 database instances (must exist)
- ❌ Your NodeGroups (must exist)

It DOES create:
- ✅ Lambda functions for automation
- ✅ DynamoDB table for registry
- ✅ API Gateway for REST API
- ✅ IAM roles and policies
- ✅ EventBridge rules for scheduling

See [docs/WHAT_GETS_CREATED.md](docs/WHAT_GETS_CREATED.md) for complete details.

## 🎨 Dashboard

The codebase includes a **modern React dashboard** (~100KB gzipped) with:

### Dashboard URL
**Live Dashboard**: http://eks-app-controller-ui-420464349284.s3-website-us-east-1.amazonaws.com/

### Features
- **Real-Time Live Status**: Auto-refreshes every 5 seconds with fresh data from API
  - **NO CACHING** - All status is computed live on every request
  - Database state from live EC2 instance checks
  - NodeGroup state from live EKS API calls
  - Pod counts from live Kubernetes API calls
  - HTTP status from live HTTP HEAD requests
- **Application Cards**: 
  - **Application Name** displayed prominently at top of each card
  - **Namespace** badge shown when available
  - **Hostnames** field properly populated (never shows "N/A")
  - Clean, modern card design with rounded corners and shadows
- **Component Status Indicators**: Visual indicators for Postgres, Neo4j, and NodeGroups
  - 🟢 Green = Running/Ready (Postgres/Neo4j: EC2 running, NodeGroups: ACTIVE with nodes)
  - 🔴 Red = Stopped (Postgres/Neo4j: EC2 stopped, NodeGroups: DELETING/DEGRADED/NOT_FOUND)
  - 🟡 Yellow = Starting/Scaling (NodeGroups: ACTIVE/UPDATING/CREATING)
  - Indicators appear for all applications with component data
- **Database Details**: Shows database host, port, and state (from live EC2 checks)
  - **Shared Resource Detection**: Shows "🔗 Shared Resource" badge when database is shared with other applications
  - Lists all applications sharing the same database instance
- **One-Click Operations**: Start/stop controls with automatic NodeGroup scaling
- **Smart Status Logic**: 
  - Application status determined by live HTTP check (200 = UP, else = DOWN)
  - Component states shown independently (Postgres, Neo4j, NodeGroups)
  - All status updates in real-time (no stale data)
- **Shared Resource Warnings**: 
  - Alerts when stopping apps with shared databases
  - Shows "🔗 Shared Resource" badge for databases and NodeGroups shared across applications
  - Displays list of applications sharing the same resource
  - **Distributed Lock Protection**: Prevents race conditions in concurrent stop scenarios
  - **Intelligent Stop Logic**: Shows why database was skipped (active apps detected)
- **Modern UI**: Clean card design with dark mode support
- **Responsive Design**: Works on desktop and mobile devices
- **Search & Filter**: Find applications quickly by name, namespace, or hostname

### API Endpoint
**API Gateway URL**: https://6rgavd4jt7.execute-api.us-east-1.amazonaws.com

See [docs/DASHBOARD_INFO.md](docs/DASHBOARD_INFO.md) for detailed features and deployment.

## 🧪 Testing

### **Quick Test (Single Application)**
```bash
# Test one app with 9 comprehensive checks
./scripts/test-each-application.sh mi.dev.mareana.com
```

### **Batch Test (All Applications)**
```bash
# Test all apps automatically (5 essential checks)
./scripts/test-all-apps-batch.sh

# Test all apps interactively (9 detailed checks per app)
./scripts/test-each-application.sh
```

### **Manual HTTP Test**
```bash
# Test HTTP accessibility (same as health monitor)
curl -I --max-time 5 -o /dev/null -s -w "%{http_code}\n" https://mi.dev.mareana.com
```

### **What Gets Tested**
1. ✅ DynamoDB Registry Check
2. ✅ Kubernetes Pods Check (live from Kubernetes API)
3. ✅ Kubernetes Services Check
4. ✅ Kubernetes Ingress Check
5. ✅ **HTTP Accessibility** (live HTTP HEAD request)
6. ✅ NodeGroup Status Check (live from EKS API)
7. ✅ Database Status Check (live from EC2 API)
8. ✅ API Gateway Endpoint Check
9. ✅ Status Consistency Verification

**See [TEST_ALL_APPLICATIONS.md](TEST_ALL_APPLICATIONS.md) for complete testing guide.**

## 🔒 Shared Database Protection & Distributed Locking

The system includes **advanced protection for shared databases** with distributed locking to prevent race conditions:

### **Distributed Lock Mechanism**

- **DynamoDB-Based Locks**: Uses DynamoDB with TTL for distributed locking
- **Lock Key Pattern**: `LOCK#DB#<db_identifier>` (uses EC2 instance ID or host:port)
- **Automatic Expiration**: Locks expire after 60 seconds (prevents stuck locks)
- **Atomic Operations**: Lock acquisition uses conditional writes (prevents conflicts)
- **Retry Logic**: Exponential backoff with jitter (max 3 retries)

### **Shared Database Stop Workflow**

When stopping an application with shared databases:

1. **Lock Acquisition**: Controller acquires distributed lock for database
2. **Sharing App Discovery**: Queries registry for all apps sharing the database
3. **Live Status Checks**: Calls quick-status endpoint for each sharing app (3s timeout)
4. **Decision Logic**:
   - If ANY sharing app is **UP** → Skip DB stop, release lock
   - If ANY sharing app is **UNKNOWN** → Treat as UP (fail-safe), skip DB stop
   - If ALL sharing apps are **DOWN** → Proceed to stop database
5. **Lock Release**: Releases lock only if owner matches (prevents hijacking)

### **Race Condition Prevention**

- **Concurrent Stops**: Only one controller can acquire lock at a time
- **Sequential Stops**: Lock ensures proper ordering of stop operations
- **Fail-Safe Defaults**: UNKNOWN status = UP (prevents accidental stops)
- **Lock Timeout**: Automatic expiration prevents stuck locks

### **Quick-Status Endpoint**

- **Endpoint**: `GET /status/quick?app=<app_name>`
- **Response**: `{ "app": "...", "status": "UP|DOWN|UNKNOWN", "http_code": 200, "timestamp": "..." }`
- **Timeout**: 3 seconds
- **Purpose**: Lightweight status check for Controller Lambda shared-app verification

**See [SHARED_DB_LOCK_IMPLEMENTATION.md](SHARED_DB_LOCK_IMPLEMENTATION.md) for complete implementation details.**

## 🔍 Health Monitoring

The system provides **real-time, live status monitoring** with **NO CACHING**. All status is computed fresh on every API request.

### **Live Status Checks (No Caching)**

**API Handler performs all checks live on every request:**

1. **Database State (Postgres & Neo4j)**
   - **LIVE EC2 Instance Check**: `ec2.describe_instances()` called every request
   - **Rule**: EC2 state = "running" → DB state = "running", else = "stopped"
   - **NO port checks** - EC2 instance state is the ONLY source of truth
   - **NO caching** - Fresh EC2 API call every time
   - Status reflects actual server state immediately

2. **NodeGroup State**
   - **LIVE EKS API Call**: `eks.describe_nodegroup()` called every request
   - Returns live `desired`, `min`, `max`, `current`, and `status` (ACTIVE/DEGRADED/UPDATING)
   - **NO DynamoDB cache** - Always fetches from EKS directly
   - Shows exact current scaling values
   - Also fetches current node count from Auto Scaling Groups for accurate status

3. **Pod State**
   - **LIVE Kubernetes API Call**: `k8s_client.list_namespaced_pod()` called every request
   - Returns live counts: `running`, `pending`, `crashloop`, `total`
   - Returns detailed pod lists with: `name`, `phase`, `reason`, `owner`, `created`, `restart_count`
   - **NO cached pod counts** - Always fetches from Kubernetes directly
   - Requires `eks:DescribeCluster` permission for Kubernetes client initialization
   - Requires Kubernetes RBAC permissions (see [docs/POD_RBAC_SETUP.md](docs/POD_RBAC_SETUP.md))
   - Gracefully handles 401 Unauthorized errors (returns empty lists with warning)

4. **HTTP Status**
   - **LIVE HTTP HEAD Request**: `requests.head()` called every request
   - **Strict Rule**: Only HTTP 200 = UP, everything else = DOWN
   - 5-second timeout, follows redirects, HTTPS/HTTP fallback
   - **NO cached HTTP status** - Always performs fresh HTTP check

**Parallel Execution:**
- All 4 checks run simultaneously using `ThreadPoolExecutor` for speed
- Typical API response time: 2-3 seconds for all apps

### **Health Monitor Lambda (Background)**

- Runs every **1 minute** (not 15 minutes) for background recording
- Updates DynamoDB with HTTP status and timestamps
- **Note**: UI does NOT rely on Health Monitor - API Handler performs live checks

### **Status Determination Logic**

**Component States (Live from APIs):**
- **Postgres**: 
  - `running` (EC2 instance state = "running") ✅
  - `stopped` (EC2 instance state = "stopped") ❌
- **Neo4j**: 
  - `running` (EC2 instance state = "running") ✅
  - `stopped` (EC2 instance state = "stopped") ❌
- **NodeGroups**: 
  - `ACTIVE` (EKS NodeGroup status) ✅
  - `DEGRADED` or other states ❌

**Application Final Status:**
- **UP** (🟢): HTTP status code = 200
- **DOWN** (🔴): HTTP status code ≠ 200 (including 301, 302, 401, 403, 405, 500, 503, timeout, connection errors)

**No WAITING State:**
- Application status is determined ONLY by HTTP check
- Component states are shown independently for information
- No blocking logic - HTTP check always runs

## 🚨 Troubleshooting

**Common Issues:**

1. **No applications discovered**
   - Check Ingress resources exist: `kubectl get ingress -A`
   - Verify resource tags are correct
   - Check Discovery Lambda logs

2. **Start/Stop fails**
   - Verify IAM permissions
   - Check Controller Lambda logs
   - Ensure resources exist and are tagged

3. **Dashboard shows errors**
   - Verify API Gateway URL is correct
   - Check CORS configuration
   - Review browser console

4. **Dashboard not showing live updates**
   - API Handler performs all checks live (no caching)
   - Dashboard auto-refreshes every 5 seconds
   - Hard refresh browser (Ctrl+Shift+R / Cmd+Shift+R) to clear cache
   - Check browser console (F12) for API errors

5. **Application name or hostnames showing as "N/A"**
   - Fixed in latest update - API now returns `name`, `hostname`, `hostnames` fields
   - UI displays application name at top of each card
   - Hostnames field shows actual values (never "N/A")
   - Hard refresh dashboard to see updates

See [docs/RUNBOOK.md](docs/RUNBOOK.md) for detailed troubleshooting.

## 📝 License

This project is provided as-is for use in your environment.

## 🤝 Support

- **Documentation**: See `docs/` directory
- **Issues**: Check CloudWatch logs for Lambda functions
- **Questions**: Review architecture and runbook documentation

## 🎯 Next Steps

1. ✅ Review [docs/PREREQUISITES.md](docs/PREREQUISITES.md)
2. ✅ Tag your resources per [docs/TAGGING.md](docs/TAGGING.md)
3. ✅ Deploy infrastructure with `terragrunt apply`
4. ✅ Configure Kubernetes RBAC for pod status (see [docs/POD_RBAC_SETUP.md](docs/POD_RBAC_SETUP.md))
5. ✅ Deploy dashboard to S3/CloudFront
6. ✅ Start managing your applications!

## 🆕 Recent Updates

### **Distributed Locking for Shared Databases** (Latest)
- ✅ Distributed lock mechanism using DynamoDB with TTL
- ✅ Prevents race conditions in concurrent stop scenarios
- ✅ Quick-status endpoint for lightweight app status checks
- ✅ Enhanced shared database protection with live status verification
- ✅ Fail-safe design: UNKNOWN status treated as UP

### **Pod Status Display** (Latest)
- ✅ Live pod counts from Kubernetes API
- ✅ RBAC configuration for pod listing permissions
- ✅ Detailed pod information (running, pending, crashloop)
- ✅ Graceful error handling for missing permissions

### **Multi-Account Configuration** (Previous)
- ✅ Centralized `config/config.yaml` for all account settings
- ✅ Single source of truth for namespace and NodeGroup mappings
- ✅ Easy deployment to new AWS accounts

---

**Ready to deploy?** Start with [QUICKSTART.md](QUICKSTART.md) or [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## 📋 Application Configuration

### Supported Applications

The system currently supports **16 applications** with hard-coded namespace and NodeGroup mappings:

| Application | Namespace | NodeGroup | Default Scaling |
|------------|-----------|-----------|-----------------|
| ai360.dev.mareana.com | ai360 | ai360-ondemand | desired=1, min=1, max=2 |
| ebr.dev.mareana.com | ebr-dev | vsm-dev | desired=1, min=1, max=2 |
| flux.dev.mareana.com | flux-system | flux | desired=1, min=1, max=2 |
| grafana.dev.mareana.com | monitoring | flux | desired=1, min=1, max=2 |
| k8s-dashboard.dev.mareana.com | kubernetes-dashboard | flux | desired=1, min=1, max=2 |
| prometheus.dev.mareana.com | monitoring | flux | desired=1, min=1, max=2 |
| gtag.dev.mareana.com | gtag-dev | gtag-dev | desired=1, min=1, max=2 |
| lab.dev.mareana.com | lab-dev | lab-dev | desired=1, min=1, max=2 |
| mi-app-airflow.cloud.mareana.com | mi-app | mi-app-new | desired=2, min=1, max=2 |
| mi-r1-airflow.dev.mareana.com | mi-r1-dev | mi-r1-dev | desired=1, min=1, max=2 |
| mi-r1-spark.dev.mareana.com | mi-r1-dev | mi-r1-dev | desired=1, min=1, max=2 |
| mi-r1.dev.mareana.com | mi-r1-dev | mi-r1-dev | desired=1, min=1, max=2 |
| mi-spark.dev.mareana.com | mi-app | mi-app-new | desired=1, min=1, max=2 |
| mi.dev.mareana.com | mi-app | mi-app-new | desired=1, min=1, max=2 |
| vsm-bms.dev.mareana.com | vsm-bms | None (pods only) | - |
| vsm.dev.mareana.com | vsm-dev | vsm-dev-ng | desired=1, min=1, max=2 |

**Note**: Applications with `NodeGroup: None` only scale pods, not NodeGroups.

### Adding New Applications

To add a new application:

1. **Update Discovery Lambda** (`lambdas/discovery/lambda_function.py`):
   - Add namespace mapping to `APP_NAMESPACE_MAPPING`

2. **Update API Handler & Controller Lambdas**:
   - Add NodeGroup mapping to `NODEGROUP_DEFAULTS` (or set to `None` for pods only)

3. **Rebuild and Deploy**:
   ```bash
   ./build-lambdas.sh
   aws lambda update-function-code --function-name eks-app-controller-discovery --zip-file fileb://build/discovery.zip
   aws lambda update-function-code --function-name eks-app-controller-api-handler --zip-file fileb://build/api-handler.zip
   aws lambda update-function-code --function-name eks-app-controller-controller --zip-file fileb://build/controller.zip
   ```

4. **Run Discovery Lambda**:
   ```bash
   aws lambda invoke --function-name eks-app-controller-discovery --region us-east-1 /tmp/discovery-output.json
   ```

