# Resource Tagging Guide

Proper tagging is **critical** for the auto-discovery system to work correctly. All resources must be tagged according to this standard.

## Tagging Requirements

### EC2 Database Instances (PostgreSQL)

**Required Tags:**
- `AppName`: Application identifier (e.g., `mi.dev.mareana.com`)
- `Component`: Must be `postgres`
- `Shared`: `true` if shared with other apps, `false` otherwise

**Example:**
```bash
aws ec2 create-tags \
  --resources i-1234567890abcdef0 \
  --tags \
    Key=AppName,Value=mi.dev.mareana.com \
    Key=Component,Value=postgres \
    Key=Shared,Value=false
```

### EC2 Database Instances (Neo4j)

**Required Tags:**
- `AppName`: Application identifier
- `Component`: Must be `neo4j`
- `Shared`: `true` if shared with other apps, `false` otherwise

**Example:**
```bash
aws ec2 create-tags \
  --resources i-0987654321fedcba0 \
  --tags \
    Key=AppName,Value=mi.dev.mareana.com \
    Key=Component,Value=neo4j \
    Key=Shared,Value=false
```

### EKS NodeGroups

**Required Tags:**
- `AppName`: Application identifier
- `Component`: Must be `nodegroup`

**Example:**
```bash
aws eks tag-resource \
  --resource-arn arn:aws:eks:us-east-1:123456789012:nodegroup/my-cluster/my-nodegroup/12345678-1234-1234-1234-123456789012 \
  --tags \
    AppName=mi.dev.mareana.com \
    Component=nodegroup
```

**Note**: NodeGroups can also be tagged during creation via Terraform/CloudFormation.

## Tagging Best Practices

### 1. Use Consistent AppName Format

Use the primary hostname as the AppName:
- ✅ `mi.dev.mareana.com`
- ✅ `app1.production.example.com`
- ❌ `MI App`
- ❌ `app-1`

### 2. Shared Resources

**When to mark as Shared:**
- Database instance serves multiple applications
- Multiple apps read/write to the same database
- Database is a shared service

**Example - Shared PostgreSQL:**
```bash
# Tag for App 1
aws ec2 create-tags \
  --resources i-shared-db \
  --tags \
    Key=AppName,Value=app1.example.com \
    Key=Component,Value=postgres \
    Key=Shared,Value=true

# Tag for App 2 (same instance)
aws ec2 create-tags \
  --resources i-shared-db \
  --tags \
    Key=AppName,Value=app2.example.com \
    Key=Component,Value=postgres \
    Key=Shared,Value=true
```

**Important**: The system will detect shared resources automatically by checking if multiple apps have the same instance ID.

### 3. Multiple NodeGroups per App

If an application uses multiple NodeGroups, tag all of them with the same `AppName`:

```bash
# NodeGroup 1
aws eks tag-resource \
  --resource-arn arn:aws:eks:...:nodegroup/cluster/ng-app-1/... \
  --tags AppName=mi.dev.mareana.com,Component=nodegroup

# NodeGroup 2
aws eks tag-resource \
  --resource-arn arn:aws:eks:...:nodegroup/cluster/ng-app-2/... \
  --tags AppName=mi.dev.mareana.com,Component=nodegroup
```

### 4. Ingress Resources

Ingress resources are discovered automatically by scanning Kubernetes. The hostname from the Ingress rule is used as the `AppName`. No manual tagging required, but you can add labels for organization:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  labels:
    app: mi.dev.mareana.com
    component: ingress
spec:
  rules:
  - host: mi.dev.mareana.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: app-service
            port:
              number: 80
```

## Verification

### Check EC2 Tags

```bash
aws ec2 describe-instances \
  --filters "Name=tag:Component,Values=postgres" \
  --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`AppName`].Value|[0],Tags[?Key==`Component`].Value|[0],Tags[?Key==`Shared`].Value|[0]]' \
  --output table
