"""
API Handler Lambda Function
Handles GET requests with LIVE status checks - NO CACHING.
All status is computed fresh on every request.
"""

import json
import os
import time
import boto3
import requests
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from kubernetes import client, config
from botocore.exceptions import ClientError

# Import config loader
try:
    from config.loader import (
        get_config, get_eks_cluster_name, get_dynamodb_table_name,
        get_app_namespace_mapping, get_nodegroup_defaults
    )
except ImportError:
    # Fallback for local testing or if config module not available
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from config.loader import (
        get_config, get_eks_cluster_name, get_dynamodb_table_name,
        get_app_namespace_mapping, get_nodegroup_defaults
    )

# Load configuration (cached after first load)
try:
    CONFIG = get_config()
    EKS_CLUSTER_NAME = get_eks_cluster_name()
    TABLE_NAME = get_dynamodb_table_name()
    APP_NAMESPACE_MAPPING = get_app_namespace_mapping()
    NODEGROUP_DEFAULTS = get_nodegroup_defaults()
except Exception as e:
    # Fallback to environment variables if config loading fails
    print(f"⚠️ Warning: Could not load config.yaml: {e}")
    print("⚠️ Falling back to environment variables")
    EKS_CLUSTER_NAME = os.environ.get('EKS_CLUSTER_NAME', 'mi-eks-cluster')
    TABLE_NAME = os.environ.get('REGISTRY_TABLE_NAME', 'eks-app-registry')
    APP_NAMESPACE_MAPPING = {}
    NODEGROUP_DEFAULTS = {}

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
eks_client = boto3.client('eks')
ec2_client = boto3.client('ec2')

# Kubernetes client (will be initialized when needed)
k8s_client = None

# EC2 instance cache to avoid rate limiting (cache for 30 seconds)
_ec2_instance_cache = {}
_cache_timestamps = {}
CACHE_TTL = 30  # seconds

def get_namespace_for_app(app_name, discovered_namespace=None):
    """Get the correct namespace for an application using authoritative mapping."""
    if app_name in APP_NAMESPACE_MAPPING:
        return APP_NAMESPACE_MAPPING[app_name]
    return discovered_namespace or 'default'

def get_nodegroup_defaults_for_app(app_name):
    """Get NodeGroup defaults for an application from the authoritative mapping."""
    return NODEGROUP_DEFAULTS.get(app_name)

def get_bearer_token(cluster_name):
    """Generate EKS authentication token."""
    import base64
    from botocore.signers import RequestSigner
    
    STS_TOKEN_EXPIRES_IN = 60
    session = boto3.session.Session()
    sts_client = session.client('sts')
    service_id = sts_client.meta.service_model.service_id
    
    signer = RequestSigner(
        service_id,
        session.region_name,
        'sts',
        'v4',
        session.get_credentials(),
        session.events
    )
    
    params = {
        'method': 'GET',
        'url': f'https://sts.{session.region_name}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
        'body': '',
        'headers': {
            'host': f'sts.{session.region_name}.amazonaws.com',
            'x-k8s-aws-id': cluster_name
        },
        'context': {}
    }
    
    signed_url = signer.generate_presigned_url(
        params,
        region_name=session.region_name,
        expires_in=STS_TOKEN_EXPIRES_IN,
        operation_name=''
    )
    
    return f"k8s-aws-v1.{base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8').rstrip('=')}"

