# Pod Status Display Fix

## Problem

Dashboard always shows:
- Running: 0
- Pending: 0
- CrashLoop: 0
- Total: 0

for all applications, even when pods exist.

## Root Causes Identified

1. **Kubernetes Client Initialization** - May fail silently
2. **RBAC Permissions** - 401/403 errors not properly handled
3. **Namespace Mapping** - Wrong namespace being used
4. **Error Handling** - Exceptions being swallowed
5. **Response Structure** - Pods data may not be included in response

## Fixes Applied

### 1. Enhanced Kubernetes Client Initialization

**File**: `lambdas/api-handler/lambda_function.py`

- Added detailed logging for each step of client initialization
- Added connection test after initialization
- Better error messages for missing permissions
- Handles both 401 (Unauthorized) and 403 (Forbidden) errors
- Fallback to kubeconfig for local testing

**Changes**:
- Logs cluster endpoint, certificate size, token generation
- Tests connection by listing namespaces
- Clear error messages for RBAC issues

### 2. Improved Pod Fetching with Error Handling

**File**: `lambdas/api-handler/lambda_function.py` - `check_pod_state_live()`

- Handles 401 Unauthorized (RBAC permission denied)
- Handles 403 Forbidden (RBAC permission denied)
- Returns structured error information
- Always returns pods dict (even on error)
- Detailed logging for debugging

**Error Response Format**:
```python
{
    'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
    'running_list': [], 'pending_list': [], 'crashloop_list': [],
    'error': 'RBAC permission denied (HTTP 403)',
    'warning': 'No permission to list pods in namespace X. See docs/POD_RBAC_SETUP.md'
}
```

### 3. Namespace Determination

**File**: `lambdas/api-handler/lambda_function.py` - `get_app_live_status()`

- Uses authoritative namespace mapping from `config/config.yaml`
- Logs namespace override when mapping differs from DynamoDB
- Ensures correct namespace is used for pod listing

**Logging**:
```
✅ Using namespace for mi.dev.mareana.com: mi-app
🔄 Namespace override for app: discovered → mi-app (from config mapping)
```

### 4. Response Structure Validation

**File**: `lambdas/api-handler/lambda_function.py` - `get_app_live_status()`

- Ensures pods dict always has all required fields
- Validates pods data structure before returning
- Adds default values if missing
- Timeout handling for pod checks (30 seconds)

### 5. UI Debug Logging

**File**: `ui/src/App.jsx`

- Added console logging for pod data in API response
- Logs sample app pod data for debugging
- Helps identify if data is missing from API

## Testing

### Verify Pod Counts

1. **Check CloudWatch Logs**:
   ```bash
   aws logs tail /aws/lambda/eks-app-controller-api-handler --follow
   ```

   Look for:
   - `✅ Successfully retrieved X pods from namespace Y`
   - `✅ Pod state for namespace: running=X, pending=Y, crashloop=Z, total=N`
   - `⚠️ Kubernetes RBAC: No permission...` (if RBAC not configured)

2. **Check Browser Console**:
   - Open dashboard
   - Press F12 → Console tab
   - Look for: `Sample app pod data: { app: "...", pods: {...}, namespace: "..." }`

3. **Test Specific App**:
   ```bash
   # Get pod data for specific app
   curl https://YOUR_API_GATEWAY_URL/apps/mi.dev.mareana.com | jq '.pods'
   ```

## Expected Behavior After Fix

### When RBAC is Configured

```
✅ Pod state for mi-app: running=12, pending=1, crashloop=0, total=13
```

Dashboard shows:
- Running: 12
- Pending: 1
- CrashLoop: 0
- Total: 13

### When RBAC is Missing

```
⚠️ Kubernetes RBAC: No permission to list pods in namespace mi-app (HTTP 403)
```

Dashboard shows:
- Running: 0
- Pending: 0
- CrashLoop: 0
- Total: 0
- (With warning message in logs)

## RBAC Setup Required

If pod counts are still 0, check RBAC permissions:

1. **Verify RBAC is configured**:
   ```bash
   kubectl get clusterrole eks-api-handler-lambda-role
   kubectl get clusterrolebinding eks-api-handler-lambda-binding
   ```

2. **Check aws-auth ConfigMap**:
   ```bash
   kubectl get configmap aws-auth -n kube-system -o yaml
   ```

3. **See**: `docs/POD_RBAC_SETUP.md` for complete setup instructions

## Deployment

1. **Rebuild Lambda packages**:
   ```bash
   ./build-lambdas.sh
   ```

2. **Deploy API Handler**:
   ```bash
   aws lambda update-function-code \
     --function-name eks-app-controller-api-handler \
     --zip-file fileb://build/api-handler.zip \
     --region us-east-1
   ```

3. **Verify**:
   - Check CloudWatch logs for pod retrieval messages
   - Refresh dashboard
   - Check browser console for pod data

## Troubleshooting

### Still Showing 0 Pods?

1. **Check namespace is correct**:
   - Verify `config/config.yaml` has correct namespace mapping
   - Check CloudWatch logs for namespace being used

2. **Check RBAC permissions**:
   - Look for 401/403 errors in logs
   - Follow `docs/POD_RBAC_SETUP.md` to configure RBAC

3. **Check Kubernetes client initialization**:
   - Look for "✅ Kubernetes client initialized and tested successfully"
   - If missing, check EKS cluster access and IAM permissions

4. **Verify pods exist**:
   ```bash
   kubectl get pods -n <namespace>
   ```

5. **Test API directly**:
   ```bash
   curl https://YOUR_API_GATEWAY_URL/apps | jq '.[0].pods'
   ```

## Files Changed

- `lambdas/api-handler/lambda_function.py` - Enhanced pod fetching, error handling, logging
- `ui/src/App.jsx` - Added debug logging for pod data

## Next Steps

1. Deploy updated API Handler Lambda
2. Check CloudWatch logs for pod retrieval
3. Verify dashboard shows correct pod counts
4. If still 0, check RBAC setup (see `docs/POD_RBAC_SETUP.md`)

