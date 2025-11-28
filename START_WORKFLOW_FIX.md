# Start Workflow Fix - Root Cause Analysis & Solution

## 🔍 Root Cause Analysis

### Problem
Steps 3-5 of the Start Application workflow were not executing:
- ❌ NodeGroups were NOT scaled up
- ❌ Kubernetes Deployments/StatefulSets were NOT scaled up
- ❌ No new nodes appeared in the cluster
- ❌ Pods remained scaled to 0

### Root Causes Identified

1. **Insufficient Logging**
   - No detailed logging to track workflow execution
   - Exceptions were being caught but not logged with full tracebacks
   - Could not diagnose where the workflow was failing

2. **Missing Error Handling**
   - NodeGroup existence was not verified before scaling
   - If NodeGroup didn't exist, the workflow would fail silently
   - No validation of EKS_CLUSTER_NAME environment variable

3. **Async Invocation Issues**
   - No logging when async invocation was triggered
   - No verification that async invocation succeeded
   - Errors in async execution were not visible

4. **Missing Validation**
   - No check if NodeGroup exists before attempting to scale
   - No validation that EKS_CLUSTER_NAME is set
   - No verification that Kubernetes client initialized correctly

## ✅ Fixes Implemented

### 1. Comprehensive Logging Added

**Lambda Handler:**
- Added detailed event logging at start of handler
- Added EKS_CLUSTER_NAME validation with clear error messages
- Added full traceback printing for all exceptions
- Added step-by-step logging for async invocations

**Start Workflow:**
- Added detailed logging for each step (1-5)
- Added logging for NodeGroup existence verification
- Added logging for current vs target NodeGroup sizes
- Added logging for Kubernetes workload scaling operations
- Added pod status checks after scaling

### 2. Enhanced Error Handling

**NodeGroup Scaling (STEP 3):**
- Verify NodeGroup exists before attempting to scale
- Handle `ResourceNotFoundException` gracefully (skip with warning)
- Check if scaling is needed before making API call
- Log current vs target configuration
- Full traceback for all exceptions

**NodeGroup Wait (STEP 4):**
- Only wait if NodeGroup scaling was successful
- Handle different NodeGroup states (UPDATING, CREATING, DEGRADED, etc.)
- Better timeout handling with warnings instead of errors
- Skip if NodeGroup scaling was skipped

**Kubernetes Scaling (STEP 5):**
- Verify Kubernetes client is initialized
- List and log all Deployments and StatefulSets found
- Skip scaling if already at target replicas
- Collect and report all scaling errors
- Check pod status after scaling

### 3. Async Invocation Improvements

**Before Invocation:**
- Log function name, app name, and payload
- Validate all required parameters

**After Invocation:**
- Log response status code
- Log response metadata
- Handle invocation failures with proper error responses

**In Async Handler:**
- Full traceback printing for all exceptions
- Detailed logging of operation start and completion
- Log success status and any errors

### 4. Validation & Safety Checks

**Environment Variables:**
- Validate EKS_CLUSTER_NAME is set at handler start
- Return error immediately if missing

**NodeGroup Validation:**
- Check if NodeGroup exists before scaling
- Compare current vs target configuration
- Skip scaling if already at target

**Kubernetes Client:**
- Verify client initialization
- Provide helpful error messages if initialization fails

## 📋 Code Changes Summary

### File: `lambdas/controller/lambda_function.py`

1. **`lambda_handler()` function:**
   - Added comprehensive event logging
   - Added EKS_CLUSTER_NAME validation
   - Enhanced async invocation logging
   - Full traceback for exceptions

2. **`start_application()` function - STEP 3:**
   - Added NodeGroup existence verification
   - Added current vs target configuration comparison
   - Enhanced error handling with ClientError detection
   - Better logging for all operations

3. **`start_application()` function - STEP 4:**
   - Only execute if NodeGroup scaling was successful
   - Better state handling (UPDATING, CREATING, DEGRADED, etc.)
   - Enhanced logging with elapsed time and node counts
   - Warnings instead of errors for timeouts

4. **`start_application()` function - STEP 5:**
   - Enhanced Kubernetes client validation
   - Detailed logging for Deployments and StatefulSets
   - Skip scaling if already at target
   - Pod status checking after scaling
   - Better error collection and reporting