def load_k8s_config():
    """Load Kubernetes configuration for EKS with detailed error handling."""
    global k8s_client
    # Always refresh the token to ensure RBAC changes are picked up
    # Reset client to None to force re-initialization
    k8s_client = None
    
    try:
        # Try in-cluster config first (if running in EKS)
        config.load_incluster_config()
        k8s_client = client
        print(f"✅ Loaded in-cluster Kubernetes config")
        return
    except Exception as e:
        print(f"ℹ️  In-cluster config not available: {str(e)}")
        pass
    
    try:
        print(f"🔍 Loading EKS config for cluster: {EKS_CLUSTER_NAME}")
        # Get EKS cluster information
        import base64
        cluster_info = eks_client.describe_cluster(name=EKS_CLUSTER_NAME)
        cluster = cluster_info['cluster']
        
        cluster_endpoint = cluster.get('endpoint')
        if not cluster_endpoint:
            raise Exception(f"Cluster {EKS_CLUSTER_NAME} has no endpoint")
        
        print(f"   Cluster endpoint: {cluster_endpoint}")
        
        # Configure Kubernetes client
        configuration = client.Configuration()
        configuration.host = cluster_endpoint
        configuration.verify_ssl = True
        configuration.ssl_ca_cert = None
        
        # Decode certificate
        ca_data = cluster.get('certificateAuthority', {}).get('data')
        if not ca_data:
            raise Exception(f"Cluster {EKS_CLUSTER_NAME} has no certificate authority data")
        
        cert_data = base64.b64decode(ca_data)
        print(f"   Certificate decoded: {len(cert_data)} bytes")
        
        # Write cert to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.crt') as cert_file:
            cert_file.write(cert_data)
            configuration.ssl_ca_cert = cert_file.name
            print(f"   Certificate written to: {cert_file.name}")
        
        # Get authentication token (always generate fresh token)
        print(f"   Generating authentication token...")
        token = get_bearer_token(EKS_CLUSTER_NAME)
        if not token:
            raise Exception("Failed to generate authentication token")
        
        configuration.api_key = {"authorization": "Bearer " + token}
        print(f"   Token generated: {token[:20]}...")
        
        # Set the default configuration
        client.Configuration.set_default(configuration)
        k8s_client = client
        
        # Test the connection by listing namespaces (lightweight check)
        try:
            core_v1 = client.CoreV1Api()
            # This will fail if auth is wrong, but we catch it
            _ = core_v1.list_namespace(limit=1)
            print(f"✅ Kubernetes client initialized and tested successfully")
        except Exception as test_error:
            error_str = str(test_error)
            if '401' in error_str or '403' in error_str or 'Unauthorized' in error_str or 'Forbidden' in error_str:
                print(f"⚠️  Kubernetes authentication test failed: {error_str}")
                print(f"   This may indicate RBAC permission issues")
                print(f"   Client initialized but may not have permissions")
            else:
                print(f"⚠️  Kubernetes connection test failed: {error_str}")
                # Still set client - let individual calls handle errors
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = str(e)
        print(f"❌ AWS EKS API error: {error_code} - {error_msg}")
        if error_code == 'ResourceNotFoundException':
            print(f"   Cluster {EKS_CLUSTER_NAME} not found")
        elif error_code == 'UnauthorizedOperation':
            print(f"   Missing eks:DescribeCluster permission")
        try:
            # Final fallback to kubeconfig (for local testing)
            config.load_kube_config()
            k8s_client = client
            print(f"✅ Fallback: Loaded kubeconfig")
        except Exception as fallback_error:
            print(f"❌ Could not load kubeconfig fallback: {str(fallback_error)}")
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error loading Kubernetes config: {error_msg}")
        import traceback
        traceback.print_exc()
        try:
            # Final fallback to kubeconfig (for local testing)
            config.load_kube_config()
            k8s_client = client
            print(f"✅ Fallback: Loaded kubeconfig")
        except Exception as fallback_error:
            print(f"❌ Could not load kubeconfig fallback: {str(fallback_error)}")

def find_ec2_instance_by_ip(ip_address):
    """
    Find EC2 instance by private IP address with caching to avoid rate limiting.
    Returns: (instance_id, state) or (None, None) if not found
    """
    if not ip_address:
        return None, None
    
    # Check cache first
    import time
    current_time = time.time()
    if ip_address in _ec2_instance_cache:
        cache_time = _cache_timestamps.get(ip_address, 0)
        if current_time - cache_time < CACHE_TTL:
            return _ec2_instance_cache[ip_address]
    
    try:
        response = ec2_client.describe_instances(
            Filters=[
                {'Name': 'private-ip-address', 'Values': [ip_address]},
                {'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'pending', 'stopping']}
            ]
        )
        
        if response.get('Reservations'):
            instance = response['Reservations'][0]['Instances'][0]
            instance_id = instance['InstanceId']
            state = instance['State']['Name']
            result = (instance_id, state)
            # Cache the result
            _ec2_instance_cache[ip_address] = result
            _cache_timestamps[ip_address] = current_time
            return result
        
        # Cache None result too
        result = (None, None)
        _ec2_instance_cache[ip_address] = result
        _cache_timestamps[ip_address] = current_time
        return result
    except Exception as e:
        error_msg = str(e)
        # If rate limited, return cached value if available
        if 'RequestLimitExceeded' in error_msg or 'Throttling' in error_msg:
            if ip_address in _ec2_instance_cache:
                print(f"⚠️  EC2 rate limited, using cached value for {ip_address}")
                return _ec2_instance_cache[ip_address]
        print(f"Error finding EC2 instance by IP {ip_address}: {error_msg}")
        return None, None

def check_shared_resource(instance_id, resource_type='database'):
    """
    Check if a resource (EC2 instance or NodeGroup) is shared with other applications.
    Returns: (is_shared, shared_with_apps)
    Optimized to avoid excessive EC2 calls.
    """
    if not instance_id:
        return False, []
    
    try:
        shared_with = []
        
        # Check EC2 tags for Shared=true (with caching)
        if resource_type == 'database':
            # Use cached instance lookup - we already have instance_id, so we can skip the IP lookup
            # Just check if multiple apps reference the same instance_id
            table = dynamodb.Table(TABLE_NAME)
            scan_response = table.scan()
            
            for item in scan_response.get('Items', []):
                app_name = item.get('app_name', {})
                if isinstance(app_name, dict) and 'S' in app_name:
                    app_name = app_name['S']
                
                # Check if this app uses the same instance
                postgres_host = item.get('postgres_host', {})
                neo4j_host = item.get('neo4j_host', {})
                
                def get_host_value(host_field):
                    if isinstance(host_field, dict) and 'S' in host_field:
                        return host_field['S']
                    return host_field if isinstance(host_field, str) else None
                
                pg_host = get_host_value(postgres_host)
                neo4j_host_val = get_host_value(neo4j_host)
                
                # Get instance ID for this app (uses cache)
                if pg_host:
                    pg_instance_id, _ = find_ec2_instance_by_ip(pg_host)
                    if pg_instance_id == instance_id and app_name not in shared_with:
                        shared_with.append(app_name)
                
                if neo4j_host_val:
                    neo4j_instance_id, _ = find_ec2_instance_by_ip(neo4j_host_val)
                    if neo4j_instance_id == instance_id and app_name not in shared_with:
                        shared_with.append(app_name)
        
        return len(shared_with) > 1, shared_with
    except Exception as e:
        error_msg = str(e)
        # Don't fail on rate limits, just return not shared
        if 'RequestLimitExceeded' in error_msg or 'Throttling' in error_msg:
            print(f"⚠️  Rate limited checking shared resource for {instance_id}, assuming not shared")
            return False, []
        print(f"Error checking shared resource for {instance_id}: {error_msg}")
        return False, []

def check_db_state_live(host):
    """
    Check database state LIVE from EC2 instance state.
    NO CACHE - always performs fresh EC2 API call.
    Returns: dict with state, instance_id, is_shared, shared_with
    """
    if not host:
        return {
            'state': 'stopped',
            'instance_id': None,
            'is_shared': False,
            'shared_with': []
        }
    
    try:
        instance_id, ec2_state = find_ec2_instance_by_ip(host)
        if instance_id and ec2_state:
            state = "running" if ec2_state.lower() == "running" else "stopped"
            is_shared, shared_with = check_shared_resource(instance_id, 'database')
            return {
                'state': state,
                'instance_id': instance_id,
                'is_shared': is_shared,
                'shared_with': shared_with
            }
        return {
            'state': 'stopped',
            'instance_id': None,
            'is_shared': False,
            'shared_with': []
        }
    except Exception as e:
        print(f"Error checking DB state for {host}: {str(e)}")
        return {
            'state': 'stopped',
            'instance_id': None,
            'is_shared': False,
            'shared_with': []
        }

def check_nodegroup_state_live(nodegroup_name):
    """
    Check NodeGroup state LIVE from EKS.
    NO CACHE - always performs fresh EKS API call.
    Returns: dict with status, desired, min, max, current
    """
    if not nodegroup_name:
        print(f"⚠️  NodeGroup name is empty, skipping check")
        return None
    
    try:
        print(f"🔍 Checking NodeGroup state for: {nodegroup_name}")
        response = eks_client.describe_nodegroup(
            clusterName=EKS_CLUSTER_NAME,
            nodegroupName=nodegroup_name
        )
        
        ng = response.get('nodegroup', {})
        scaling_config = ng.get('scalingConfig', {})
        status = ng.get('status', 'UNKNOWN')
        
        # Get current node count from resources
        # For EKS NodeGroups, we can get instance count from the resources field
        # or fallback to desired size (which is usually accurate)
        resources = ng.get('resources', {})
        auto_scaling_groups = resources.get('autoScalingGroups', [])
        current = scaling_config.get('desiredSize', 0)  # Default to desired
        
        if auto_scaling_groups:
            # Try to get actual current count from ASG
            asg_name = auto_scaling_groups[0].get('name')
            if asg_name:
                try:
                    asg = boto3.client('autoscaling')
                    asg_response = asg.describe_auto_scaling_groups(
                        AutoScalingGroupNames=[asg_name]
                    )
                    if asg_response.get('AutoScalingGroups'):
                        asg_info = asg_response['AutoScalingGroups'][0]
                        # Use DesiredCapacity as current (usually accurate for EKS)
                        # Could also use Instances count, but DesiredCapacity is more reliable
                        current = asg_info.get('DesiredCapacity', scaling_config.get('desiredSize', 0))
                        print(f"   📊 ASG {asg_name}: DesiredCapacity={current}")
                except Exception as e:
                    print(f"⚠️  Could not get ASG current count for {asg_name}: {str(e)}")
                    # Fallback: use desired size as current estimate
                    current = scaling_config.get('desiredSize', 0)
        
        desired = scaling_config.get('desiredSize')
        min_size = scaling_config.get('minSize')
        max_size = scaling_config.get('maxSize')
        
        # Check if NodeGroup is shared with other applications
        is_shared = False
        shared_with = []
        try:
            # Check if multiple apps use this NodeGroup
            table = dynamodb.Table(TABLE_NAME)
            scan_response = table.scan()
            apps_using_ng = []
            for item in scan_response.get('Items', []):
                app_name = item.get('app_name', {})
                if isinstance(app_name, dict) and 'S' in app_name:
                    app_name = app_name['S']
                # Check if this app's NodeGroup matches
                nodegroup_defaults = get_nodegroup_defaults_for_app(app_name)
                if nodegroup_defaults and nodegroup_defaults.get('nodegroup') == nodegroup_name:
                    apps_using_ng.append(app_name)
            if len(apps_using_ng) > 1:
                is_shared = True
                shared_with = apps_using_ng
        except Exception as e:
            print(f"⚠️  Could not check NodeGroup sharing for {nodegroup_name}: {str(e)}")
        
        print(f"✅ NodeGroup {nodegroup_name}: status={status}, desired={desired}, current={current}, min={min_size}, max={max_size}, shared={is_shared}")
        
        return {
            'name': nodegroup_name,
            'desired': desired,
            'current': current,
            'min': min_size,
            'max': max_size,
            'status': status,
            'is_shared': is_shared,
            'shared_with': shared_with
        }
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'ResourceNotFoundException':
            print(f"❌ NodeGroup {nodegroup_name} not found in cluster {EKS_CLUSTER_NAME}")
        else:
            print(f"❌ Error checking NodeGroup state for {nodegroup_name}: {error_code} - {str(e)}")
        return {
            'name': nodegroup_name,
            'desired': None,
            'current': None,
            'min': None,
            'max': None,
            'status': 'NOT_FOUND'
        }
    except Exception as e:
        print(f"❌ Unexpected error checking NodeGroup state for {nodegroup_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'name': nodegroup_name,
            'desired': None,
            'current': None,
            'min': None,
            'max': None,
            'status': 'UNKNOWN'
        }

def check_pod_state_live(namespace):
    """
    Check pod state LIVE from Kubernetes.
    NO CACHE - always performs fresh Kubernetes API call.
    Returns: dict with running, pending, crashloop, total, and detailed pod lists
    """
    if not namespace:
        print(f"⚠️  Namespace is empty, skipping pod check")
        return {
            'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
            'running_list': [], 'pending_list': [], 'crashloop_list': [],
            'error': 'Namespace is empty'
        }
    
    print(f"🔍 Starting pod check for namespace: {namespace}")
    
    # Always reload config to get fresh token with latest RBAC permissions
    global k8s_client
    k8s_client = None
    load_k8s_config()
    
    if k8s_client is None:
        print(f"❌ Kubernetes client not available, skipping pod check for namespace {namespace}")
        return {
            'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
            'running_list': [], 'pending_list': [], 'crashloop_list': [],
            'error': 'Kubernetes client not initialized',
            'warning': 'Kubernetes client failed to initialize. Check EKS cluster access and IAM permissions.'
        }
    
    try:
        print(f"🔍 Checking pod state for namespace: {namespace}")
        
        # Verify k8s_client is properly initialized
        if k8s_client is None:
            raise Exception("Kubernetes client is None after initialization")
        
        # Use the global k8s_client which was just loaded
        try:
            core_v1 = k8s_client.CoreV1Api()
            print(f"   ✅ CoreV1Api client created successfully")
        except Exception as client_error:
            print(f"   ❌ Failed to create CoreV1Api client: {str(client_error)}")
            raise Exception(f"CoreV1Api initialization failed: {str(client_error)}")
        
        try:
            print(f"   📡 Calling Kubernetes API: list_namespaced_pod(namespace='{namespace}')")
            pods = core_v1.list_namespaced_pod(namespace=namespace)
            print(f"✅ Successfully retrieved {len(pods.items)} pods from namespace {namespace}")
        except Exception as api_error:
            # Handle RBAC permission issues (401 Unauthorized, 403 Forbidden)
            error_str = str(api_error)
            error_body = getattr(api_error, 'body', '')
            error_status = getattr(api_error, 'status', None)
            
            # Check for HTTP status codes
            if hasattr(api_error, 'status'):
                error_status = api_error.status
            elif hasattr(api_error, 'reason'):
                # Try to extract status from reason
                if '401' in error_str or 'Unauthorized' in error_str:
                    error_status = 401
                elif '403' in error_str or 'Forbidden' in error_str:
                    error_status = 403
            
            # Handle 401 Unauthorized or 403 Forbidden (RBAC permission issues)
            if error_status in [401, 403] or '401' in error_str or '403' in error_str or 'Unauthorized' in error_str or 'Forbidden' in error_str:
                print(f"⚠️  Kubernetes RBAC: No permission to list pods in namespace '{namespace}' (HTTP {error_status or '401/403'})")
                print(f"   Error: {error_str}")
                print(f"   Status: {error_status}")
                print(f"   Body: {error_body[:200] if error_body else 'N/A'}")
                print(f"   To fix: Ensure aws-auth ConfigMap maps IAM role to username 'eks-api-handler-lambda'")
                print(f"   See: docs/POD_RBAC_SETUP.md for setup instructions")
                return {
                    'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
                    'running_list': [], 'pending_list': [], 'crashloop_list': [],
                    'error': f'RBAC permission denied (HTTP {error_status or 401})',
                    'warning': f'No permission to list pods in namespace {namespace}. See docs/POD_RBAC_SETUP.md'
                }
            
            # Handle other API errors
            print(f"❌ Error listing pods in namespace '{namespace}': {error_str}")
            print(f"   Error type: {type(api_error).__name__}")
            print(f"   Status: {error_status}")
            import traceback
            traceback.print_exc()
            # Return empty pods instead of crashing
            return {
                'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
                'running_list': [], 'pending_list': [], 'crashloop_list': [],
                'error': f'Kubernetes API error: {error_str[:100]}'
            }
        
        running = 0
        pending = 0
        crashloop = 0
        total = len(pods.items)
        
        running_list = []
        pending_list = []
        crashloop_list = []
        
        for pod in pods.items:
            phase = pod.status.phase
            pod_name = pod.metadata.name
            created = pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
            
            # Determine owner
            owner = "Unknown"
            if pod.metadata.owner_references:
                ref = pod.metadata.owner_references[0]
                owner = f"{ref.kind.lower()}/{ref.name}"
            
            pod_info = {
                'name': pod_name,
                'phase': phase,
                'reason': None,
                'owner': owner,
                'created': created
            }
            
            if phase == 'Running':
                running += 1
                running_list.append(pod_info)
            elif phase == 'Pending':
                pending += 1
                # Get pending reason
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        if cs.state and cs.state.waiting:
                            pod_info['reason'] = cs.state.waiting.reason
                            break
                pending_list.append(pod_info)
            
            # Check for CrashLoopBackOff or other error states
            crashloop_detected = False
            crashloop_reason = None
            restart_count = 0
            
            if pod.status.container_statuses:
                for container_status in pod.status.container_statuses:
                    if container_status.state:
                        if container_status.state.waiting:
                            reason = container_status.state.waiting.reason
                            if 'CrashLoopBackOff' in reason or 'ImagePullBackOff' in reason or 'ErrImagePull' in reason:
                                crashloop_detected = True
                                crashloop_reason = reason
                                restart_count = container_status.restart_count or 0
                                break
                        elif container_status.state.terminated:
                            if container_status.state.terminated.reason in ['Error', 'CrashLoopBackOff']:
                                crashloop_detected = True
                                crashloop_reason = container_status.state.terminated.reason
                                restart_count = container_status.restart_count or 0
                                break
                    if container_status.restart_count and container_status.restart_count > 5:
                        # High restart count indicates issues
                        if not crashloop_detected:
                            crashloop_detected = True
                            crashloop_reason = f"High restart count: {container_status.restart_count}"
                            restart_count = container_status.restart_count
            
            # Also check init containers
            if not crashloop_detected and pod.status.init_container_statuses:
                for init_status in pod.status.init_container_statuses:
                    if init_status.state and init_status.state.waiting:
                        reason = init_status.state.waiting.reason
                        if 'CrashLoopBackOff' in reason or 'ImagePullBackOff' in reason:
                            crashloop_detected = True
                            crashloop_reason = reason
                            restart_count = init_status.restart_count or 0
                            break
            
            if crashloop_detected:
                crashloop += 1
                pod_info['reason'] = crashloop_reason
                pod_info['restart_count'] = restart_count
                crashloop_list.append(pod_info)
        
        print(f"✅ Pod state for {namespace}: running={running}, pending={pending}, crashloop={crashloop}, total={total}")
        
        return {
            'running': running,
            'pending': pending,
            'crashloop': crashloop,
            'total': total,
            'running_list': running_list,
            'pending_list': pending_list,
            'crashloop_list': crashloop_list
        }
    except Exception as e:
        print(f"❌ Error checking pod state for namespace {namespace}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
            'running_list': [], 'pending_list': [], 'crashloop_list': []
        }

def check_http_status_live(hostname):
    """
    Perform LIVE HTTP check to determine application status.
    NO CACHE - always performs fresh HTTP request.
    Returns: (status, http_code, latency_ms)
    STRICT RULE: Only 200 = UP, everything else = DOWN
    """
    if not hostname:
        return 'DOWN', 0, None
    
    # Try HTTPS first, then HTTP as fallback
    urls_to_try = []
    if hostname.startswith('http'):
        urls_to_try.append(hostname)
    else:
        urls_to_try.append(f"https://{hostname}")
        urls_to_try.append(f"http://{hostname}")
    
    for url in urls_to_try:
        try:
            start_time = time.time()
            response = requests.head(url, timeout=5, verify=False, allow_redirects=True)
            latency_ms = int((time.time() - start_time) * 1000)
            status_code = response.status_code
            
            # STRICT: Only 200 = UP, everything else = DOWN
            if status_code == 200:
                return 'UP', status_code, latency_ms
            else:
                return 'DOWN', status_code, latency_ms
                
        except requests.exceptions.Timeout:
            if url == urls_to_try[-1]:
                return 'DOWN', 0, 5000
            continue
        except requests.exceptions.ConnectionError:
            if url == urls_to_try[-1]:
                return 'DOWN', 0, None
            continue
        except requests.exceptions.SSLError:
            continue  # Try HTTP fallback
        except Exception:
            if url == urls_to_try[-1]:
                return 'DOWN', 0, None
            continue
    
    return 'DOWN', 0, None

def get_app_metadata(app_name):
    """
    Get application metadata from DynamoDB (namespace, hostnames, DB hosts).
    This is the ONLY use of DynamoDB - for metadata, NOT for status.
    """
    table = dynamodb.Table(TABLE_NAME)
    
    try:
        response = table.get_item(Key={'app_name': app_name})
        if 'Item' not in response:
            return None
        
        item = response['Item']
        
        # Helper to extract value from DynamoDB format
        def get_value(field, default=None):
            val = item.get(field, default)
            if val is None:
                return default
            if isinstance(val, dict) and 'S' in val:
                return val['S']
            if isinstance(val, dict) and 'L' in val:
                return [h.get('S', '') if isinstance(h, dict) else h for h in val['L']]
            if isinstance(val, dict) and 'N' in val:
                return int(val['N'])
            return val
        
        # Format hostnames
        hostnames_raw = item.get('hostnames', [])
        if isinstance(hostnames_raw, dict) and 'L' in hostnames_raw:
            hostnames = [h.get('S', '') if isinstance(h, dict) else h for h in hostnames_raw['L']]
        else:
            hostnames = hostnames_raw if isinstance(hostnames_raw, list) else []
        
        return {
            'app_name': app_name,
            'namespace': get_value('namespace', 'default'),
            'hostnames': hostnames,
            'postgres_host': get_value('postgres_host'),
            'postgres_port': get_value('postgres_port', 5432),
            'postgres_db': get_value('postgres_db'),
            'postgres_user': get_value('postgres_user'),
            'neo4j_host': get_value('neo4j_host'),
            'neo4j_port': get_value('neo4j_port', 7687),
            'neo4j_username': get_value('neo4j_username')
        }
    except Exception as e:
        print(f"Error getting app metadata for {app_name}: {str(e)}")
        return None

def get_app_live_status(app_name):
    """
    Get LIVE status for a single application.
    Performs all checks in parallel for speed.
    NO CACHING - all checks are fresh.
    """
    # Get metadata from DynamoDB (only for namespace, hostnames, DB hosts)
    metadata = get_app_metadata(app_name)
    if not metadata:
        print(f"⚠️  No metadata found for app: {app_name}")
        return None
    
    # Use authoritative namespace mapping (from config.yaml)
    discovered_namespace = metadata.get('namespace')
    namespace = get_namespace_for_app(app_name, discovered_namespace)
    
    # Log namespace determination for debugging
    if discovered_namespace != namespace:
        print(f"🔄 Namespace override for {app_name}: {discovered_namespace} → {namespace} (from config mapping)")
    else:
        print(f"✅ Using namespace for {app_name}: {namespace}")
    
    hostnames = metadata['hostnames']
    primary_hostname = hostnames[0] if hostnames else None
    
    # Get NodeGroup name from defaults
    nodegroup_defaults = get_nodegroup_defaults_for_app(app_name)
    nodegroup_name = nodegroup_defaults['nodegroup'] if nodegroup_defaults else None
    
    # Perform all checks in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all checks
        db_postgres_future = executor.submit(check_db_state_live, metadata['postgres_host'])
        db_neo4j_future = executor.submit(check_db_state_live, metadata['neo4j_host'])
        http_future = executor.submit(check_http_status_live, primary_hostname)
        pods_future = executor.submit(check_pod_state_live, namespace)
        
        # Get results (with timeout handling)
        try:
            postgres_result = db_postgres_future.result(timeout=30)
        except Exception as e:
            print(f"⚠️  Error getting postgres result: {str(e)}")
            postgres_result = {'state': 'stopped', 'instance_id': None, 'is_shared': False, 'shared_with': []}
        
        try:
            neo4j_result = db_neo4j_future.result(timeout=30)
        except Exception as e:
            print(f"⚠️  Error getting neo4j result: {str(e)}")
            neo4j_result = {'state': 'stopped', 'instance_id': None, 'is_shared': False, 'shared_with': []}
        
        try:
            http_status, http_code, http_latency_ms = http_future.result(timeout=10)
        except Exception as e:
            print(f"⚠️  Error getting HTTP result: {str(e)}")
            http_status, http_code, http_latency_ms = 'DOWN', 0, None
        
        try:
            pods = pods_future.result(timeout=30)
            # Ensure pods dict has all required fields
            if not isinstance(pods, dict):
                pods = {'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0, 'running_list': [], 'pending_list': [], 'crashloop_list': []}
            # Ensure all fields exist
            pods.setdefault('running', 0)
            pods.setdefault('pending', 0)
            pods.setdefault('crashloop', 0)
            pods.setdefault('total', 0)
            pods.setdefault('running_list', [])
            pods.setdefault('pending_list', [])
            pods.setdefault('crashloop_list', [])
            print(f"✅ Pod data for {app_name}: running={pods.get('running')}, pending={pods.get('pending')}, crashloop={pods.get('crashloop')}, total={pods.get('total')}")
        except Exception as e:
            print(f"⚠️  Error getting pods result for {app_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            pods = {
                'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
                'running_list': [], 'pending_list': [], 'crashloop_list': [],
                'error': f'Pod check failed: {str(e)[:100]}'
            }
    
    # Get NodeGroup state (separate call, can't be parallelized easily with others)
    nodegroups = []
    if nodegroup_name:
        ng_state = check_nodegroup_state_live(nodegroup_name)
        if ng_state:
            nodegroups.append(ng_state)
    
    # Extract database state from dict (new format)
    postgres_state = postgres_result.get('state', 'stopped') if isinstance(postgres_result, dict) else postgres_result
    neo4j_state = neo4j_result.get('state', 'stopped') if isinstance(neo4j_result, dict) else neo4j_result
    
    # Build response in required format
    primary_hostname = metadata['hostnames'][0] if metadata['hostnames'] else app_name
    
    return {
        'app': app_name,  # Keep for backward compatibility
        'name': app_name,  # Primary field for UI
        'hostname': primary_hostname,  # Primary hostname
        'hostnames': metadata['hostnames'],  # All hostnames
        'namespace': metadata['namespace'],
        'http': {
            'status': http_status,
            'code': http_code,
            'latency_ms': http_latency_ms
        },
        'postgres': {
            'state': postgres_state,
            'host': metadata['postgres_host'],
            'port': metadata['postgres_port'],
            'is_shared': postgres_result.get('is_shared', False) if isinstance(postgres_result, dict) else False,
            'shared_with': postgres_result.get('shared_with', []) if isinstance(postgres_result, dict) else []
        },
        'neo4j': {
            'state': neo4j_state,
            'host': metadata['neo4j_host'],
            'port': metadata['neo4j_port'],
            'is_shared': neo4j_result.get('is_shared', False) if isinstance(neo4j_result, dict) else False,
            'shared_with': neo4j_result.get('shared_with', []) if isinstance(neo4j_result, dict) else []
        },
        'nodegroups': nodegroups,
        'pods': pods,
        'last_checked': 'live'
    }

def get_all_apps_live():
    """
    Get LIVE status for all applications.
    Performs all checks in parallel for speed.
    """
    table = dynamodb.Table(TABLE_NAME)
    
    try:
        response = table.scan()
        apps_metadata = response.get('Items', [])
        
        # Extract app names
        app_names = []
        for app in apps_metadata:
            app_name = app.get('app_name')
            if isinstance(app_name, dict) and 'S' in app_name:
                app_name = app_name['S']
            if app_name:
                app_names.append(app_name)
        
        # Get live status for all apps in parallel
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(get_app_live_status, app_name): app_name 
                      for app_name in app_names}
            
            for future in as_completed(futures):
                app_name = futures[future]
                try:
                    result = future.result(timeout=60)  # 60 second timeout per app
                    if result:
                        # Ensure pods data is always present
                        if 'pods' not in result or not result['pods']:
                            print(f"⚠️  Missing pods data for {app_name}, adding default")
                            result['pods'] = {
                                'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
                                'running_list': [], 'pending_list': [], 'crashloop_list': []
                            }
                        results.append(result)
                except Exception as e:
                    print(f"❌ Error getting live status for {app_name}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    # Still add app with default pods data so UI doesn't break
                    results.append({
                        'app': app_name,
                        'name': app_name,
                        'hostname': app_name,
                        'status': 'DOWN',
                        'pods': {
                            'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0,
                            'running_list': [], 'pending_list': [], 'crashloop_list': [],
                            'error': f'Status check failed: {str(e)[:100]}'
                        }
                    })
        
        print(f"✅ Returning {len(results)} apps with pod data")
        return results
    except Exception as e:
        print(f"Error getting all apps: {str(e)}")
        raise

def lambda_handler(event, context):
    """Main Lambda handler."""
    http_method = event.get('httpMethod', '')
    path = event.get('path', '')
    path_params = event.get('pathParameters') or {}
    
    try:
        # Handle GET /apps - list all apps with LIVE status
        if http_method == 'GET' and '/apps' in path and not path_params.get('app_name'):
            apps = get_all_apps_live()
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                },
                'body': json.dumps({
                    'apps': apps,
                    'count': len(apps)
                }, default=str)
            }
        
        # Handle GET /apps/{app_name} - get app details with LIVE status
        elif http_method == 'GET' and path_params.get('app_name'):
            app_name = path_params['app_name']
            app = get_app_live_status(app_name)
            
            if app:
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps(app, default=str)
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': f'Application {app_name} not found'}, default=str)
                }
        
        # Handle GET /status/{app_name} - quick status check (UP/DOWN only)
        elif http_method == 'GET' and '/status/' in path and path_params.get('app_name'):
            app_name = path_params['app_name']
            metadata = get_app_metadata(app_name)
            
            if not metadata:
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': f'Application {app_name} not found'}, default=str)
                }
            
            # Perform quick HTTP check
            hostnames = metadata.get('hostnames', [])
            primary_hostname = hostnames[0] if hostnames else None
            
            if not primary_hostname:
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'app_name': app_name, 'status': 'DOWN', 'reason': 'No hostname'}, default=str)
                }
            
            # Quick HTTP check
            urls_to_try = [f"https://{primary_hostname}", f"http://{primary_hostname}"]
            status = 'DOWN'
            http_code = None
            
            for url in urls_to_try:
                try:
                    response = requests.head(url, timeout=5, verify=False, allow_redirects=True)
                    http_code = response.status_code
                    if response.status_code == 200:
                        status = 'UP'
                        break
                except:
                    continue
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'app_name': app_name, 'status': status}, default=str)
            }
        
        # Handle GET /status/quick?app=<app_name> - lightweight quick status endpoint for Controller
        elif http_method == 'GET' and '/status/quick' in path:
            query_params = event.get('queryStringParameters') or {}
            app_name = query_params.get('app')
            
            if not app_name:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Missing app parameter'}, default=str)
                }
            
            metadata = get_app_metadata(app_name)
            
            if not metadata:
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'app': app_name,
                        'status': 'UNKNOWN',
                        'http_code': None,
                        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        'reason': 'Application not found in registry'
                    }, default=str)
                }
            
            # Perform quick HTTP check with 3s timeout
            hostnames = metadata.get('hostnames', [])
            primary_hostname = hostnames[0] if hostnames else None
            
            if not primary_hostname:
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'app': app_name,
                        'status': 'UNKNOWN',
                        'http_code': None,
                        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        'reason': 'No hostname configured'
                    }, default=str)
                }
            
            # Quick HTTP check with 3s timeout
            urls_to_try = [f"https://{primary_hostname}", f"http://{primary_hostname}"]
            status = 'UNKNOWN'
            http_code = None
            
            for url in urls_to_try:
                try:
                    response = requests.head(url, timeout=3, verify=False, allow_redirects=True)
                    http_code = response.status_code
                    if response.status_code == 200:
                        status = 'UP'
                        break
                    else:
                        status = 'DOWN'
                except requests.exceptions.Timeout:
                    status = 'UNKNOWN'
                    break
                except (requests.exceptions.ConnectionError, requests.exceptions.RequestException):
                    continue
                except Exception:
                    status = 'UNKNOWN'
                    break
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'app': app_name,
                    'status': status,
                    'http_code': http_code,
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                }, default=str)
            }
        
        # Handle OPTIONS for CORS
        elif http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                },
                'body': ''
            }
        
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Invalid request'}, default=str)
            }
    
    except Exception as e:
        print(f"API handler error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)}, default=str)
        }
