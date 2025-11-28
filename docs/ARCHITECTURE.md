# Architecture Documentation

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React UI (S3/CloudFront)                 │
│              https://app-controller.example.com             │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ HTTPS
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway (HTTP API)                  │
│              /apps  /start  /stop                            │
└──────┬──────────────┬──────────────┬─────────────────────────┘
       │              │              │
       │              │              │
       ▼              ▼              ▼
┌──────────┐  ┌──────────────┐  ┌──────────────┐
│ API      │  │ Controller   │  │ Controller   │
│ Handler  │  │ Lambda       │  │ Lambda       │
│ Lambda   │  │ (Start)      │  │ (Stop)       │
└────┬─────┘  └──────┬───────┘  └──────┬───────┘
     │               │                  │
     │               │                  │
     └───────────────┴──────────────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  DynamoDB Registry   │
          │  (App Metadata)      │
          └──────────┬───────────┘
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
┌──────────┐  ┌──────────┐  ┌──────────────┐
│Discovery │  │  Health  │  │  EventBridge │
│ Lambda   │  │ Monitor  │  │  (Scheduler)  │
└────┬─────┘  └────┬─────┘  └──────────────┘
     │             │
     │             │
     ▼             ▼
┌─────────────────────────────────────────┐
│         AWS EKS Cluster                  │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ Ingress    │  │  NodeGroups      │   │
│  │ Resources  │  │  (Auto-scaled)   │   │
│  └────────────┘  └──────────────────┘   │
└─────────────────────────────────────────┘
     │
     │
     ▼
┌─────────────────────────────────────────┐
│         EC2 Instances                    │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ PostgreSQL │  │  Neo4j           │   │
│  │ (Tagged)   │  │  (Tagged)        │   │
│  └────────────┘  └──────────────────┘   │
└─────────────────────────────────────────┘
```

## Component Details

### 1. Discovery Lambda

**Purpose**: Automatically detect applications and their dependencies

**Trigger**: EventBridge (hourly) or manual invocation

**Process**:
1. Scan all Kubernetes Ingress resources across namespaces
2. Extract hostnames from Ingress rules
3. Map hostnames to NodeGroups via tags
4. Map hostnames to EC2 database instances via tags
5. Detect shared resources (databases used by multiple apps)
6. Update DynamoDB registry

**Input**: None (scans cluster)

**Output**: Updated registry entries in DynamoDB

### 2. Controller Lambda

**Purpose**: Start or stop applications and dependencies

**Trigger**: API Gateway (POST /start or POST /stop)

**Process (Start)**:
1. Read app configuration from DynamoDB
2. Scale NodeGroups to desired capacity
3. Start PostgreSQL EC2 instances
4. Start Neo4j EC2 instances
5. Update registry status to "UP"

**Process (Stop)**:
1. Read app configuration from DynamoDB
2. Check for shared resources
3. Scale NodeGroups to 0
4. Stop PostgreSQL instances (skip if shared)
5. Stop Neo4j instances (skip if shared)
6. Update registry status to "DOWN"
7. Return warnings for shared resources

**Input**: `{"app_name": "mi.dev.mareana.com"}`

**Output**: Operation result with status and warnings

### 3. Health Monitor Lambda

**Purpose**: Periodically check application health

**Trigger**: EventBridge (every 5 minutes)

**Process**:
1. Scan all apps in registry
2. For each app:
   - Check NodeGroup desired size > 0
   - Check EC2 instance states (running)
   - Check Ingress endpoint reachability
3. Determine status: UP, DOWN, or DEGRADED
4. Update registry with status

**Input**: None (scans registry)

**Output**: Updated status in DynamoDB

### 4. API Handler Lambda

**Purpose**: Serve application list API

**Trigger**: API Gateway (GET /apps)

**Process**:
1. Scan DynamoDB registry
2. Format application data for UI
3. Return JSON response

**Input**: None

**Output**: `{"apps": [...], "count": N}`

### 5. DynamoDB Registry

**Schema**:
```json
{
  "app_name": "mi.dev.mareana.com",
  "hostnames": ["mi.dev.mareana.com"],
  "nodegroups": [
    {
      "name": "ng-app-mi",
      "desired_size": 2,
      "min_size": 0,
      "max_size": 10
    }
  ],
  "postgres_instances": ["i-1234567890abcdef0"],
  "neo4j_instances": ["i-0987654321fedcba0"],
  "shared_resources": {
    "postgres": [],
    "neo4j": []
  },
  "status": "UP",
  "health_url": "/healthz",
  "last_updated": "2024-01-01T00:00:00Z",
  "last_health_check": "2024-01-01T00:05:00Z"
}
```

**Partition Key**: `app_name` (String)

### 6. React UI

**Features**:
- Auto-refresh every 30 seconds
- Status indicators (🟢 UP, 🔴 DOWN, 🟡 DEGRADED)
- One-click start/stop
- Shared resource warnings
- Application details display

**Technology**: React 18, Vite, Axios

## Data Flow

### Discovery Flow
```
EventBridge → Discovery Lambda → Kubernetes API → EKS API → EC2 API → DynamoDB
```

### Start/Stop Flow
```
UI → API Gateway → Controller Lambda → EKS API / EC2 API → DynamoDB → Response
```

### Health Check Flow
```
EventBridge → Health Monitor Lambda → EKS API / EC2 API / HTTP → DynamoDB
```

## Security Considerations

1. **IAM Roles**: Least privilege principle
2. **API Gateway**: Consider adding authentication (Cognito, API Keys)
3. **Lambda VPC**: If accessing private resources
4. **DynamoDB**: Enable encryption at rest
5. **S3/CloudFront**: Enable HTTPS only
6. **Kubernetes RBAC**: Lambda needs read access to Ingress

## Scalability

- **DynamoDB**: Pay-per-request (auto-scaling)
- **Lambda**: Automatic scaling (concurrent executions)
- **API Gateway**: Handles high request volumes
- **EventBridge**: Reliable scheduling

## High Availability

- **Lambda**: Multi-AZ by default
- **DynamoDB**: Multi-AZ replication
- **API Gateway**: Regional service
- **S3/CloudFront**: Global distribution

## Cost Optimization

- **DynamoDB**: Pay-per-request (cost-effective for low-medium traffic)
- **Lambda**: Pay per invocation (very cost-effective)
- **EventBridge**: Free tier includes 1M custom events/month
- **API Gateway**: Pay per API call
- **S3/CloudFront**: Pay for storage and data transfer

## Tagging Strategy

All resources must follow this tagging standard:

**EC2 Instances:**
- `AppName`: Application identifier (e.g., `mi.dev.mareana.com`)
- `Component`: `postgres` or `neo4j`
- `Shared`: `true` or `false`

**NodeGroups:**
- `AppName`: Application identifier
- `Component`: `nodegroup`

**Ingress:**
- Tagged via Kubernetes labels (optional, hostname used as identifier)

## Error Handling

1. **Lambda Errors**: Logged to CloudWatch, return error response
2. **API Errors**: Return appropriate HTTP status codes
3. **Shared Resources**: Warn but don't fail
4. **Missing Resources**: Log warning, continue with available resources

## Future Enhancements

1. Authentication/Authorization (Cognito, OAuth)
2. Audit logging (CloudTrail integration)
3. Cost tracking per application
4. Scheduled start/stop (cron-like)
5. Multi-cluster support
6. Slack/Teams notifications
7. Application dependency graphs
8. Rollback capabilities