```

### Check NodeGroup Tags

```bash
aws eks describe-nodegroup \
  --cluster-name my-cluster \
  --nodegroup-name my-nodegroup \
  --query 'nodegroup.tags' \
  --output json
```

### Verify Discovery

After tagging, run discovery and check DynamoDB:

```bash
# Trigger discovery
aws lambda invoke \
  --function-name eks-app-controller-discovery \
  response.json

# Check registry
aws dynamodb scan \
  --table-name eks-app-controller-registry \
  --filter-expression "app_name = :name" \
  --expression-attribute-values '{":name":{"S":"mi.dev.mareana.com"}}'
```

## Common Tagging Mistakes

### ❌ Wrong Component Value
```bash
# Wrong
Key=Component,Value=PostgreSQL  # Should be lowercase "postgres"
Key=Component,Value=db          # Should be "postgres" or "neo4j"
```

### ❌ Missing Shared Tag
```bash
# Missing Shared tag - system will assume false
Key=AppName,Value=app.example.com
Key=Component,Value=postgres
# Missing: Key=Shared,Value=true
```

### ❌ Inconsistent AppName
```bash
# AppName doesn't match Ingress hostname
# Ingress: mi.dev.mareana.com
# Tag: AppName=mi-app  # Wrong!
```

### ❌ Case Sensitivity
```bash
# Tags are case-sensitive
Key=appname,Value=...  # Wrong! Should be "AppName"
Key=APPNAME,Value=...  # Wrong! Should be "AppName"
```

## Tagging Scripts

### Bulk Tag EC2 Instances

```bash
#!/bin/bash
# Tag multiple PostgreSQL instances for an app

APP_NAME="mi.dev.mareana.com"
INSTANCE_IDS=("i-123" "i-456" "i-789")

for instance_id in "${INSTANCE_IDS[@]}"; do
  aws ec2 create-tags \
    --resources "$instance_id" \
    --tags \
      Key=AppName,Value="$APP_NAME" \
      Key=Component,Value=postgres \
      Key=Shared,Value=false
done
```

### Tag All NodeGroups in Cluster

```bash
#!/bin/bash
# Tag all nodegroups for an app

CLUSTER_NAME="my-cluster"
APP_NAME="mi.dev.mareana.com"

NODEGROUPS=$(aws eks list-nodegroups --cluster-name "$CLUSTER_NAME" --query 'nodegroups[]' --output text)

for ng in $NODEGROUPS; do
  NG_ARN=$(aws eks describe-nodegroup \
    --cluster-name "$CLUSTER_NAME" \
    --nodegroup-name "$ng" \
    --query 'nodegroup.nodegroupArn' \
    --output text)
  
  aws eks tag-resource \
    --resource-arn "$NG_ARN" \
    --tags AppName="$APP_NAME" Component=nodegroup
done
```

## Troubleshooting

### Resources Not Discovered

1. **Check tags exist:**
   ```bash
   aws ec2 describe-instances --instance-ids i-xxx --query 'Reservations[].Instances[].Tags'
   ```

2. **Check tag values match exactly:**
   - `AppName` must match Ingress hostname
   - `Component` must be exactly `postgres`, `neo4j`, or `nodegroup`
   - Case-sensitive!

3. **Check instance state:**
   - Discovery finds instances in `running` or `stopped` state
   - Terminated instances are ignored

### Shared Resources Not Detected

1. **Verify Shared tag:**
   ```bash
   aws ec2 describe-instances --instance-ids i-xxx \
     --query 'Reservations[].Instances[].Tags[?Key==`Shared`]'
   ```

2. **Check multiple apps have same instance:**
   - Discovery checks if multiple `AppName` values reference same instance ID
   - Both apps must be in registry

3. **Review Discovery Lambda logs:**
   ```bash
   aws logs tail /aws/lambda/eks-app-controller-discovery --follow
   ```


