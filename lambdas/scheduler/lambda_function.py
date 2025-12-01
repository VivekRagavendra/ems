"""
Scheduler Lambda Function
Intelligent auto-scheduling with IST (Asia/Kolkata) timezone support.
Runs every 5 minutes via EventBridge to check and trigger start/stop actions.
"""

import json
import os
import boto3
import requests
from datetime import datetime, timedelta
import pytz
import re

# Import config loader
try:
    from config.loader import get_config, get_dynamodb_table_name
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from config.loader import get_config, get_dynamodb_table_name

# Load configuration
try:
    CONFIG = get_config()
    REGISTRY_TABLE_NAME = get_dynamodb_table_name()
    SCHEDULES_TABLE_NAME = os.environ.get('SCHEDULES_TABLE_NAME', 'eks-app-controller-app-schedules')
    OPERATION_LOGS_TABLE_NAME = os.environ.get('OPERATION_LOGS_TABLE_NAME', 'eks-app-controller-operation-logs')
    API_GATEWAY_URL = os.environ.get('API_GATEWAY_URL', '')
except Exception as e:
    print(f"⚠️ Warning: Could not load config: {e}")
    REGISTRY_TABLE_NAME = os.environ.get('REGISTRY_TABLE_NAME', 'eks-app-controller-registry')
    SCHEDULES_TABLE_NAME = os.environ.get('SCHEDULES_TABLE_NAME', 'eks-app-controller-app-schedules')
    OPERATION_LOGS_TABLE_NAME = os.environ.get('OPERATION_LOGS_TABLE_NAME', 'eks-app-controller-operation-logs')
    API_GATEWAY_URL = os.environ.get('API_GATEWAY_URL', '')

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ist_tz = pytz.timezone('Asia/Kolkata')

# Weekday mapping
WEEKDAY_MAP = {
    'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6
}

def validate_time_format(time_str):
    """Validate HH:MM format (24-hour)."""
    pattern = r'^([01]\d|2[0-3]):([0-5]\d)$'
    return bool(re.match(pattern, time_str))

def parse_time_ist(time_str):
    """Parse HH:MM string and return time object in IST."""
    if not validate_time_format(time_str):
        raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM (24-hour)")
    
    hour, minute = map(int, time_str.split(':'))
    return datetime.now(ist_tz).replace(hour=hour, minute=minute, second=0, microsecond=0)

def get_current_ist_time():
    """Get current time in IST timezone."""
    return datetime.now(ist_tz)

def is_weekday_included(weekdays, current_weekday):
    """Check if current weekday is in the weekdays list."""
    if not weekdays:
        return True  # If no weekdays specified, assume all days
    
    weekday_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    current_name = weekday_names[current_weekday]
    return current_name in weekdays

