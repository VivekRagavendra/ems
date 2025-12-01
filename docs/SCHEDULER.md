# Auto-Scheduler Documentation

## Overview

The Auto-Scheduler feature enables automatic start/stop of applications based on a **single global schedule** defined in `config.yaml`. All schedule times are interpreted in **IST (Asia/Kolkata)** timezone. Schedule times and weekdays are centrally managed and cannot be edited via UI or API.

## Architecture

### Components

1. **Scheduler Lambda** (`lambdas/scheduler/lambda_function.py`)
   - Runs every 5 minutes via EventBridge
   - Uses **global schedule** from `config.yaml` (applies to ALL apps)
   - Checks all applications for scheduled actions
   - Triggers start/stop via API Gateway endpoints

2. **DynamoDB Table: `app_schedules`**
   - PK: `app_name`
   - Stores: `enabled` flag only (times/weekdays come from global_schedule)
   - Per-app enable/disable toggle

3. **API Endpoints**:
   - `GET /apps/{app}/schedule` - Get global schedule + enabled flag (read-only)
   - `POST /apps/{app}/schedule` - **DISABLED** (returns HTTP 400)
   - `POST /apps/{app}/schedule/enable` - Toggle enabled state (only this works)

4. **UI Component**: Schedule panel
   - **Read-only display** of global schedule times and weekdays
   - Enable/disable toggle (only editable field)

## Global Schedule Configuration

### Format

The global schedule is defined in `config/config.yaml`:

```yaml
global_schedule:
  timezone: "Asia/Kolkata"
  weekdays_start: ["Mon", "Tue", "Wed", "Thu", "Fri"]  # Days when apps start
  weekdays_stop: ["Mon", "Tue", "Wed", "Thu", "Fri"]    # Days when apps stop
  weekend_shutdown: true  # If true, apps are stopped on Sat/Sun
  start_time: "09:00"  # Start time in IST (HH:MM format)
  stop_time: "22:00"   # Stop time in IST (HH:MM format)
```

### Default Schedule

- **Monday-Friday**: Start at 09:00 IST, Stop at 22:00 IST
- **Saturday-Sunday**: Apps are automatically stopped (weekend shutdown enforced)

### Per-App Configuration

- **Enabled Flag**: Each app can have scheduling enabled/disabled via DynamoDB
- **Times/Weekdays**: Cannot be changed per-app (uses global schedule)

## Schedule Logic

### Decision Rules

1. **Start Action**: Triggered when:
   - Current IST time is within 5-minute window after scheduled ON time
   - App is currently DOWN
   - Today's weekday is in the `weekdays` array
   - `enabled` is `true`

2. **Stop Action**: Triggered when:
   - Current IST time is within 5-minute window after scheduled OFF time
   - App is currently UP (or UNKNOWN - fail-safe)
   - Today's weekday is in the `weekdays` array
   - `enabled` is `true`

### Timezone Handling

- All schedule times are stored and interpreted in **IST (Asia/Kolkata)**
- Scheduler converts current UTC time to IST for comparisons
- UI displays times with "IST (Asia/Kolkata)" label

### Status Checks

- Uses API Handler `/status/quick` endpoint for app status
- Treats `UNKNOWN` as `UP` (fail-safe for stop decisions)
- Falls back to DynamoDB registry status if API unavailable

## API Usage

### Get Schedule

```bash
GET /apps/{app_name}/schedule

Response:
{
  "app": "mi.dev.mareana.com",
  "enabled": true,
  "on": "09:00",
  "off": "18:00",
  "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri"],
  "source": "database"  # or "config" or "none"
}
```

### Update Schedule

```bash
POST /apps/{app_name}/schedule
Content-Type: application/json

{
  "enabled": true,
  "on": "09:00",
  "off": "18:00",
  "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri"]
}

Response: 200 OK with saved schedule object
```

### Toggle Enabled

```bash
POST /apps/{app_name}/schedule/enable

Response:
{
  "app": "mi.dev.mareana.com",
  "enabled": true
}
```

## Validation Rules

1. **Time Format**: Must match `^([01]\d|2[0-3]):([0-5]\d)$` (HH:MM, 24-hour)
2. **On/Off Times**: Cannot be identical
3. **Weekdays**: Must be subset of `["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]`
4. **At Least One Weekday**: Recommended when enabling schedule

## UI Usage

### Schedule Panel

1. **Enable/Disable Toggle**: Quick toggle to enable/disable scheduling
2. **Start Time**: Time picker for scheduled start (IST)
3. **Stop Time**: Time picker for scheduled stop (IST)
4. **Weekdays**: Checkboxes for each weekday
5. **Save Button**: Saves schedule to DynamoDB

### Visual Indicators

- **Warning Badge**: Shows when scheduling is disabled
- **Success Message**: Confirms when schedule is saved
- **Error Message**: Displays validation or API errors

## Operation Logs

All scheduler actions are logged to `operation_logs` DynamoDB table:

```json
{
  "PK": "app_name_action_timestamp",
  "SK": "2024-01-15T09:02:00Z",
  "app": "mi.dev.mareana.com",
  "action": "start",
  "source": "scheduler",
  "reason": "Scheduled ON time 09:00 IST reached",
  "timestamp": "2024-01-15T09:02:00Z",
  "ttl": 1736899200  # 90 days from now
}
```

## Troubleshooting

### Schedule Not Triggering

1. **Check Enabled Flag**: Verify `enabled: true` in schedule
2. **Verify Timezone**: Ensure times are in IST (not UTC)
3. **Check Weekdays**: Verify today's weekday is in the array
4. **App Status**: Check if app is already in desired state
5. **Scheduler Logs**: Check CloudWatch logs for scheduler Lambda

### Timezone Issues

- All times must be in IST (Asia/Kolkata)
- UI displays "All times shown in IST (Asia/Kolkata)"
- Scheduler automatically converts UTC to IST

### API Errors

- Verify API Gateway URL is set in scheduler Lambda environment
- Check IAM permissions for scheduler to invoke API Gateway
- Verify API Gateway routes are configured correctly

## Best Practices

1. **Test Schedules**: Start with a test app to verify scheduling works
2. **Monitor Logs**: Check operation_logs for scheduled actions
3. **Gradual Rollout**: Enable scheduling for a few apps first
4. **Weekday Selection**: Be careful with weekday selection to avoid unintended stops
5. **Time Windows**: Use 5-minute windows to account for EventBridge timing

## Future Enhancements

1. **Holiday Calendar**: Skip scheduling on holidays
2. **Multiple Schedules**: Support multiple on/off times per day
3. **Time Zone Selection**: Allow per-app timezone selection
4. **Schedule Templates**: Pre-configured schedule templates
5. **Notification Integration**: Notify on scheduled actions


