# Shared Database Lock Implementation

## Overview

This document describes the implementation of distributed locking for shared database stop operations to prevent race conditions and ensure databases are only stopped when all dependent applications are DOWN.

## Architecture

### 1. Distributed Lock Mechanism

**DynamoDB Single-Table Design:**
- Uses existing `app_registry` table with composite key pattern
- Lock items use PK: `LOCK#DB#<db_identifier>`
- TTL enabled for automatic lock expiration (60 seconds)
- Lock attributes:
  - `app_name`: `LOCK#DB#<db_identifier>` (PK)
  - `owner_id`: UUID of the lock owner
  - `ttl`: Epoch seconds for expiration
  - `created_at`: Timestamp
  - `lock_type`: "database"
  - `db_identifier`: EC2 instance ID or host:port

### 2. Lock Acquisition Flow

```
1. Controller generates unique owner_id (UUID)
2. Attempts atomic PutItem with ConditionExpression:
   - Lock doesn't exist OR lock has expired (ttl < now)
3. If successful → lock acquired
4. If ConditionalCheckFailedException → retry with exponential backoff + jitter
5. Max 3 retries, then fail-safe (skip DB stop)
```

### 3. Database Stop Workflow

```
For each database (Postgres/Neo4j):
  1. Determine db_identifier (prefer EC2 instance ID, fallback to host:port)
  2. Check if database is shared
     - If dedicated → stop immediately (no lock needed)
     - If shared → proceed with lock mechanism
  3. Acquire distributed lock
  4. Query registry for all sharing applications
  5. Remove current app from sharing list
  6. For each sharing app:
     - Call quick-status endpoint (3s timeout)
     - Collect status: UP, DOWN, or UNKNOWN
  7. Decision logic:
     - If ANY app is UP → skip stop, release lock
     - If ANY app is UNKNOWN → treat as UP (fail-safe), skip stop
     - If ALL apps are DOWN → proceed to stop DB
  8. Release lock (only if owner_id matches)
```

### 4. Quick-Status Endpoint

**Endpoint**: `GET /status/quick?app=<app_name>`

**Response**:
```json
{
  "app": "app_name",
  "status": "UP" | "DOWN" | "UNKNOWN",
  "http_code": 200 | null,
  "timestamp": "2025-11-28T18:00:00Z"
}
```

**Behavior**:
- Performs HTTP HEAD request to app hostname
- 3 second timeout
- Returns UNKNOWN on timeout/errors (fail-safe)
- Only HTTP 200 = UP, everything else = DOWN

### 5. Safety Rules