## 🧪 Testing

### Test Script Created
**File:** `scripts/test-start-workflow.sh`

The test script validates:
- ✅ EC2 database instance states
- ✅ NodeGroup configuration and existence
- ✅ Kubernetes workloads (Deployments, StatefulSets, Pods)

**Usage:**
```bash
./scripts/test-start-workflow.sh <app-name>
```

**Example:**
```bash
./scripts/test-start-workflow.sh mi-r1.dev.mareana.com
```

### Monitoring

**CloudWatch Logs:**
```bash
# Follow Controller Lambda logs in real-time
aws logs tail /aws/lambda/eks-app-controller-controller --follow
```

**What to Look For:**
- `🚀 CONTROLLER LAMBDA INVOKED` - Handler started
- `🔄 ASYNC INVOCATION DETECTED` - Async workflow started
- `STEP 3: SCALING NODEGROUP(S)` - NodeGroup scaling
- `STEP 4: WAITING FOR NODEGROUP` - NodeGroup wait
- `STEP 5: SCALING DEPLOYMENTS` - Kubernetes scaling
- `✅ SUCCESS` or `⚠️ COMPLETED WITH ERRORS` - Final status

## 🚀 Deployment

1. **Build Lambda:**
   ```bash
   ./build-lambdas.sh
   ```

2. **Deploy Lambda:**
   ```bash
   cd infrastructure
   terragrunt apply -auto-approve -target=aws_lambda_function.controller
   ```

3. **Verify Deployment:**
   - Check CloudWatch logs for new invocations
   - Test start workflow from dashboard
   - Monitor logs for detailed execution flow

## 📊 Expected Behavior After Fix

When clicking "Start Application":

1. ✅ **STEP 1-2:** Postgres/Neo4j EC2 starts (already working)
2. ✅ **STEP 3:** NodeGroup scales from 0 → desired_default
   - Verifies NodeGroup exists
   - Compares current vs target
   - Scales only if needed
   - Logs all operations
3. ✅ **STEP 4:** Waits for NodeGroup to be ACTIVE
   - Only if STEP 3 succeeded
   - Polls every 15 seconds
   - Logs status updates
   - Times out after 10 minutes with warning
4. ✅ **STEP 5:** Deployments & StatefulSets scale up
   - Lists all workloads
   - Scales to max(1, current_replicas)
   - Logs each operation
   - Checks pod status
5. ✅ **Result:** Application returns HTTP 200, dashboard shows all components 🟢

## 🔧 IAM Permissions

All required permissions are already in place:
- ✅ `eks:UpdateNodegroupConfig` - Scale NodeGroups
- ✅ `eks:DescribeNodegroup` - Check NodeGroup status
- ✅ `lambda:InvokeFunction` - Async self-invocation
- ✅ Kubernetes RBAC - Scale workloads (via k8s-rbac/controller-lambda-rbac.yaml)

## 📝 Next Steps

1. **Deploy the fix:**
   ```bash
   cd infrastructure && terragrunt apply -auto-approve -target=aws_lambda_function.controller
   ```

2. **Test the workflow:**
   - Use the test script: `./scripts/test-start-workflow.sh <app-name>`
   - Start an application from the dashboard
   - Monitor CloudWatch logs

3. **Verify results:**
   - Check NodeGroup scales correctly
   - Verify nodes appear in cluster
   - Confirm pods are running
   - Check application HTTP status

## 🐛 Troubleshooting

If issues persist:

1. **Check CloudWatch Logs:**
   ```bash
   aws logs tail /aws/lambda/eks-app-controller-controller --follow
   ```

2. **Verify Environment Variables:**
   - `EKS_CLUSTER_NAME` must be set
   - Check Lambda environment configuration

3. **Check IAM Permissions:**
   - Verify Controller Lambda role has all required permissions
   - Check Kubernetes RBAC is applied

4. **Verify NodeGroup Exists:**
   ```bash
   aws eks describe-nodegroup --cluster-name <cluster> --nodegroup-name <nodegroup>
   ```

5. **Test Kubernetes Access:**
   ```bash
   kubectl get nodes
   kubectl get deployments -n <namespace>
   ```

