"""
Health Monitor Lambda Function
Periodically checks application health via HTTP and updates status in registry.
Measures HTTP latency and updates DynamoDB with all health metrics.
"""

import json
import os
import time
import boto3
import requests
import socket
from datetime import datetime
from botocore.exceptions import ClientError
from urllib.parse import urlparse

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ec2 = boto3.client('ec2')
eks_client = boto3.client('eks')

# DynamoDB table name
TABLE_NAME = os.environ.get('REGISTRY_TABLE_NAME', 'eks-app-registry')
EKS_CLUSTER_NAME = os.environ.get('EKS_CLUSTER_NAME')

def get_all_apps():
    """Get all applications from registry."""
    table = dynamodb.Table(TABLE_NAME)
    
    try:
        response = table.scan()
        return response.get('Items', [])
    except Exception as e:
        print(f"Error scanning registry: {str(e)}")
        return []

def check_nodegroup_health(cluster_name, nodegroup_name):
    """Check if NodeGroup has running nodes."""
    try:
        response = eks_client.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name
        )
        desired_size = response['nodegroup'].get('scalingConfig', {}).get('desiredSize', 0)
        return desired_size > 0
    except Exception as e:
        print(f"Error checking nodegroup {nodegroup_name}: {str(e)}")
        return False

def check_ec2_instance_health(instance_id):
    """Check if EC2 instance is running."""
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        if response.get('Reservations'):
            state = response['Reservations'][0]['Instances'][0]['State']['Name']
            return state == 'running'
        return False
    except Exception as e:
        print(f"Error checking instance {instance_id}: {str(e)}")
        return False

def find_ec2_instance_by_ip(ip_address):
    """
    Find EC2 instance by private IP address.
    Returns: (instance_id, state) or (None, None) if not found
    """
    if not ip_address:
        return None, None
    
    try:
        # Search for instances with matching private IP
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'private-ip-address', 'Values': [ip_address]},
                {'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'pending', 'stopping']}
            ]
        )
        
        if response.get('Reservations'):
            instance = response['Reservations'][0]['Instances'][0]
            instance_id = instance['InstanceId']
            state = instance['State']['Name']
            return instance_id, state
        
        return None, None
    except Exception as e:
        print(f"Error finding EC2 instance by IP {ip_address}: {str(e)}")
        return None, None

def evaluate_database_state(ec2_state):
    """
    Evaluate database state based ONLY on EC2 instance state.
    STRICT RULE: EC2 state is the ONLY source of truth.
    """
    if ec2_state and ec2_state.lower() == "running":
        return "running"
    return "stopped"

def check_postgres_health(host, port, db=None, user=None):
    """
    Check if PostgreSQL is accessible and running.
    Returns: ('running' | 'stopped')
    """
    if not host or not port:
        return 'stopped'
    
    try:
        # Use socket connection (pure Python, no external dependencies)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        
        if result == 0:
            print(f"  ✅ PostgreSQL: {host}:{port} is accessible")
            return 'running'
        else:
            print(f"  ❌ PostgreSQL: {host}:{port} connection refused")
            return 'stopped'
    except socket.timeout:
        print(f"  ❌ PostgreSQL: {host}:{port} connection timeout")
        return 'stopped'
    except Exception as e:
        print(f"  ❌ PostgreSQL: {host}:{port} check failed: {str(e)}")
        return 'stopped'

def check_neo4j_health(host, port):
    """
    Check if Neo4j is accessible and running.
    Returns: ('running' | 'stopped')
    """
    if not host or not port:
        return 'stopped'
    
    try:
        # Method 1: Try socket connection on bolt port
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, int(port)))
            sock.close()
            
            if result == 0:
                print(f"  ✅ Neo4j: {host}:{port} is accessible")
                return 'running'
            else:
                print(f"  ❌ Neo4j: {host}:{port} connection refused")
                return 'stopped'
        except socket.timeout:
            print(f"  ❌ Neo4j: {host}:{port} connection timeout")
            return 'stopped'
        except Exception as e:
            print(f"  ❌ Neo4j: {host}:{port} check failed: {str(e)}")
            return 'stopped'
        
        # Method 2: Try HTTP check on port 7474 (fallback if bolt port fails)
        if int(port) == 7687:  # If bolt port, try HTTP port
            try:
                http_response = requests.head(f"http://{host}:7474", timeout=2)
                if http_response.status_code in [200, 401, 403]:
                    print(f"  ✅ Neo4j: {host}:7474 is accessible (HTTP fallback)")
                    return 'running'
            except:
                pass
        
    except Exception as e:
        print(f"  ❌ Neo4j health check error: {str(e)}")
        return 'stopped'
    
    return 'stopped'