1. **UNKNOWN = UP**: If status check returns UNKNOWN (timeout, error), treat as UP and do NOT stop database
2. **Lock timeout**: 60 seconds TTL ensures locks don't persist indefinitely
3. **Fail-safe on lock failure**: If lock cannot be acquired, skip DB stop rather than risk concurrent operations
4. **Owner verification**: Only release lock if owner_id matches (prevents releasing someone else's lock)

## Implementation Details

### Controller Lambda Changes

**New Functions:**
- `acquire_db_lock(db_identifier, owner_id, ttl_seconds, max_retries)`
- `release_db_lock(lock_key, owner_id)`
- `check_app_quick_status(app_name, api_base_url, timeout)`
- `stop_database_with_lock(db_host, db_type, app_name, results, api_base_url)`

**Modified Functions:**
- `stop_application()` - Now uses `stop_database_with_lock()` for both Postgres and Neo4j

### API Handler Lambda Changes

**New Endpoint:**
- `GET /status/quick?app=<app_name>` - Lightweight status check for Controller

### Infrastructure Changes

**DynamoDB Table:**
- Added TTL attribute for automatic lock expiration
- No schema changes needed (uses existing table with different PK pattern)

**IAM Permissions:**
- Controller Lambda: Added `PutItem`, `DeleteItem`, `Scan` permissions for lock operations

**API Gateway:**
- Added route: `GET /status/quick` → API Handler Lambda

## Concurrency Handling

### Scenario 1: Concurrent Stop Requests

**Example**: Two apps (A and B) sharing DB, both stopped simultaneously

1. Request 1 (stop A) acquires lock
2. Request 2 (stop B) waits for lock (retries)
3. Request 1 checks sharing apps → B is still UP → skips DB stop → releases lock
4. Request 2 acquires lock → checks sharing apps → A is DOWN → skips DB stop (A already stopped)
5. Result: DB remains running (correct)

### Scenario 2: Sequential Stops

**Example**: Stop A, then stop B (last app)

1. Stop A: Acquires lock → checks B (UP) → skips DB stop
2. Stop B: Acquires lock → checks A (DOWN) → stops DB
3. Result: DB stopped only when last app is stopped (correct)

### Scenario 3: Lock Contention

**Example**: Multiple requests try to stop different apps sharing same DB

- First request acquires lock
- Other requests retry with exponential backoff
- If lock not acquired after 3 retries → fail-safe (skip DB stop)
- TTL ensures lock expires if process crashes

## Testing

### Unit Tests Needed

1. `acquire_db_lock()` - Test lock acquisition, retry logic, TTL handling
2. `release_db_lock()` - Test owner verification, error handling
3. `check_app_quick_status()` - Test UP/DOWN/UNKNOWN responses
4. `stop_database_with_lock()` - Test full workflow with mocks

### Integration Tests

1. **Concurrent stops**: Simulate 2+ simultaneous stop requests
2. **Sequential stops**: Stop apps one by one, verify DB stops only when last app stops
3. **Lock timeout**: Verify locks expire after TTL
4. **UNKNOWN handling**: Verify UNKNOWN status prevents DB stop

### E2E Test Script

```bash
# Test scenario: 3 apps sharing DB
# 1. All UP → stop app A → DB should NOT stop
# 2. Stop app B → DB should NOT stop (A still UP)
# 3. Stop app C → DB should stop (all apps down)
```

## Configuration

### Environment Variables

- `API_GATEWAY_URL`: Base URL for API Gateway (required for quick-status checks)
- `SHARED_DB_LOCK_ENABLED`: Feature flag (default: true)

### Config.yaml

```yaml
controller:
  shared_db_lock_enabled: true
  lock_ttl_seconds: 60
  lock_max_retries: 3
  quick_status_timeout: 3
```

## Monitoring & Logging

### CloudWatch Logs

**Lock Operations:**
- `🔒 Lock acquired for db=<id>, owner=<uuid>`
- `⏳ Lock held by another process, retrying...`
- `❌ Lock not acquired for db=<id> after N attempts`
- `🔓 Lock released for <key>, owner=<uuid>`

**Database Stop Decisions:**
- `🔍 Processing <db_type> database: <host>`
- `🔍 <db_type> shared with N application(s): <list>`
- `⚠️ <app> is UP` / `✅ <app> is DOWN`
- `⚠️ <db_type> shared with active apps: <list>. Skipping stop.`
- `✅ All sharing applications are DOWN - stopping <db_type> database...`

### Metrics (Future)

- `db.stop.skipped_shared_active` - Counter with tag `db_identifier`
- `db.stop.skipped_lock` - Counter with tag `db_identifier`
- `db.stop.stopped` - Counter with tag `db_identifier`
- `lock.acquire.retries` - Histogram
- `lock.acquire.duration` - Histogram

## Rollout Plan

1. **Phase 1**: Deploy infrastructure changes (DynamoDB TTL, IAM permissions)
2. **Phase 2**: Deploy API Handler with quick-status endpoint
3. **Phase 3**: Deploy Controller with lock mechanism (feature flag enabled)
4. **Phase 4**: Monitor logs for 24-48 hours
5. **Phase 5**: Remove feature flag if stable

## Troubleshooting

### Lock Not Acquired

**Symptoms**: Logs show "Lock not acquired after 3 attempts"

**Causes**:
- High concurrency (multiple simultaneous stops)
- Lock held by crashed process (wait for TTL expiration)

**Solutions**:
- Increase `lock_max_retries`
- Decrease `lock_ttl_seconds` for faster expiration
- Check for stuck locks in DynamoDB

### Quick-Status Returns UNKNOWN

**Symptoms**: All apps show UNKNOWN, DB never stops

**Causes**:
- API Gateway URL not configured
- Network timeout
- API Handler Lambda errors

**Solutions**:
- Verify `API_GATEWAY_URL` environment variable
- Check API Handler Lambda logs
- Verify API Gateway route exists

### Database Stopped Prematurely

**Symptoms**: DB stopped even though other apps are UP

**Causes**:
- Quick-status endpoint returning incorrect status
- Race condition in status checks

**Solutions**:
- Verify quick-status endpoint logic
- Check timing of status checks vs app shutdown
- Review logs for status check timing

## Future Enhancements

1. **SQS Queue**: Use SQS for lock acquisition failures (better than retries)
2. **Lock Metrics**: CloudWatch metrics for lock operations
3. **Lock Dashboard**: UI showing active locks
4. **Lock Cleanup**: Lambda to clean up expired locks
5. **Distributed Tracing**: X-Ray for lock acquisition flow