def get_global_schedule():
    """Get global schedule from config.yaml (applies to ALL apps)."""
    global_schedule = CONFIG.get('global_schedule', {})
    if not global_schedule:
        print("   ⚠️  No global_schedule found in config.yaml")
        return None
    
    return {
        'timezone': global_schedule.get('timezone', 'Asia/Kolkata'),
        'weekdays_start': global_schedule.get('weekdays_start', ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']),
        'weekdays_stop': global_schedule.get('weekdays_stop', ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']),
        'weekend_shutdown': global_schedule.get('weekend_shutdown', True),
        'start_time': global_schedule.get('start_time', '09:00'),
        'stop_time': global_schedule.get('stop_time', '22:00')
    }

def get_app_schedule_enabled(app_name):
    """Get only the enabled flag for app from DynamoDB (times/weekdays come from global_schedule)."""
    schedules_table = dynamodb.Table(SCHEDULES_TABLE_NAME)
    try:
        response = schedules_table.get_item(Key={'app': app_name})
        if 'Item' in response:
            schedule = response['Item']
            return schedule.get('enabled', False)
    except Exception as e:
        print(f"   ⚠️  Error reading schedule enabled flag from DB for {app_name}: {e}")
    
    # Default to enabled if not found
    return True

def check_app_status(app_name):
    """Check if app is UP or DOWN using API Handler quick-status endpoint."""
    if not API_GATEWAY_URL:
        print(f"   ⚠️  API_GATEWAY_URL not set, using DynamoDB status")
        # Fallback: check DynamoDB registry
        registry_table = dynamodb.Table(REGISTRY_TABLE_NAME)
        try:
            response = registry_table.get_item(Key={'app_name': app_name})
            if 'Item' in response:
                http_status = response['Item'].get('http', {}).get('status', 'UNKNOWN')
                return http_status == 'UP'
        except Exception as e:
            print(f"   ⚠️  Error checking status from registry: {e}")
        return True  # Fail-safe: treat UNKNOWN as UP
    
    try:
        url = f"{API_GATEWAY_URL}/status/quick?app={app_name}"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            status = data.get('status', 'UNKNOWN')
            # Treat UNKNOWN as UP (fail-safe for scheduler stop decisions)
            return status == 'UP' or status == 'UNKNOWN'
        return True  # Fail-safe
    except Exception as e:
        print(f"   ⚠️  Error calling quick-status: {e}")
        return True  # Fail-safe: treat as UP

def trigger_start(app_name):
    """Trigger start action for app."""
    if not API_GATEWAY_URL:
        print(f"   ⚠️  API_GATEWAY_URL not set, cannot trigger start")
        return False
    
    try:
        url = f"{API_GATEWAY_URL}/start"
        payload = {
            'app_name': app_name,
            'source': 'scheduler'
        }
        response = requests.post(url, json=payload, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error triggering start: {e}")
        return False

def trigger_stop(app_name):
    """Trigger stop action for app."""
    if not API_GATEWAY_URL:
        print(f"   ⚠️  API_GATEWAY_URL not set, cannot trigger stop")
        return False
    
    try:
        url = f"{API_GATEWAY_URL}/stop"
        payload = {
            'app_name': app_name,
            'source': 'scheduler'
        }
        response = requests.post(url, json=payload, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error triggering stop: {e}")
        return False

def log_operation(app_name, action, reason):
    """Log operation to operation_logs table."""
    logs_table = dynamodb.Table(OPERATION_LOGS_TABLE_NAME)
    
    try:
        timestamp = datetime.utcnow().isoformat() + 'Z'
        operation_id = f"{app_name}_{action}_{int(datetime.utcnow().timestamp())}"
        
        # TTL: 90 days from now
        ttl = int((datetime.utcnow() + timedelta(days=90)).timestamp())
        
        item = {
            'PK': operation_id,
            'SK': timestamp,
            'app': app_name,
            'action': action,
            'source': 'scheduler',
            'reason': reason,
            'timestamp': timestamp,
            'ttl': ttl
        }
        
        logs_table.put_item(Item=item)
    except Exception as e:
        print(f"   ⚠️  Error logging operation: {e}")


def get_all_apps():
    """Get all applications from registry."""
    registry_table = dynamodb.Table(REGISTRY_TABLE_NAME)
    try:
        response = registry_table.scan()
        return response.get('Items', [])
    except Exception as e:
        print(f"Error scanning registry: {str(e)}")
        return []

def lambda_handler(event, context):
    """Main Lambda handler."""
    print("="*70)
    print("⏰ SCHEDULER - Auto-Scheduling Check (Global Schedule)")
    print("="*70)
    
    current_time_ist = get_current_ist_time()
    print(f"Current IST time: {current_time_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    try:
        # Load global schedule (applies to ALL apps)
        global_schedule = get_global_schedule()
        if not global_schedule:
            print("❌ No global_schedule found in config.yaml. Scheduler cannot proceed.")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Global schedule not configured'
                })
            }
        
        print(f"📅 Global Schedule:")
        print(f"   Start Time: {global_schedule['start_time']} IST")
        print(f"   Stop Time: {global_schedule['stop_time']} IST")
        print(f"   Weekdays (Start): {', '.join(global_schedule['weekdays_start'])}")
        print(f"   Weekdays (Stop): {', '.join(global_schedule['weekdays_stop'])}")
        print(f"   Weekend Shutdown: {global_schedule['weekend_shutdown']}")
        
        apps = get_all_apps()
        print(f"Found {len(apps)} applications")
        
        actions_triggered = 0
        
        for app_data in apps:
            app_name = app_data.get('app_name') or app_data.get('name') or 'unknown'
            
            try:
                # Get only the enabled flag for this app
                enabled = get_app_schedule_enabled(app_name)
                
                if not enabled:
                    print(f"   ⏭️  {app_name}: Auto-scheduling disabled, skipping")
                    continue
                
                # Check app status before deciding action
                is_up = check_app_status(app_name)
                
                action, reason = should_trigger_action(app_name, global_schedule, enabled, current_time_ist)
                
                if action:
                    # Only trigger if state change is needed
                    if action == 'start' and not is_up:
                        print(f"\n🔄 {app_name}: Triggering {action.upper()} - {reason}")
                        success = trigger_start(app_name)
                        if success:
                            log_operation(app_name, action, reason)
                            actions_triggered += 1
                            print(f"   ✅ {action.upper()} triggered successfully")
                        else:
                            print(f"   ❌ Failed to trigger {action}")
                    elif action == 'stop' and is_up:
                        print(f"\n🔄 {app_name}: Triggering {action.upper()} - {reason}")
                        success = trigger_stop(app_name)
                        if success:
                            log_operation(app_name, action, reason)
                            actions_triggered += 1
                            print(f"   ✅ {action.upper()} triggered successfully")
                        else:
                            print(f"   ❌ Failed to trigger {action}")
                else:
                    # Log that schedule was checked but no action needed
                    pass
                    
            except Exception as e:
                print(f"❌ Error processing {app_name}: {e}")
                continue
        
        print(f"\n✅ Scheduler completed: {actions_triggered} action(s) triggered")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Scheduler check completed',
                'actions_triggered': actions_triggered,
                'timestamp_ist': current_time_ist.isoformat()
            })
        }
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }


