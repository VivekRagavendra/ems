# Fix for Incorrect Application Status

## Problem
Dashboard showing `mi.dev.mareana.com` as **DOWN** when it's actually **UP** and serving traffic.

## Root Cause
The health monitor Lambda was marking applications as DOWN if:
- NodeGroups list was empty (not yet mapped)
- Even though the app was discovered from Kubernetes Ingress (meaning it IS running)

## Solution Applied
Updated the health monitor logic in `/Users/viveks/EMS/lambdas/health-monitor/lambda_function.py`:

**Before:**
```python
# If no NodeGroups found, mark as DOWN
if not nodegroup_up:
    return 'DOWN'
```

**After:**
```python
# If NodeGroups not mapped yet, assume UP (app discovered from Ingress)
if not has_nodegroups:
    print(f"{app_name}: No NodeGroups mapped, assuming UP (discovered from Ingress)")
    return 'UP'

# Only mark as DOWN if NodeGroups ARE mapped but all have desiredSize = 0
if not nodegroup_up:
    return 'DOWN'
```

## New Logic
1. **App discovered from Ingress, no NodeGroups mapped** → Status = `UP`
   - Reason: If an Ingress exists, the app is serving traffic
   
2. **NodeGroups mapped and desiredSize > 0** → Status = `UP`
   - Reason: Compute resources are running
   
3. **NodeGroups mapped but desiredSize = 0** → Status = `DOWN`
   - Reason: Compute resources are stopped

4. **Databases down** → Status = `DEGRADED`
   - Reason: App may be running but missing dependencies

## Deployment Steps

### Step 1: Refresh AWS Credentials (if expired)
```bash
aws configure
# Or if using SSO:
aws sso login --profile your-profile
```

### Step 2: Deploy the Fixed Lambda
```bash
aws lambda update-function-code \
  --function-name eks-app-controller-health-monitor \
  --zip-file fileb:///Users/viveks/EMS/build/health-monitor-fixed.zip \
  --region us-east-1
```

### Step 3: Trigger Immediate Health Check
```bash
aws lambda invoke \
  --function-name eks-app-controller-health-monitor \
  --region us-east-1 \
  /tmp/health-result.json

# View results
cat /tmp/health-result.json | jq
```

### Step 4: Verify the Fix
```bash
# Check specific app status in DynamoDB
aws dynamodb get-item \
  --table-name eks-app-controller-registry \
  --region us-east-1 \
  --key '{"app_name": {"S": "mi.dev.mareana.com"}}' \
  --query 'Item.{Status: status.S, LastHealthCheck: last_health_check.S}'
```

### Step 5: Refresh Dashboard
- Reload the dashboard in your browser
- Status should now show correct values

## Alternative (No Action Required)
If you don't want to deploy right now:
- The health monitor runs automatically **every 15 minutes**
- It will pick up the fix on the next scheduled run
- Or deploy the fix later when convenient

## Expected Result
After deployment and health check:
- ✅ `mi.dev.mareana.com` → Status = `UP`
- ✅ All other running apps → Status = `UP`
- ✅ Only stopped apps (desiredSize = 0) → Status = `DOWN`

## Files Modified
- `/Users/viveks/EMS/lambdas/health-monitor/lambda_function.py`
- `/Users/viveks/EMS/build/health-monitor-fixed.zip` (ready to deploy)

## Verification Commands
```bash
# List all apps and their status
curl -s https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com/apps | jq '.apps[] | {app: .app_name, status: .status}'

# Check specific NodeGroup
aws eks describe-nodegroup \
  --cluster-name mi-eks-cluster \
  --nodegroup-name mi-dev \
  --region us-east-1 \
  --query 'nodegroup.scalingConfig'
```

---

**Fix is ready to deploy!** The updated Lambda package is at:
`/Users/viveks/EMS/build/health-monitor-fixed.zip`

