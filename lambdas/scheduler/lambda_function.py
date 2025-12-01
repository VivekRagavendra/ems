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

def get_app_schedule(app_name):
    """Get schedule for app from DynamoDB override or config.yaml default."""
    # First check DynamoDB override
    schedules_table = dynamodb.Table(SCHEDULES_TABLE_NAME)
    try:
        response = schedules_table.get_item(Key={'app': app_name})
        if 'Item' in response:
            schedule = response['Item']
            return {
                'enabled': schedule.get('enabled', False),
                'on': schedule.get('on'),
                'off': schedule.get('off'),
                'weekdays': schedule.get('weekdays', [])
            }
    except Exception as e:
        print(f"   ⚠️  Error reading schedule from DB for {app_name}: {e}")
    
    # Fallback to config.yaml
    apps_config = CONFIG.get('apps', {})
    if app_name in apps_config:
        schedule = apps_config[app_name].get('schedule', {})
        return {
            'enabled': schedule.get('enabled', False),
            'on': schedule.get('on'),
            'off': schedule.get('off'),
            'weekdays': schedule.get('weekdays', [])
        }
    
    return None

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

def should_trigger_action(app_name, schedule, current_time_ist):
    """Determine if start/stop action should be triggered."""
    if not schedule or not schedule.get('enabled'):
        return None, None
    
    on_time_str = schedule.get('on')
    off_time_str = schedule.get('off')
    weekdays = schedule.get('weekdays', [])
    
    if not on_time_str or not off_time_str:
        return None, None
    
    # Check if today is included in weekdays
    current_weekday = current_time_ist.weekday()
    if not is_weekday_included(weekdays, current_weekday):
        return None, None
    
    try:
        on_time = parse_time_ist(on_time_str)
        off_time = parse_time_ist(off_time_str)
        
        # Create datetime objects for today with the scheduled times
        on_datetime = current_time_ist.replace(hour=on_time.hour, minute=on_time.minute, second=0, microsecond=0)
        off_datetime = current_time_ist.replace(hour=off_time.hour, minute=off_time.minute, second=0, microsecond=0)
        
        # Check if we're in the 5-minute window after ON time
        on_window_start = on_datetime
        on_window_end = on_datetime + timedelta(minutes=5)
        
        # Check if we're in the 5-minute window after OFF time
        off_window_start = off_datetime
        off_window_end = off_datetime + timedelta(minutes=5)
        
        # Check app status
        is_up = check_app_status(app_name)
        
        # Decision logic
        if on_window_start <= current_time_ist < on_window_end and not is_up:
            return 'start', f"Scheduled ON time {on_time_str} IST reached"
        
        if off_window_start <= current_time_ist < off_window_end and is_up:
            return 'stop', f"Scheduled OFF time {off_time_str} IST reached"
        
        return None, None
        
    except Exception as e:
        print(f"   ❌ Error parsing schedule times: {e}")
        return None, None

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
    print("⏰ SCHEDULER - Auto-Scheduling Check")
    print("="*70)
    
    current_time_ist = get_current_ist_time()
    print(f"Current IST time: {current_time_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    try:
        apps = get_all_apps()
        print(f"Found {len(apps)} applications")
        
        actions_triggered = 0
        
        for app_data in apps:
            app_name = app_data.get('app_name') or app_data.get('name') or 'unknown'
            
            try:
                schedule = get_app_schedule(app_name)
                
                if not schedule:
                    continue
                
                action, reason = should_trigger_action(app_name, schedule, current_time_ist)
                
                if action:
                    print(f"\n🔄 {app_name}: Triggering {action.upper()} - {reason}")
                    
                    success = False
                    if action == 'start':
                        success = trigger_start(app_name)
                    elif action == 'stop':
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
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }


