# Shared Database Protection Implementation

## Overview

Implemented protection for shared Postgres and Neo4j databases to prevent stopping them when other applications are still running. The system now uses **live HTTP checks** instead of stale DynamoDB status to determine if sharing applications are UP.

## Problem Solved

**Before**: When stopping an application that shares a database with other apps, the controller would stop the database EC2 instance, bringing down all dependent applications.

**After**: The controller checks if ANY sharing application is UP using live HTTP checks. Databases are only stopped when ALL sharing applications are DOWN.

## Implementation Details

### 1. Controller Lambda (`lambdas/controller/lambda_function.py`)

#### New Helper Functions

**`get_sharing_applications(resource_host, resource_type, current_app_name)`**
- Scans DynamoDB to find all applications using the same database IP
- Returns list of app names that share the database
- Handles both Postgres and Neo4j independently

**`check_app_status_live(app_name)`**
- Performs live HTTP HEAD request to application hostname
- Tries HTTPS first, then HTTP fallback
- Returns `True` only if HTTP 200 response (strict rule)
- Conservative: assumes UP if check fails (prevents accidental DB stop)

**`are_any_apps_running(app_list)`**
- Checks if ANY application in the list is currently UP
- Uses `check_app_status_live()` for each app
- Returns `True` if any app is UP, `False` if all are DOWN

**Updated `is_shared_resource_in_use()`**
- Now uses live HTTP checks instead of stale DynamoDB status
- Calls `get_sharing_applications()` to find sharing apps
- Calls `are_any_apps_running()` to check if any are UP
- Returns `True` if database is in use, `False` if safe to stop

#### Updated Stop Workflow

The `stop_application()` function now:

1. **Stops NodeGroups and Pods** (unchanged)
2. **Before stopping Postgres**:
   - Checks if Postgres is shared
   - If shared, finds all sharing applications
   - Performs live HTTP checks on each sharing app
   - **Only stops Postgres if ALL sharing apps are DOWN**
   - Logs warning if database is skipped due to active apps

3. **Before stopping Neo4j**:
   - Same logic as Postgres
   - Checks independently (Postgres and Neo4j can have different sharing apps)

### 2. API Handler Lambda (`lambdas/api-handler/lambda_function.py`)

#### New Endpoint

**`GET /status/{app_name}`** - Quick status check
- Returns `{"app_name": "...", "status": "UP" | "DOWN"}`
- Performs live HTTP check (HEAD request)
- Fast response for Controller Lambda to check sharing apps
- Used by Controller Lambda for real-time status checks

### 3. Discovery Lambda (`lambdas/discovery/lambda_function.py`)

#### Enhanced `check_shared_resources()`

- **Method 1**: Checks EC2 tags for `Shared=true` and `AppName` tags
- **Method 2**: Scans DynamoDB registry for apps with same database IP
- Combines both methods to find ALL sharing applications
- Stores `linked_apps` list in `shared_resources` field in DynamoDB

## How It Works

### Example Scenario

**Shared Postgres**: `10.2.129.29`  
**Sharing Apps**: `gtag.dev.mareana.com`, `vsm-bms.dev.mareana.com`, `ebr.dev.mareana.com`

#### Case 1: All Apps UP → Stop gtag.dev

1. User clicks STOP on `gtag.dev.mareana.com`
2. Controller stops gtag.dev's NodeGroup and pods
3. Controller checks Postgres `10.2.129.29`:
   - Finds sharing apps: `vsm-bms.dev`, `ebr.dev`
   - Performs live HTTP checks:
     - `vsm-bms.dev.mareana.com` → HTTP 200 → **UP** ✅
     - `ebr.dev.mareana.com` → HTTP 200 → **UP** ✅
   - **Result**: Database NOT stopped (other apps are UP)
   - Logs: "Shared PostgreSQL 10.2.129.29 is in use by active applications - SKIPPING STOP"

#### Case 2: All Apps DOWN → Stop Last App

1. `ebr.dev` and `vsm-bms.dev` are already DOWN
2. User clicks STOP on `gtag.dev.mareana.com`
3. Controller stops gtag.dev's NodeGroup and pods
4. Controller checks Postgres `10.2.129.29`:
   - Finds sharing apps: `vsm-bms.dev`, `ebr.dev`
   - Performs live HTTP checks:
     - `vsm-bms.dev.mareana.com` → Connection refused → **DOWN** ❌
     - `ebr.dev.mareana.com` → Connection refused → **DOWN** ❌
   - **Result**: All sharing apps are DOWN → Database CAN be stopped
   - Stops Postgres EC2 instance

#### Case 3: Mixed State

1. `ebr.dev` is UP, `vsm-bms.dev` is DOWN
2. User clicks STOP on `gtag.dev.mareana.com`
3. Controller checks sharing apps:
   - `ebr.dev` → **UP** ✅
   - `vsm-bms.dev` → **DOWN** ❌
   - **Result**: At least one app is UP → Database NOT stopped

## Key Features

✅ **Live HTTP Checks** - No reliance on stale DynamoDB status  
✅ **Strict Rule** - Only HTTP 200 = UP, everything else = DOWN  
✅ **Independent Checks** - Postgres and Neo4j checked separately  
✅ **Conservative Default** - If check fails, assumes UP (prevents accidental stop)  
✅ **Comprehensive Discovery** - Finds sharing apps via EC2 tags AND DynamoDB scan  
✅ **Clear Logging** - Detailed logs show which apps are checked and results  

## Testing Scenarios

### Test Case 1: Stop App with Shared DB (Other Apps UP)

```bash
# 1. Ensure all apps are UP
# 2. Stop gtag.dev.mareana.com
# Expected: gtag.dev stops, Postgres/Neo4j continue running
```

### Test Case 2: Stop Last App Using Shared DB

```bash
# 1. Stop ebr.dev and vsm-bms.dev first
# 2. Stop gtag.dev.mareana.com
# Expected: gtag.dev stops, Postgres/Neo4j also stop (all apps down)
```

### Test Case 3: Mixed State

```bash
# 1. Ensure ebr.dev is UP, vsm-bms.dev is DOWN
# 2. Stop gtag.dev.mareana.com
# Expected: gtag.dev stops, Postgres/Neo4j continue (ebr.dev still UP)
```

## Deployment

1. **Rebuild Lambda packages**:
   ```bash
   ./build-lambdas.sh
   ```

2. **Deploy updated functions**:
   ```bash
   aws lambda update-function-code \
     --function-name eks-app-controller-controller \
     --zip-file fileb://build/controller.zip \
     --region us-east-1

   aws lambda update-function-code \
     --function-name eks-app-controller-api-handler \
     --zip-file fileb://build/api-handler.zip \
     --region us-east-1

   aws lambda update-function-code \
     --function-name eks-app-controller-discovery \
     --zip-file fileb://build/discovery.zip \
     --region us-east-1
   ```

3. **Run Discovery** (to update shared resource mappings):
   ```bash
   aws lambda invoke \
     --function-name eks-app-controller-discovery \
     --region us-east-1 \
     /tmp/discovery-output.json
   ```

4. **Verify**:
   - Check CloudWatch logs for shared database checks
   - Test stopping an app with shared database
   - Verify database is not stopped when other apps are UP

## Log Messages

### When Database is Protected

```
ℹ️  PostgreSQL 10.2.129.29 is SHARED - checking if other apps are UP...
ℹ️  PostgreSQL 10.2.129.29 is shared with: ebr.dev.mareana.com, vsm-bms.dev.mareana.com
🔍 Checking live status of 2 sharing application(s)...
   ✅ ebr.dev.mareana.com is UP (HTTP 200 from https://ebr.dev.mareana.com)
⚠️  Database is in use by active applications - will NOT stop
⚠️  Shared PostgreSQL 10.2.129.29 is in use by active applications - SKIPPING STOP
```

### When Database Can Be Stopped

```
ℹ️  PostgreSQL 10.2.129.29 is SHARED - checking if other apps are UP...
ℹ️  PostgreSQL 10.2.129.29 is shared with: ebr.dev.mareana.com, vsm-bms.dev.mareana.com
🔍 Checking live status of 2 sharing application(s)...
   ❌ ebr.dev.mareana.com is DOWN (no HTTP 200 response)
   ❌ vsm-bms.dev.mareana.com is DOWN (no HTTP 200 response)
✅ All sharing applications are DOWN - safe to stop database
🔄 Shared PostgreSQL 10.2.129.29 is NOT in use - stopping EC2 instance...
✅ Stopped unused shared PostgreSQL instance
```

## Safety Guarantees

1. **Never stops database if ANY sharing app is UP** (verified by live HTTP check)
2. **Conservative on errors** - If status check fails, assumes app is UP (prevents accidental stop)
3. **Independent checks** - Postgres and Neo4j checked separately
4. **Comprehensive discovery** - Finds sharing apps via multiple methods

## Future Enhancements (Optional)

- [ ] UI warning modal when stopping app with shared database
- [ ] API endpoint to list all sharing apps for a database
- [ ] Dashboard indicator showing shared database status
- [ ] Configurable timeout for HTTP checks
- [ ] Retry logic for failed HTTP checks

