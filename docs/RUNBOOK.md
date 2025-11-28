# Operations Runbook

## Overview

This runbook provides operational procedures for the EKS Application Start/Stop Controller system.

## System Components

1. **Discovery Lambda**: Scans Ingress, detects apps, updates registry (runs hourly)
2. **Controller Lambda**: Handles start/stop operations (triggered via API)
3. **Health Monitor Lambda**: Checks application health (runs every 5 minutes)
4. **API Handler Lambda**: Serves application list API (triggered via API Gateway)
5. **DynamoDB Registry**: Central store for application metadata
6. **API Gateway**: REST API endpoint
7. **React UI**: Web dashboard

## Common Operations

### Viewing All Applications

**Via UI:**
1. Open the web dashboard
2. Applications are automatically listed with status

**Via API:**
```bash
curl https://your-api-gateway-url.execute-api.region.amazonaws.com/prod/apps
```

**Via AWS CLI:**
```bash
aws dynamodb scan --table-name eks-app-controller-registry
```

### Starting an Application

**Via UI:**
1. Find the application card
2. Click "▶ Start" button
3. Wait for confirmation message

**Via API:**
```bash
curl -X POST https://your-api-gateway-url.execute-api.region.amazonaws.com/prod/start \
  -H "Content-Type: application/json" \
  -d '{"app_name": "mi.dev.mareana.com"}'
```

**What happens:**
1. NodeGroups scaled up to desired capacity
2. PostgreSQL EC2 instances started
3. Neo4j EC2 instances started
4. Registry status updated to "UP"

### Stopping an Application

**Via UI:**
1. Find the application card
2. Click "⏹ Stop" button
3. Confirm if shared resources warning appears
4. Wait for confirmation message

**Via API:**
```bash
curl -X POST https://your-api-gateway-url.execute-api.region.amazonaws.com/prod/stop \
  -H "Content-Type: application/json" \
  -d '{"app_name": "mi.dev.mareana.com"}'
```

**What happens:**
1. NodeGroups scaled down to 0
2. PostgreSQL EC2 instances stopped (if not shared)
3. Neo4j EC2 instances stopped (if not shared)
4. Registry status updated to "DOWN"
5. Warnings shown for shared resources

### Manual Discovery Trigger

If you need to force a discovery run:

```bash
aws lambda invoke \
  --function-name eks-app-controller-discovery \
  --payload '{}' \
  response.json

cat response.json
```

### Checking Application Status

**Via UI:**
- Status badges show: 🟢 UP, 🔴 DOWN, 🟡 DEGRADED

**Via API:**
```bash
curl https://your-api-gateway-url.execute-api.region.amazonaws.com/prod/apps | jq '.apps[] | select(.app_name=="mi.dev.mareana.com")'
```

**Status Meanings:**
- **UP**: NodeGroups running, databases running, ingress reachable
- **DOWN**: NodeGroups at 0, or services unreachable
- **DEGRADED**: Partial up (e.g., DB up but pods down, or ingress unreachable)

### Viewing Lambda Logs

```bash
# Discovery Lambda
aws logs tail /aws/lambda/eks-app-controller-discovery --follow

# Controller Lambda
aws logs tail /aws/lambda/eks-app-controller-controller --follow

# Health Monitor Lambda
aws logs tail /aws/lambda/eks-app-controller-health-monitor --follow

# API Handler Lambda
aws logs tail /aws/lambda/eks-app-controller-api-handler --follow
```

## Troubleshooting

### Application Not Appearing in UI

**Possible causes:**
1. Discovery hasn't run yet
2. No Ingress resources found
3. Lambda error during discovery

**Resolution:**
1. Check Discovery Lambda logs
2. Manually trigger discovery
3. Verify Ingress resources exist in cluster
4. Check DynamoDB table for entries

### Start/Stop Operation Fails

**Possible causes:**
1. IAM permissions insufficient
2. NodeGroup doesn't exist
3. EC2 instance not found
4. Resource already in target state

**Resolution:**
1. Check Controller Lambda logs
2. Verify IAM role permissions
3. Check resource tags
4. Verify resource exists in AWS

### Shared Resource Warning Appears

**What it means:**
- Database instance is tagged with `Shared=true`
- Multiple applications use the same database
- Database will NOT be stopped

**Resolution:**
- This is expected behavior
- Review database tagging if incorrect
- Manually stop shared databases if needed (with caution)

### Health Check Shows DEGRADED

**Possible causes:**
1. NodeGroup running but pods not ready
2. Database running but not accessible
3. Ingress endpoint unreachable

**Resolution:**
1. Check Kubernetes pod status: `kubectl get pods -A`
2. Check database connectivity
3. Verify ingress configuration
4. Check application logs

## Emergency Procedures

### System-Wide Shutdown

To stop all applications:

```bash
# Get all apps
APPS=$(aws dynamodb scan --table-name eks-app-controller-registry --query 'Items[].app_name.S' --output text)

# Stop each app
for app in $APPS; do
  curl -X POST https://your-api-gateway-url/stop \
    -H "Content-Type: application/json" \
    -d "{\"app_name\": \"$app\"}"
done
```

### Manual Registry Update

If registry is corrupted or needs manual update:

```bash
aws dynamodb put-item \
  --table-name eks-app-controller-registry \
  --item '{
    "app_name": {"S": "mi.dev.mareana.com"},
    "status": {"S": "UP"},
    "hostnames": {"L": [{"S": "mi.dev.mareana.com"}]},
    "nodegroups": {"L": []},
    "postgres_instances": {"L": []},
    "neo4j_instances": {"L": []}
  }'
```

### Disable Auto-Discovery

To temporarily disable automatic discovery:

```bash
# Disable EventBridge rule
aws events disable-rule --name eks-app-controller-discovery-schedule
```

Re-enable:
```bash
aws events enable-rule --name eks-app-controller-discovery-schedule
```

## Monitoring

### Key Metrics to Monitor

1. **Discovery Lambda**: Execution time, success rate
2. **Controller Lambda**: Start/stop operation success rate
3. **Health Monitor**: Health check accuracy
4. **DynamoDB**: Read/Write capacity, throttling
5. **API Gateway**: Request count, latency, errors

### CloudWatch Alarms

Recommended alarms:
- Lambda function errors > threshold
- DynamoDB throttling
- API Gateway 5xx errors
- Health check failures for critical apps

## Maintenance

### Regular Tasks

1. **Weekly**: Review Lambda logs for errors
2. **Monthly**: Review and update resource tags
3. **Quarterly**: Review IAM permissions
4. **As needed**: Update Lambda runtime versions

### Backup

- DynamoDB: Enable point-in-time recovery
- Lambda code: Version control (Git)
- Terraform state: Store in S3 with versioning

## Support Contacts

- **Infrastructure Team**: For AWS resource issues
- **Platform Team**: For EKS/Kubernetes issues
- **Development Team**: For application-specific issues