def check_http_accessibility(hostname):
    """
    Check if application is accessible via HTTP/HTTPS and measure latency.
    Uses strict evaluation: 200 = UP, everything else = DOWN
    Includes reliability fixes: timeout, redirects, HTTP fallback if HTTPS fails.
    Returns: (is_accessible, status_code, latency_ms)
    """
    if not hostname:
        print(f"  ❌ HTTP: No hostname provided")
        return False, 0, None
    
    # Try HTTPS first, then HTTP as fallback
    urls_to_try = []
    if hostname.startswith('http'):
        urls_to_try.append(hostname)
    else:
        urls_to_try.append(f"https://{hostname}")
        urls_to_try.append(f"http://{hostname}")
    
    for url in urls_to_try:
        try:
            print(f"  🌐 Testing HTTP: {url}")
            
            # Measure latency
            start_time = time.time()
            
            # Make HEAD request with redirects enabled, 5-second timeout
            response = requests.head(url, timeout=5, verify=False, allow_redirects=True)
            
            # Calculate latency in milliseconds
            latency_ms = int((time.time() - start_time) * 1000)
            
            status_code = response.status_code
            
            print(f"  📡 HTTP Response: {status_code} (latency: {latency_ms}ms)")
            
            # STRICT EVALUATION: 200 = UP, 405 (Prometheus) = UP, everything else = DOWN
            if status_code == 200 or status_code == 405:  # 405 is Prometheus case - treat as UP
                print(f"  ✅ HTTP: App is UP (HTTP {status_code}, {latency_ms}ms)")
                return True, status_code, latency_ms
            else:
                print(f"  ❌ HTTP: App is DOWN (HTTP {status_code}, {latency_ms}ms)")
                return False, status_code, latency_ms
                
        except requests.exceptions.Timeout:
            print(f"  ❌ HTTP: TIMEOUT for {url} (no response within 5 seconds)")
            # Continue to next URL if available
            if url == urls_to_try[-1]:  # Last URL
                return False, 0, 5000
            continue
        except requests.exceptions.ConnectionError as e:
            print(f"  ❌ HTTP: CONNECTION REFUSED/FAILED for {url}")
            # Continue to next URL if available
            if url == urls_to_try[-1]:  # Last URL
                return False, 0, None
            continue
        except requests.exceptions.SSLError as e:
            print(f"  ⚠️  HTTP: SSL ERROR for {url}, trying next URL...")
            # Continue to next URL (HTTP fallback)
            continue
        except Exception as e:
            print(f"  ❌ HTTP: ERROR for {url} - {type(e).__name__}: {str(e)}")
            # Continue to next URL if available
            if url == urls_to_try[-1]:  # Last URL
                return False, 0, None
            continue
    
    # All URLs failed
    print(f"  ❌ HTTP: All attempts failed for {hostname}")
    return False, 0, None

def determine_app_status(app_data):
    """
    Determine application status based SOLELY on HTTP check.
    HTTP status is the authoritative source - components are checked but don't affect final status.
    Returns: (status, http_status_code, http_latency_ms, component_states)
    """
    app_name = app_data.get('app_name', 'unknown')
    nodegroups = app_data.get('nodegroups', [])
    postgres_instances = app_data.get('postgres_instances', [])
    neo4j_instances = app_data.get('neo4j_instances', [])
    hostnames = app_data.get('hostnames', [])
    
    print(f"\n{'='*70}")
    print(f"🔍 Checking: {app_name}")
    print(f"{'='*70}")
    
    # ALWAYS perform HTTP check first (authoritative source)
    http_accessible = False
    http_status_code = 0
    http_latency_ms = None
    
    if hostnames and len(hostnames) > 0:
        primary_hostname = hostnames[0] if isinstance(hostnames[0], str) else hostnames[0].get('S', '')
        print(f"\n  🌐 Performing HTTP check (authoritative status source)...")
        http_accessible, http_status_code, http_latency_ms = check_http_accessibility(primary_hostname)
    else:
        print(f"  ⚠️  No hostnames found for HTTP check")
        http_status_code = 0
        http_latency_ms = None
    
    # Check component states (for informational purposes only - don't affect final status)
    print(f"\n  🔍 Checking Component States (EC2 state ONLY - no port checks)...")
    
    # Check Postgres - EC2 instance state is the ONLY source of truth
    postgres_state = 'stopped'
    postgres_host = app_data.get('postgres_host')
    
    if postgres_host:
        # Find EC2 instance by IP address
        instance_id, ec2_state = find_ec2_instance_by_ip(postgres_host)
        if instance_id:
            postgres_state = evaluate_database_state(ec2_state)
            print(f"    {'✅' if postgres_state == 'running' else '❌'} PostgreSQL: EC2 instance {instance_id} ({postgres_host}) is {ec2_state.upper()} → DB state: {postgres_state}")
        else:
            # If instance not found by IP, try instance IDs from registry
            if postgres_instances:
                for pid in postgres_instances:
                    instance_id = pid if isinstance(pid, str) else pid.get('instance_id') or pid.get('S', '')
                    if instance_id:
                        ec2_running = check_ec2_instance_health(instance_id)
                        ec2_state = 'running' if ec2_running else 'stopped'
                        postgres_state = evaluate_database_state(ec2_state)
                        print(f"    {'✅' if postgres_state == 'running' else '❌'} PostgreSQL: EC2 instance {instance_id} is {ec2_state.upper()} → DB state: {postgres_state}")
                        break
            else:
                print(f"    ⚠️  PostgreSQL: No EC2 instance found for IP {postgres_host}")
    else:
        print(f"    ⚠️  No PostgreSQL host configured")
    
    # Check Neo4j - EC2 instance state is the ONLY source of truth
    neo4j_state = 'stopped'
    neo4j_host = app_data.get('neo4j_host')
    
    if neo4j_host:
        # Find EC2 instance by IP address
        instance_id, ec2_state = find_ec2_instance_by_ip(neo4j_host)
        if instance_id:
            neo4j_state = evaluate_database_state(ec2_state)
            print(f"    {'✅' if neo4j_state == 'running' else '❌'} Neo4j: EC2 instance {instance_id} ({neo4j_host}) is {ec2_state.upper()} → DB state: {neo4j_state}")
        else:
            # If instance not found by IP, try instance IDs from registry
            if neo4j_instances:
                for nid in neo4j_instances:
                    instance_id = nid if isinstance(nid, str) else nid.get('instance_id') or nid.get('S', '')
                    if instance_id:
                        ec2_running = check_ec2_instance_health(instance_id)
                        ec2_state = 'running' if ec2_running else 'stopped'
                        neo4j_state = evaluate_database_state(ec2_state)
                        print(f"    {'✅' if neo4j_state == 'running' else '❌'} Neo4j: EC2 instance {instance_id} is {ec2_state.upper()} → DB state: {neo4j_state}")
                        break
            else:
                print(f"    ⚠️  Neo4j: No EC2 instance found for IP {neo4j_host}")
    else:
        print(f"    ⚠️  No Neo4j host configured")
    
    # Check NodeGroups
    nodegroup_state = 'stopped'
    if nodegroups and len(nodegroups) > 0:
        for ng in nodegroups:
            ng_name = ng.get('name') if isinstance(ng, dict) else ng
            if ng_name and check_nodegroup_health(EKS_CLUSTER_NAME, ng_name):
                nodegroup_state = 'ready'
                print(f"    ✅ NodeGroup '{ng_name}' is READY")
                break
            else:
                print(f"    ❌ NodeGroup '{ng_name}' is STOPPED")
    else:
        if hostnames:
            print(f"    ⚠️  No NodeGroups mapped (might be shared/ingress-only)")
            nodegroup_state = 'unknown'
        else:
            print(f"    ❌ No NodeGroups")
            nodegroup_state = 'stopped'
    
    # STRICT STATUS DETERMINATION: HTTP status is the ONLY source of truth
    print(f"\n  📊 Status Determination (HTTP-only):")
    print(f"    HTTP Status Code: {http_status_code}")
    print(f"    HTTP Latency: {http_latency_ms}ms" if http_latency_ms else "    HTTP Latency: N/A")
    print(f"    Component States (informational): Postgres={postgres_state}, Neo4j={neo4j_state}, NodeGroups={nodegroup_state}")
    
    # STRICT EVALUATION: HTTP 200 = UP, 405 (Prometheus) = UP, everything else = DOWN
    if http_status_code == 200 or http_status_code == 405:  # 405 is Prometheus case
        final_status = 'UP'
        print(f"  ✅ FINAL STATUS: UP (HTTP {http_status_code})")
    else:
        final_status = 'DOWN'
        print(f"  ❌ FINAL STATUS: DOWN (HTTP {http_status_code} or connection failed)")
    
    component_states = {
        'postgres_state': postgres_state,
        'neo4j_state': neo4j_state,
        'nodegroup_state': nodegroup_state
    }
    
    return final_status, http_status_code, http_latency_ms, component_states

def update_app_health(app_name, status, http_status_code, http_latency_ms=None, component_states=None):
    """Update application health status, HTTP code, latency, and component states in registry."""
    table = dynamodb.Table(TABLE_NAME)
    
    try:
        update_expr = 'SET #status = :status, final_app_status = :final_status, http_status_code = :http_code, last_health_check = :timestamp'
        expr_values = {
            ':status': status,
            ':final_status': status,
            ':http_code': http_status_code,
            ':timestamp': int(time.time())
        }
        expr_names = {
            '#status': 'status'
        }
        
        # Add component states if provided (informational only)
        if component_states:
            if component_states.get('postgres_state'):
                update_expr += ', postgres_state = :postgres_state'
                expr_values[':postgres_state'] = component_states['postgres_state']
            if component_states.get('neo4j_state'):
                update_expr += ', neo4j_state = :neo4j_state'
                expr_values[':neo4j_state'] = component_states['neo4j_state']
            if component_states.get('nodegroup_state'):
                update_expr += ', nodegroup_state = :nodegroup_state'
                expr_values[':nodegroup_state'] = component_states['nodegroup_state']
        
        if http_latency_ms is not None:
            update_expr += ', http_latency_ms = :latency'
            expr_values[':latency'] = http_latency_ms
        
        table.update_item(
            Key={'app_name': app_name},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues=expr_values
        )
        return True
    except Exception as e:
        print(f"Error updating health for {app_name}: {str(e)}")
        return False

def lambda_handler(event, context):
    """Main Lambda handler."""
    print("="*70)
    print("🏥 HEALTH MONITOR - Starting health check")
    print("="*70)
    
    # Get all applications
    apps = get_all_apps()
    print(f"\n📋 Found {len(apps)} applications to check\n")
    
    results = []
    
    for app in apps:
        app_name = app.get('app_name')
        
        try:
            # Determine status, HTTP code, latency, and component states
            status, http_status_code, http_latency_ms, component_states = determine_app_status(app)
            
            # Update in registry
            update_app_health(app_name, status, http_status_code, http_latency_ms, component_states)
            
            results.append({
                'app_name': app_name,
                'status': status,
                'http_status_code': http_status_code,
                'http_latency_ms': http_latency_ms,
                'component_states': component_states
            })
            
        except Exception as e:
            print(f"❌ Error checking {app_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append({
                'app_name': app_name,
                'status': 'UNKNOWN',
                'error': str(e)
            })
    
    print("\n" + "="*70)
    print("✅ Health check completed")
    print("="*70)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Health check completed',
            'apps_checked': len(apps),
            'results': results
        })
    }
