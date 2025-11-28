"""
Controller Lambda Function
Handles start/stop operations for applications with complete workflow.
"""

import json
import os
import time
import boto3
import requests
import socket
from botocore.exceptions import ClientError
from kubernetes import client, config
from urllib.parse import urlparse

# Import config loader
try:
    from config.loader import (
        get_config, get_eks_cluster_name, get_dynamodb_table_name,
        get_nodegroup_defaults
    )
except ImportError:
    # Fallback for local testing or if config module not available
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from config.loader import (
        get_config, get_eks_cluster_name, get_dynamodb_table_name,
        get_nodegroup_defaults
    )

# Load configuration (cached after first load)
try:
    CONFIG = get_config()
    EKS_CLUSTER_NAME = get_eks_cluster_name()
    TABLE_NAME = get_dynamodb_table_name()
    NODEGROUP_DEFAULTS_DICT = get_nodegroup_defaults()
except Exception as e:
    # Fallback to environment variables if config loading fails
    print(f"⚠️ Warning: Could not load config.yaml: {e}")
    print("⚠️ Falling back to environment variables")
    EKS_CLUSTER_NAME = os.environ.get('EKS_CLUSTER_NAME')
    TABLE_NAME = os.environ.get('REGISTRY_TABLE_NAME', 'eks-app-registry')
    NODEGROUP_DEFAULTS_DICT = {}

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ec2 = boto3.client('ec2')
eks = boto3.client('eks')
autoscaling = boto3.client('autoscaling')

# Kubernetes client (will be initialized when needed)
k8s_client = None

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
        'body': {},
        'headers': {
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
    base64_url = base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8')
    return 'k8s-aws-v1.' + base64_url.rstrip('=')

def get_nodegroup_defaults(app_name):
    """Get NodeGroup defaults for an application from the authoritative mapping."""
    return NODEGROUP_DEFAULTS_DICT.get(app_name)

def get_app_from_registry(app_name):
    """Retrieve application information from DynamoDB."""
    table = dynamodb.Table(TABLE_NAME)
    
    try:
        response = table.get_item(Key={'app_name': app_name})
        if 'Item' in response:
            return response['Item']
        return None
    except Exception as e:
        print(f"Error getting app from registry: {str(e)}")
        raise

def get_nodegroup_asg_name(cluster_name, nodegroup_name):
    """Get Auto Scaling Group name for a NodeGroup."""
    try:
        response = eks.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name
        )
        # Extract ASG name from nodegroup resources
        resources = response['nodegroup'].get('resources', {})
        asg_names = resources.get('autoScalingGroups', [])
        if asg_names:
            return asg_names[0].get('name')
        return None
    except Exception as e:
        print(f"Error getting ASG for nodegroup {nodegroup_name}: {str(e)}")
        return None

def load_k8s_config():
    """Load Kubernetes configuration for EKS."""
    global k8s_client
    if k8s_client is not None:
        return
    
    try:
        # Try in-cluster config first (if running in EKS)
        config.load_incluster_config()
        print("✅ Loaded in-cluster Kubernetes config")
        k8s_client = client
        return
    except:
        pass
    
    try:
        # Get EKS cluster information
        import base64
        cluster_info = eks.describe_cluster(name=EKS_CLUSTER_NAME)
        cluster = cluster_info['cluster']
        
        # Configure Kubernetes client
        configuration = client.Configuration()
        configuration.host = cluster['endpoint']
        configuration.verify_ssl = True
        configuration.ssl_ca_cert = None
        
        # Decode certificate
        cert_data = base64.b64decode(cluster['certificateAuthority']['data'])
        
        # Write cert to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.crt') as cert_file:
            cert_file.write(cert_data)
            configuration.ssl_ca_cert = cert_file.name
        
        # Get authentication token
        configuration.api_key = {"authorization": "Bearer " + get_bearer_token(EKS_CLUSTER_NAME)}
        
        client.Configuration.set_default(configuration)
        k8s_client = client
        print(f"✅ Loaded EKS config for cluster: {EKS_CLUSTER_NAME}")
    except Exception as e:
        try:
            # Final fallback to kubeconfig (for local testing)
            config.load_kube_config()
            k8s_client = client
            print("✅ Loaded kubeconfig")
        except:
            print(f"⚠️  Could not load Kubernetes config: {str(e)}")
            # Continue without K8s client - some operations will be skipped

def scale_nodegroup(cluster_name, nodegroup_name, desired_capacity, min_size=None, max_size=None):
    """
    Scale a NodeGroup to desired capacity and wait until ACTIVE and HEALTHY.
    
    Args:
        cluster_name: EKS cluster name
        nodegroup_name: NodeGroup name
        desired_capacity: Desired number of nodes
        min_size: Minimum size (if None, uses current or 0)
        max_size: Maximum size (if None, uses current max)
    """
    try:
        print(f"🔄 Scaling NodeGroup: {nodegroup_name} to desired={desired_capacity}, min={min_size}, max={max_size}")
        
        # Get current nodegroup config
        response = eks.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name
        )
        
        current_config = response['nodegroup'].get('scalingConfig', {})
        current_min = current_config.get('minSize', 0)
        current_max = current_config.get('maxSize', 1)
        current_desired = current_config.get('desiredSize', 0)
        current_status = response['nodegroup'].get('status', 'UNKNOWN')
        
        # Use provided values or keep current
        target_min = min_size if min_size is not None else current_min
        target_max = max_size if max_size is not None else current_max
        
        # Ensure desired capacity is within bounds
        desired_capacity = max(target_min, min(desired_capacity, target_max))
        
        print(f"   Current: min={current_min}, max={current_max}, desired={current_desired}")
        print(f"   Target: min={target_min}, max={target_max}, desired={desired_capacity}")
        
        # Update nodegroup scaling config
        eks.update_nodegroup_config(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name,
            scalingConfig={
                'minSize': target_min,
                'maxSize': target_max,
                'desiredSize': desired_capacity
            }
        )
        
        print(f"   ✅ Scaling command sent")
        
        # Wait for NodeGroup to be ACTIVE and HEALTHY
        if desired_capacity > 0:
            max_wait = 600  # 10 minutes
            wait_interval = 15  # Check every 15 seconds
            elapsed = 0
            
            while elapsed < max_wait:
                response = eks.describe_nodegroup(
                    clusterName=cluster_name,
                    nodegroupName=nodegroup_name
                )
                ng = response['nodegroup']
                status = ng.get('status', 'UNKNOWN')
                health = ng.get('health', {})
                issues = health.get('issues', [])
                
                # Check if all instances are healthy
                resources = ng.get('resources', {})
                instances = resources.get('remoteVolumeSecurityGroups', [])  # This might not be the right field
                
                print(f"   ⏳ Status: {status}, Health issues: {len(issues)}, Elapsed: {elapsed}s")
                
                if status == 'ACTIVE' and len(issues) == 0:
                    # Check if desired nodes are running
                    scaling_config = ng.get('scalingConfig', {})
                    current_desired = scaling_config.get('desiredSize', 0)
                    
                    if current_desired == desired_capacity:
                        print(f"   ✅ NodeGroup {nodegroup_name} is ACTIVE and HEALTHY")
                        return {
                            'name': nodegroup_name,
                            'status': 'ACTIVE',
                            'desired_size': desired_capacity,
                            'healthy': True
                        }
                
                time.sleep(wait_interval)
                elapsed += wait_interval
            
            # Timeout - but return partial success
            print(f"   ⚠️  Timeout waiting for NodeGroup to be fully healthy")
            return {
                'name': nodegroup_name,
                'status': status,
                'desired_size': desired_capacity,
                'healthy': False,
                'warning': 'Timeout waiting for full health check'
            }
        else:
            # Scaling to 0 - just wait for status update
            print(f"   ✅ NodeGroup scaled to 0")
            return {
                'name': nodegroup_name,
                'status': 'ACTIVE',
                'desired_size': 0,
                'healthy': True
            }
        
    except Exception as e:
        print(f"   ❌ Error scaling nodegroup {nodegroup_name}: {str(e)}")
        raise

def start_ec2_instance(instance_id):
    """Start an EC2 instance and wait until running."""
    try:
        print(f"🔄 Starting EC2 instance: {instance_id}")
        response = ec2.start_instances(InstanceIds=[instance_id])
        state = response['StartingInstances'][0]['CurrentState']['Name']
        print(f"   Current state: {state}")
        
        # Wait for instance to be running
        max_wait = 300  # 5 minutes
        wait_interval = 10  # Check every 10 seconds
        elapsed = 0
        
        while elapsed < max_wait:
            response = ec2.describe_instances(InstanceIds=[instance_id])
            instance = response['Reservations'][0]['Instances'][0]
            current_state = instance['State']['Name']
            
            if current_state == 'running':
                private_ip = instance.get('PrivateIpAddress', 'N/A')
                print(f"   ✅ Instance {instance_id} is RUNNING (IP: {private_ip})")
                return {
                    'instance_id': instance_id,
                    'state': 'running',
                    'private_ip': private_ip
                }
            elif current_state == 'stopped':
                print(f"   ⚠️  Instance {instance_id} is STOPPED (failed to start)")
                return {
                    'instance_id': instance_id,
                    'state': 'stopped',
                    'private_ip': None
                }
            
            print(f"   ⏳ Waiting... ({current_state}, {elapsed}s elapsed)")
            time.sleep(wait_interval)
            elapsed += wait_interval
        
        # Timeout
        print(f"   ⚠️  Timeout waiting for instance {instance_id} to start")
        return {
            'instance_id': instance_id,
            'state': 'pending',
            'private_ip': None
        }
        
    except Exception as e:
        print(f"   ❌ Error starting instance {instance_id}: {str(e)}")
        raise

def stop_ec2_instance(instance_id):
    """Stop an EC2 instance."""
    try:
        response = ec2.stop_instances(InstanceIds=[instance_id])
        state = response['StoppingInstances'][0]['CurrentState']['Name']
        print(f"Stopping instance {instance_id}, current state: {state}")
        return True
    except Exception as e:
        print(f"Error stopping instance {instance_id}: {str(e)}")
        raise

def check_database_health(host, port, db_type='postgres'):
    """
    Check if database is accessible.
    Returns: True if accessible, False otherwise
    """
    if not host or not port:
        return False
    
    try:
        # Use socket connection (pure Python, no external dependencies)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        
        if result == 0:
            print(f"      ✅ {db_type.upper()} {host}:{port} is accessible")
            return True
        else:
            print(f"      ❌ {db_type.upper()} {host}:{port} connection refused")
            return False
    except socket.timeout:
        print(f"      ❌ {db_type.upper()} {host}:{port} connection timeout")
        return False
    except Exception as e:
        print(f"      ❌ {db_type.upper()} {host}:{port} check failed: {str(e)}")
        return False

def get_sharing_applications(resource_host, resource_type, current_app_name):
    """
    Get all applications that share a database resource (Postgres or Neo4j).
    
    Args:
        resource_host: Database host IP address
        resource_type: 'postgres' or 'neo4j'
        current_app_name: Name of the app being stopped (excluded from results)
    
    Returns:
        List of app names that share this database
    """
    sharing_apps = []
    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.scan()
        
        for item in response.get('Items', []):
            app_name = item.get('app_name')
            if app_name == current_app_name:
                continue
            
            # Check if this app is using the shared resource
            if resource_type == 'postgres':
                app_postgres_host = item.get('postgres_host')
                if app_postgres_host == resource_host:
                    sharing_apps.append(app_name)
            elif resource_type == 'neo4j':
                app_neo4j_host = item.get('neo4j_host')
                if app_neo4j_host == resource_host:
                    sharing_apps.append(app_name)
        
        return sharing_apps
    except Exception as e:
        print(f"⚠️  Error finding sharing applications: {str(e)}")
        return []

def check_app_status_live(app_name):
    """
    Check if an application is UP using live HTTP check.
    Calls the API Handler's live status check logic.
    
    Args:
        app_name: Application name to check
    
    Returns:
        True if app is UP (HTTP 200), False otherwise
    """
    try:
        # Get app metadata to find hostname
        app_data = get_app_from_registry(app_name)
        if not app_data:
            print(f"   ⚠️  App {app_name} not found in registry")
            return False
        
        hostnames = app_data.get('hostnames', [])
        if not hostnames:
            print(f"   ⚠️  App {app_name} has no hostnames")
            return False
        
        # Try each hostname until one responds
        primary_hostname = hostnames[0] if isinstance(hostnames, list) else hostnames
        
        # Build URLs to try (HTTPS first, then HTTP)
        urls_to_try = []
        if primary_hostname:
            urls_to_try.append(f"https://{primary_hostname}")
            urls_to_try.append(f"http://{primary_hostname}")
        
        # Perform HTTP HEAD request (faster than GET)
        for url in urls_to_try:
            try:
                response = requests.head(url, timeout=5, verify=False, allow_redirects=True)
                # STRICT: Only HTTP 200 = UP
                if response.status_code == 200:
                    print(f"   ✅ {app_name} is UP (HTTP 200 from {url})")
                    return True
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.SSLError):
                continue
            except Exception:
                continue
        
        print(f"   ❌ {app_name} is DOWN (no HTTP 200 response)")
        return False
    except Exception as e:
        print(f"   ⚠️  Error checking live status for {app_name}: {str(e)}")
        # Conservative: assume UP if we can't check (prevents stopping DB)
        return True

def are_any_apps_running(app_list):
    """
    Check if ANY applications in the list are currently running (UP).
    Uses live HTTP checks for accurate status.
    
    Args:
        app_list: List of application names to check
    
    Returns:
        True if ANY app is UP, False if ALL are DOWN
    """
    if not app_list:
        return False
    
    print(f"   🔍 Checking live status of {len(app_list)} sharing application(s)...")
    for app_name in app_list:
        if check_app_status_live(app_name):
            return True
    
    return False

def is_shared_resource_in_use(resource_host, resource_type, current_app_name):
    """
    Check if a shared resource (Postgres/Neo4j) is in use by other applications.
    Uses LIVE HTTP checks instead of stale DynamoDB status.
    
    Returns True if other apps are using it AND are UP, False otherwise.
    """
    try:
        # Get all apps sharing this database
        sharing_apps = get_sharing_applications(resource_host, resource_type, current_app_name)
        
        if not sharing_apps:
            print(f"   ℹ️  No other applications share this {resource_type} database")
            return False
        
        print(f"   ℹ️  {resource_type.upper()} {resource_host} is shared with: {', '.join(sharing_apps)}")
        
        # Check if ANY sharing app is currently UP (using live HTTP checks)
        any_running = are_any_apps_running(sharing_apps)
        
        if any_running:
            print(f"   ⚠️  Database is in use by active applications - will NOT stop")
            return True
        else:
            print(f"   ✅ All sharing applications are DOWN - safe to stop database")
            return False
    except Exception as e:
        print(f"⚠️  Error checking if shared resource is in use: {str(e)}")
        # Conservative: assume it's in use if we can't check (prevents stopping DB)
        return True

def is_database_shared(app_data, db_type='postgres'):
    """Check if a database (Postgres or Neo4j) is shared."""
    shared_resources = app_data.get('shared_resources', {})
    
    if db_type == 'postgres':
        postgres_host = app_data.get('postgres_host')
        if not postgres_host:
            return False
        for pg in shared_resources.get('postgres', []):
            if pg.get('host') == postgres_host:
                return True
    elif db_type == 'neo4j':
        neo4j_host = app_data.get('neo4j_host')
        if not neo4j_host:
            return False
        for neo in shared_resources.get('neo4j', []):
            if neo.get('host') == neo4j_host:
                return True
    
    return False

def wait_for_db_healthy(host, port, db_type='postgres', max_wait=300):
    """
    Wait for database to be healthy (accessible).
    Returns True if healthy, False if timeout.
    """
    print(f"   ⏳ Waiting for {db_type.upper()} at {host}:{port} to be healthy...")
    
    elapsed = 0
    check_interval = 5  # Check every 5 seconds
    
    while elapsed < max_wait:
        if check_database_health(host, port, db_type):
            print(f"   ✅ {db_type.upper()} is healthy")
            return True
        
        time.sleep(check_interval)
        elapsed += check_interval
        print(f"   ⏳ Still waiting... ({elapsed}s/{max_wait}s)")
    
    print(f"   ⚠️  Timeout waiting for {db_type.upper()} to be healthy")
    return False

def check_shared_resources_blocking(app_data):
    """Check if shared resources prevent shutdown."""
    shared_resources = app_data.get('shared_resources', {})
    blocking = []
    
    # Check PostgreSQL
    for pg in shared_resources.get('postgres', []):
        db_identifier = pg.get('host') or pg.get('instance_id', 'Unknown')
        blocking.append({
            'type': 'postgres',
            'host': pg.get('host'),
            'linked_apps': pg['linked_apps'],
            'message': f"Database {db_identifier} is shared with {', '.join(pg['linked_apps'])}. Cannot be stopped safely."
        })
    
    # Check Neo4j
    for neo4j in shared_resources.get('neo4j', []):
        db_identifier = neo4j.get('host') or neo4j.get('instance_id', 'Unknown')
        blocking.append({
            'type': 'neo4j',
            'host': neo4j.get('host'),
            'linked_apps': neo4j['linked_apps'],
            'message': f"Database {db_identifier} is shared with {', '.join(neo4j['linked_apps'])}. Cannot be stopped safely."
        })
    
    return blocking

def scale_kubernetes_workloads(namespace, replicas=1):
    """
    Scale Kubernetes workloads (Deployments, StatefulSets) in the namespace.
    
    Args:
        namespace: Kubernetes namespace
        replicas: Number of replicas (1 for start, 0 for stop)
    """
    load_k8s_config()
    
    if k8s_client is None:
        print("⚠️  Kubernetes client not available, skipping workload scaling")
        return {'deployments': [], 'statefulsets': [], 'replicasets': [], 'daemonsets': [], 'pods': {}}
    
    results = {
        'deployments': [],
        'statefulsets': [],
        'replicasets': [],
        'daemonsets': [],
        'pods': {'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0}
    }
    
    try:
        apps_v1 = k8s_client.AppsV1Api()
        core_v1 = k8s_client.CoreV1Api()
        
        # Scale ALL Deployments
        print(f"🔄 Scaling ALL Deployments in namespace: {namespace} to {replicas} replicas")
        deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
        for deploy in deployments.items:
            deploy_name = deploy.metadata.name
            try:
                apps_v1.patch_namespaced_deployment_scale(
                    name=deploy_name,
                    namespace=namespace,
                    body={'spec': {'replicas': replicas}}
                )
                results['deployments'].append({'name': deploy_name, 'replicas': replicas})
                print(f"   ✅ Scaled Deployment: {deploy_name} to {replicas} replica(s)")
            except Exception as e:
                print(f"   ⚠️  Failed to scale Deployment {deploy_name}: {str(e)}")
        
        # Scale ALL StatefulSets
        print(f"🔄 Scaling ALL StatefulSets in namespace: {namespace} to {replicas} replicas")
        statefulsets = apps_v1.list_namespaced_stateful_set(namespace=namespace)
        for sts in statefulsets.items:
            sts_name = sts.metadata.name
            try:
                apps_v1.patch_namespaced_stateful_set_scale(
                    name=sts_name,
                    namespace=namespace,
                    body={'spec': {'replicas': replicas}}
                )
                results['statefulsets'].append({'name': sts_name, 'replicas': replicas})
                print(f"   ✅ Scaled StatefulSet: {sts_name} to {replicas} replica(s)")
            except Exception as e:
                print(f"   ⚠️  Failed to scale StatefulSet {sts_name}: {str(e)}")
        
        # Scale ReplicaSets (standalone - only if not owned by Deployments)
        if replicas > 0:  # Only scale standalone ReplicaSets when starting
            print(f"🔄 Scaling standalone ReplicaSets in namespace: {namespace}")
            replicasets = apps_v1.list_namespaced_replica_set(namespace=namespace)
            for rs in replicasets.items:
                # Skip ReplicaSets owned by Deployments
                if rs.metadata.owner_references:
                    continue
                rs_name = rs.metadata.name
                try:
                    apps_v1.patch_namespaced_replica_set_scale(
                        name=rs_name,
                        namespace=namespace,
                        body={'spec': {'replicas': replicas}}
                    )
                    results['replicasets'].append({'name': rs_name, 'replicas': replicas})
                    print(f"   ✅ Scaled ReplicaSet: {rs_name} to {replicas} replica(s)")
                except Exception as e:
                    print(f"   ⚠️  Failed to scale ReplicaSet {rs_name}: {str(e)}")
        
        # Restart DaemonSets
        print(f"🔄 Restarting DaemonSets in namespace: {namespace}")
        daemonsets = apps_v1.list_namespaced_daemon_set(namespace=namespace)
        for ds in daemonsets.items:
            ds_name = ds.metadata.name
            try:
                apps_v1.patch_namespaced_daemon_set(
                    name=ds_name,
                    namespace=namespace,
                    body={'spec': {'template': {'metadata': {'annotations': {'kubectl.kubernetes.io/restartedAt': str(int(time.time()))}}}}}
                )
                results['daemonsets'].append({'name': ds_name, 'status': 'restarted'})
                print(f"   ✅ Restarted DaemonSet: {ds_name}")
            except Exception as e:
                print(f"   ⚠️  Failed to restart DaemonSet {ds_name}: {str(e)}")
        
        # Wait for pods to be Ready
        print(f"⏳ Waiting for pods to be Ready in namespace: {namespace}")
        try:
            # Wait for condition
            max_wait = 300
            wait_interval = 5
            elapsed = 0
            
            while elapsed < max_wait:
                pods = core_v1.list_namespaced_pod(namespace=namespace)
                ready_count = 0
                total_count = len(pods.items)
                
                for pod in pods.items:
                    if pod.status.phase == 'Running':
                        # Check if all containers are ready
                        if pod.status.container_statuses:
                            all_ready = all(cs.ready for cs in pod.status.container_statuses)
                            if all_ready:
                                ready_count += 1
                
                print(f"   ⏳ Pods: {ready_count}/{total_count} ready ({elapsed}s elapsed)")
                
                if ready_count == total_count and total_count > 0:
                    print(f"   ✅ All pods are Ready")
                    break
                
                time.sleep(wait_interval)
                elapsed += wait_interval
            
            # Collect pod statuses
            pods = core_v1.list_namespaced_pod(namespace=namespace)
            running = 0
            pending = 0
            crashloop = 0
            
            for pod in pods.items:
                phase = pod.status.phase
                if phase == 'Running':
                    running += 1
                elif phase == 'Pending':
                    pending += 1
                
                # Check for CrashLoopBackOff
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        if cs.state and cs.state.waiting:
                            if 'CrashLoopBackOff' in cs.state.waiting.reason:
                                crashloop += 1
                                break
            
            results['pods'] = {
                'running': running,
                'pending': pending,
                'crashloop': crashloop,
                'total': len(pods.items)
            }
            
        except Exception as e:
            print(f"   ⚠️  Error waiting for pods: {str(e)}")
        
    except Exception as e:
        print(f"⚠️  Error scaling Kubernetes workloads: {str(e)}")
    
    return results

def verify_http_accessibility(hostname, health_url):
    """Verify application HTTP accessibility."""
    try:
        # Construct URL
        if not hostname.startswith('http'):
            url = f"https://{hostname}{health_url}"
        else:
            parsed = urlparse(hostname)
            url = f"{parsed.scheme}://{parsed.netloc}{health_url}"
        
        print(f"🌐 Verifying HTTP accessibility: {url}")
        
        start_time = time.time()
        response = requests.head(url, timeout=5, verify=False, allow_redirects=False)
        response_time_ms = int((time.time() - start_time) * 1000)
        
        status_code = response.status_code
        is_accessible = status_code in [200, 301, 302, 401, 403]
        
        print(f"   Status: {status_code}, Latency: {response_time_ms}ms, Accessible: {is_accessible}")
        
        return {
            'http_status': status_code,
            'response_time_ms': response_time_ms,
            'accessible': is_accessible,
            'timestamp': int(time.time())
        }
        
    except requests.exceptions.Timeout:
        return {
            'http_status': 0,
            'response_time_ms': 5000,
            'accessible': False,
            'timestamp': int(time.time()),
            'error': 'Timeout'
        }
    except Exception as e:
        return {
            'http_status': 0,
            'response_time_ms': None,
            'accessible': False,
            'timestamp': int(time.time()),
            'error': str(e)
        }

def find_ec2_instance_by_ip(ip_address):
    """
    Find EC2 instance by private IP address.
    Returns: (instance_id, state) or (None, None) if not found
    """
    if not ip_address:
        return None, None
    
    try:
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

def build_start_preview(app_name):
    """
    Build a preview of all actions that would be taken when starting an application.
    Returns a preview object with all planned actions.
    """
    app_data = get_app_from_registry(app_name)
    if not app_data:
        return {
            'dry_run': True,
            'error': f'Application {app_name} not found in registry'
        }
    
    namespace = app_data.get('namespace', 'default')
    postgres_host = app_data.get('postgres_host')
    neo4j_host = app_data.get('neo4j_host')
    
    preview = {
        'dry_run': True,
        'app_name': app_name,
        'namespace': namespace,
        'actions': [],
        'warnings': [],
        'summary': {
            'ec2_instances_to_start': 0,
            'nodegroups_to_scale': 0,
            'deployments_to_scale': 0,
            'statefulsets_to_scale': 0,
            'warnings': 0
        }
    }
    
    # STEP 1: Check Postgres & Neo4j EC2 states
    if postgres_host:
        postgres_instance_id, postgres_ec2_state = find_ec2_instance_by_ip(postgres_host)
        if postgres_instance_id:
            if postgres_ec2_state != 'running':
                preview['actions'].append({
                    'type': 'start_ec2',
                    'resource': 'postgres',
                    'instance_id': postgres_instance_id,
                    'host': postgres_host,
                    'current_state': postgres_ec2_state,
                    'target_state': 'running'
                })
                preview['summary']['ec2_instances_to_start'] += 1
        else:
            preview['warnings'].append(f'PostgreSQL host {postgres_host} - no EC2 instance found')
    
    if neo4j_host:
        neo4j_instance_id, neo4j_ec2_state = find_ec2_instance_by_ip(neo4j_host)
        if neo4j_instance_id:
            if neo4j_ec2_state != 'running':
                preview['actions'].append({
                    'type': 'start_ec2',
                    'resource': 'neo4j',
                    'instance_id': neo4j_instance_id,
                    'host': neo4j_host,
                    'current_state': neo4j_ec2_state,
                    'target_state': 'running'
                })
                preview['summary']['ec2_instances_to_start'] += 1
        else:
            preview['warnings'].append(f'Neo4j host {neo4j_host} - no EC2 instance found')
    
    # STEP 2: Check NodeGroup scaling
    nodegroup_defaults = get_nodegroup_defaults(app_name)
    if nodegroup_defaults:
        nodegroup_name = nodegroup_defaults['nodegroup']
        desired_size = nodegroup_defaults['desired']
        min_size = nodegroup_defaults['min']
        max_size = nodegroup_defaults['max']
        
        try:
            response = eks.describe_nodegroup(
                clusterName=EKS_CLUSTER_NAME,
                nodegroupName=nodegroup_name
            )
            current_config = response['nodegroup'].get('scalingConfig', {})
            current_desired = current_config.get('desiredSize', 0)
            current_min = current_config.get('minSize', 0)
            current_max = current_config.get('maxSize', 0)
            
            if current_desired != desired_size or current_min != min_size or current_max != max_size:
                preview['actions'].append({
                    'type': 'scale_nodegroup',
                    'nodegroup': nodegroup_name,
                    'current_desired': current_desired,
                    'current_min': current_min,
                    'current_max': current_max,
                    'target_desired': desired_size,
                    'target_min': min_size,
                    'target_max': max_size
                })
                preview['summary']['nodegroups_to_scale'] += 1
        except Exception as e:
            preview['warnings'].append(f'Could not check NodeGroup {nodegroup_name}: {str(e)}')
    
    # STEP 3: Check Deployments and StatefulSets
    try:
        load_k8s_config()
        if k8s_client:
            apps_v1 = k8s_client.AppsV1Api()
            
            # Check Deployments
            deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
            for deploy in deployments.items:
                current_replicas = deploy.spec.replicas or 0
                target_replicas = max(1, current_replicas)
                
                if current_replicas != target_replicas:
                    preview['actions'].append({
                        'type': 'scale_deployment',
                        'name': deploy.metadata.name,
                        'namespace': namespace,
                        'current_replicas': current_replicas,
                        'target_replicas': target_replicas
                    })
                    preview['summary']['deployments_to_scale'] += 1
            
            # Check StatefulSets
            statefulsets = apps_v1.list_namespaced_stateful_set(namespace=namespace)
            for sts in statefulsets.items:
                current_replicas = sts.spec.replicas or 0
                target_replicas = max(1, current_replicas)
                
                if current_replicas != target_replicas:
                    preview['actions'].append({
                        'type': 'scale_statefulset',
                        'name': sts.metadata.name,
                        'namespace': namespace,
                        'current_replicas': current_replicas,
                        'target_replicas': target_replicas
                    })
                    preview['summary']['statefulsets_to_scale'] += 1
    except Exception as e:
        preview['warnings'].append(f'Could not check Kubernetes workloads: {str(e)}')
    
    preview['summary']['warnings'] = len(preview['warnings'])
    
    return preview

def start_application(app_name, desired_node_count=None, dry_run=False):
    """
    START APPLICATION workflow - EXACT ORDER:
    STEP 1: Check Postgres & Neo4j EC2 states
    STEP 2: Start DB EC2 instances IF stopped (wait until running)
    STEP 3: Scale NodeGroup(s) UP to default values
    STEP 4: Wait for NodeGroup to be ACTIVE
    STEP 5: Scale Deployments & StatefulSets UP (max(1, current_replicas))
    
    Args:
        app_name: Application name
        desired_node_count: Ignored - always uses defaults mapping
        dry_run: If True, return preview without executing
    
    Note: desired_node_count parameter is ignored - always uses defaults mapping
    """
    # If dry_run, return preview only
    if dry_run:
        print("="*70)
        print(f"🔍 DRY RUN: PREVIEW START ACTIONS FOR {app_name}")
        print("="*70)
        return build_start_preview(app_name)
    
    print("="*70)
    print(f"🚀 STARTING APPLICATION: {app_name}")
    print("="*70)
    
    # Fetch metadata from DynamoDB
    app_data = get_app_from_registry(app_name)
    if not app_data:
        return {
            'success': False,
            'error': f'Application {app_name} not found in registry'
        }
    
    namespace = app_data.get('namespace', 'default')
    postgres_host = app_data.get('postgres_host')
    neo4j_host = app_data.get('neo4j_host')
    
    # Initialize DynamoDB table
    table = dynamodb.Table(TABLE_NAME)
    
    # Initialize results
    results = {
        'app': app_name,
        'status': 'starting',
        'details': {
            'db_start': 'skipped',
            'nodegroup_start': 'pending',
            'pods_scale': 'pending'
        },
        'errors': []
    }
    
    # STEP 1: Check Postgres & Neo4j EC2 states
    print("\n" + "="*70)
    print("STEP 1: CHECKING POSTGRES & NEO4J EC2 STATES")
    print("="*70)
    
    postgres_instance_id = None
    postgres_ec2_state = None
    neo4j_instance_id = None
    neo4j_ec2_state = None
    
    # Check Postgres EC2 state
    if postgres_host:
        postgres_instance_id, postgres_ec2_state = find_ec2_instance_by_ip(postgres_host)
        if postgres_instance_id:
            print(f"   ✅ PostgreSQL: Found instance {postgres_instance_id} ({postgres_host}) - State: {postgres_ec2_state.upper()}")
        else:
            print(f"   ⚠️  PostgreSQL: No EC2 instance found for {postgres_host}")
    else:
        print(f"   ℹ️  No PostgreSQL host configured")
    
    # Check Neo4j EC2 state
    if neo4j_host:
        neo4j_instance_id, neo4j_ec2_state = find_ec2_instance_by_ip(neo4j_host)
        if neo4j_instance_id:
            print(f"   ✅ Neo4j: Found instance {neo4j_instance_id} ({neo4j_host}) - State: {neo4j_ec2_state.upper()}")
        else:
            print(f"   ⚠️  Neo4j: No EC2 instance found for {neo4j_host}")
    else:
        print(f"   ℹ️  No Neo4j host configured")
    
    # STEP 2: Start DB EC2 instances IF they are stopped
    print("\n" + "="*70)
    print("STEP 2: STARTING DB EC2 INSTANCES (IF STOPPED)")
    print("="*70)
    
    db_started = False
    
    # Start Postgres if stopped
    if postgres_instance_id:
        if postgres_ec2_state == 'running':
            print(f"   ✅ PostgreSQL EC2 instance {postgres_instance_id} is already RUNNING - skipping start")
            # Update state in DynamoDB
            try:
                table.update_item(
                    Key={'app_name': app_name},
                    UpdateExpression='SET postgres_state = :state',
                    ExpressionAttributeValues={':state': 'running'}
                )
            except Exception as e:
                print(f"   ⚠️  Failed to update postgres_state: {str(e)}")
        else:
            print(f"   🔄 Starting PostgreSQL EC2 instance {postgres_instance_id}...")
            try:
                # Update state to "starting"
                try:
                    table.update_item(
                        Key={'app_name': app_name},
                        UpdateExpression='SET postgres_state = :state',
                        ExpressionAttributeValues={':state': 'starting'}
                    )
                except Exception as e:
                    print(f"   ⚠️  Failed to update postgres_state: {str(e)}")
                
                instance_info = start_ec2_instance(postgres_instance_id)
                if instance_info.get('state') == 'running':
                    print(f"   ✅ PostgreSQL EC2 instance {postgres_instance_id} is now RUNNING")
                    db_started = True
                    # Update state in DynamoDB
                    try:
                        table.update_item(
                            Key={'app_name': app_name},
                            UpdateExpression='SET postgres_state = :state',
                            ExpressionAttributeValues={':state': 'running'}
                        )
                    except Exception as e:
                        print(f"   ⚠️  Failed to update postgres_state: {str(e)}")
                else:
                    error_msg = f"PostgreSQL EC2 instance {postgres_instance_id} failed to start"
                    print(f"   ❌ {error_msg}")
                    results['errors'].append(error_msg)
            except Exception as e:
                error_msg = f"Failed to start PostgreSQL {postgres_instance_id}: {str(e)}"
                print(f"   ❌ {error_msg}")
                results['errors'].append(error_msg)
    
    # Start Neo4j if stopped
    if neo4j_instance_id:
        if neo4j_ec2_state == 'running':
            print(f"   ✅ Neo4j EC2 instance {neo4j_instance_id} is already RUNNING - skipping start")
            # Update state in DynamoDB
            try:
                table.update_item(
                    Key={'app_name': app_name},
                    UpdateExpression='SET neo4j_state = :state',
                    ExpressionAttributeValues={':state': 'running'}
                )
            except Exception as e:
                print(f"   ⚠️  Failed to update neo4j_state: {str(e)}")
        else:
            print(f"   🔄 Starting Neo4j EC2 instance {neo4j_instance_id}...")
            try:
                # Update state to "starting"
                try:
                    table.update_item(
                        Key={'app_name': app_name},
                        UpdateExpression='SET neo4j_state = :state',
                        ExpressionAttributeValues={':state': 'starting'}
                    )
                except Exception as e:
                    print(f"   ⚠️  Failed to update neo4j_state: {str(e)}")
                
                instance_info = start_ec2_instance(neo4j_instance_id)
                if instance_info.get('state') == 'running':
                    print(f"   ✅ Neo4j EC2 instance {neo4j_instance_id} is now RUNNING")
                    db_started = True
                    # Update state in DynamoDB
                    try:
                        table.update_item(
                            Key={'app_name': app_name},
                            UpdateExpression='SET neo4j_state = :state',
                            ExpressionAttributeValues={':state': 'running'}
                        )
                    except Exception as e:
                        print(f"   ⚠️  Failed to update neo4j_state: {str(e)}")
                else:
                    error_msg = f"Neo4j EC2 instance {neo4j_instance_id} failed to start"
                    print(f"   ❌ {error_msg}")
                    results['errors'].append(error_msg)
            except Exception as e:
                error_msg = f"Failed to start Neo4j {neo4j_instance_id}: {str(e)}"
                print(f"   ❌ {error_msg}")
                results['errors'].append(error_msg)
    
    if db_started:
        results['details']['db_start'] = 'done'
    else:
        results['details']['db_start'] = 'skipped'
    
    # STEP 3: Scale NodeGroup(s) UP to default values
    print("\n" + "="*70)
    print("STEP 3: SCALING NODEGROUP(S) UP TO DEFAULT VALUES")
    print("="*70)
    
    # Validate EKS_CLUSTER_NAME
    if not EKS_CLUSTER_NAME:
        error_msg = "EKS_CLUSTER_NAME environment variable is not set!"
        print(f"   ❌ {error_msg}")
        results['errors'].append(error_msg)
        results['details']['nodegroup_start'] = 'failed'
        return results
    
    # Get NodeGroup defaults from authoritative mapping
    nodegroup_defaults = get_nodegroup_defaults(app_name)
    print(f"   📋 NodeGroup defaults lookup for {app_name}: {nodegroup_defaults}")
    
    if nodegroup_defaults is None:
        print(f"   ℹ️  No NodeGroup assigned for {app_name} - skipping NodeGroup scaling")
        results['details']['nodegroup_start'] = 'skipped'
    else:
        nodegroup_name = nodegroup_defaults['nodegroup']
        desired_size = nodegroup_defaults['desired']
        min_size = nodegroup_defaults['min']
        max_size = nodegroup_defaults['max']
        
        print(f"   📋 Using defaults from mapping:")
        print(f"      NodeGroup: {nodegroup_name}")
        print(f"      Desired: {desired_size}, Min: {min_size}, Max: {max_size}")
        print(f"      Cluster: {EKS_CLUSTER_NAME}")
        
        # First, verify NodeGroup exists
        nodegroup_exists = False
        current_desired = 0
        current_min = 0
        current_max = 0
        current_status = 'UNKNOWN'
        
        try:
            print(f"   🔍 Verifying NodeGroup {nodegroup_name} exists...")
            describe_response = eks.describe_nodegroup(
                clusterName=EKS_CLUSTER_NAME,
                nodegroupName=nodegroup_name
            )
            current_config = describe_response['nodegroup'].get('scalingConfig', {})
            current_desired = current_config.get('desiredSize', 0)
            current_min = current_config.get('minSize', 0)
            current_max = current_config.get('maxSize', 0)
            current_status = describe_response['nodegroup'].get('status', 'UNKNOWN')
            nodegroup_exists = True
            print(f"   ✅ NodeGroup {nodegroup_name} exists")
            print(f"      Current: Desired={current_desired}, Min={current_min}, Max={current_max}, Status={current_status}")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'ResourceNotFoundException':
                error_msg = f"NodeGroup {nodegroup_name} does not exist in cluster {EKS_CLUSTER_NAME}"
                print(f"   ❌ {error_msg}")
                print(f"   ⚠️  This application is configured to use NodeGroup {nodegroup_name}, but it doesn't exist.")
                print(f"   ⚠️  The application will start without NodeGroup scaling (pods only).")
                results['warnings'] = results.get('warnings', [])
                results['warnings'].append(error_msg)
                results['details']['nodegroup_start'] = 'skipped'
                nodegroup_exists = False
            else:
                error_msg = f"Failed to verify NodeGroup {nodegroup_name}: {error_code} - {str(e)}"
                print(f"   ❌ {error_msg}")
                import traceback
                traceback.print_exc()
                results['errors'].append(error_msg)
                results['details']['nodegroup_start'] = 'failed'
                nodegroup_exists = False
        except Exception as e:
            error_msg = f"Unexpected error checking NodeGroup {nodegroup_name}: {str(e)}"
            print(f"   ❌ {error_msg}")
            import traceback
            traceback.print_exc()
            results['errors'].append(error_msg)
            results['details']['nodegroup_start'] = 'failed'
            nodegroup_exists = False
        
        # Only proceed with scaling if NodeGroup exists
        if nodegroup_exists:
            # Check if scaling is needed
            if current_desired == desired_size and current_min == min_size and current_max == max_size:
                print(f"   ℹ️  NodeGroup {nodegroup_name} already at target size - skipping scaling")
                results['details']['nodegroup_start'] = 'skipped'
            else:
                # Update component state to "scaling"
                try:
                    table.update_item(
                        Key={'app_name': app_name},
                        UpdateExpression='SET nodegroup_state = :state',
                        ExpressionAttributeValues={':state': 'scaling'}
                    )
                    print(f"   ✅ Updated DynamoDB: nodegroup_state = 'scaling'")
                except Exception as e:
                    print(f"   ⚠️  Failed to update nodegroup_state: {str(e)}")
                
                # Scale NodeGroup
                try:
                    print(f"   🔄 Scaling NodeGroup {nodegroup_name}...")
                    print(f"      From: Desired={current_desired}, Min={current_min}, Max={current_max}")
                    print(f"      To:   Desired={desired_size}, Min={min_size}, Max={max_size}")
                    
                    update_response = eks.update_nodegroup_config(
                        clusterName=EKS_CLUSTER_NAME,
                        nodegroupName=nodegroup_name,
                        scalingConfig={
                            'desiredSize': desired_size,
                            'minSize': min_size,
                            'maxSize': max_size
                        }
                    )
                    print(f"   ✅ NodeGroup {nodegroup_name} scaling command sent successfully")
                    print(f"      Update ID: {update_response.get('update', {}).get('id', 'N/A')}")
                    results['details']['nodegroup_start'] = 'done'
                except ClientError as e:
                    error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                    error_msg = e.response.get('Error', {}).get('Message', str(e))
                    full_error = f"Failed to scale NodeGroup {nodegroup_name}: {error_code} - {error_msg}"
                    print(f"   ❌ {full_error}")
                    import traceback
                    traceback.print_exc()
                    results['errors'].append(full_error)
                    results['details']['nodegroup_start'] = 'failed'
                except Exception as e:
                    error_msg = f"Failed to scale NodeGroup {nodegroup_name}: {str(e)}"
                    print(f"   ❌ {error_msg}")
                    import traceback
                    traceback.print_exc()
                    results['errors'].append(error_msg)
                    results['details']['nodegroup_start'] = 'failed'
    
    # STEP 4: Wait for NodeGroup to be ACTIVE
    # Only wait if NodeGroup exists AND scaling was successful
    if nodegroup_defaults is not None and results['details']['nodegroup_start'] == 'done':
        print("\n" + "="*70)
        print("STEP 4: WAITING FOR NODEGROUP TO BE ACTIVE")
        print("="*70)
        
        nodegroup_name = nodegroup_defaults['nodegroup']
        desired_size = nodegroup_defaults['desired']
        max_wait = 600  # 10 minutes
        wait_interval = 15  # Check every 15 seconds
        elapsed = 0
        
        print(f"   ⏳ Waiting for NodeGroup {nodegroup_name} to reach ACTIVE status...")
        print(f"   📋 Target: {desired_size} nodes, Status: ACTIVE")
        print(f"   ⏱️  Max wait time: {max_wait}s")
        
        while elapsed < max_wait:
            try:
                response = eks.describe_nodegroup(
                    clusterName=EKS_CLUSTER_NAME,
                    nodegroupName=nodegroup_name
                )
                ng = response['nodegroup']
                status = ng.get('status', 'UNKNOWN')
                scaling_config = ng.get('scalingConfig', {})
                current_desired = scaling_config.get('desiredSize', 0)
                resources = ng.get('resources', {})
                instance_groups = resources.get('remoteAccessSecurityGroups', [])
                
                # Count actual nodes
                node_count = len(resources.get('autoScalingGroups', []))
                
                print(f"   ⏳ [{elapsed}s] Status: {status}, Desired: {current_desired}/{desired_size}, Nodes: {node_count}")
                
                if status == 'ACTIVE' and current_desired >= desired_size:
                    print(f"   ✅ NodeGroup {nodegroup_name} is ACTIVE with {current_desired} nodes (target: {desired_size})")
                    # Update component state to "ready"
                    try:
                        table.update_item(
                            Key={'app_name': app_name},
                            UpdateExpression='SET nodegroup_state = :state',
                            ExpressionAttributeValues={':state': 'ready'}
                        )
                        print(f"   ✅ Updated DynamoDB: nodegroup_state = 'ready'")
                    except Exception as e:
                        print(f"   ⚠️  Failed to update nodegroup_state: {str(e)}")
                    break
                elif status in ['UPDATING', 'CREATING']:
                    print(f"   ⏳ NodeGroup is {status}... waiting...")
                elif status in ['DEGRADED', 'UPDATE_FAILED', 'CREATE_FAILED']:
                    error_msg = f"NodeGroup {nodegroup_name} is in {status} state"
                    print(f"   ⚠️  {error_msg}")
                    results['errors'].append(error_msg)
                    break
                
                time.sleep(wait_interval)
                elapsed += wait_interval
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_msg = f"Error checking NodeGroup status: {error_code} - {str(e)}"
                print(f"   ⚠️  {error_msg}")
                time.sleep(wait_interval)
                elapsed += wait_interval
            except Exception as e:
                error_msg = f"Unexpected error checking NodeGroup status: {str(e)}"
                print(f"   ⚠️  {error_msg}")
                import traceback
                traceback.print_exc()
                time.sleep(wait_interval)
                elapsed += wait_interval
        
        if elapsed >= max_wait:
            warning_msg = f"Timeout waiting for NodeGroup {nodegroup_name} to be ACTIVE (waited {max_wait}s)"
            print(f"   ⚠️  {warning_msg}")
            results['warnings'] = results.get('warnings', [])
            results['warnings'].append(warning_msg)
    elif nodegroup_defaults is not None and results['details']['nodegroup_start'] == 'skipped':
        print("\n" + "="*70)
        print("STEP 4: SKIPPED (NodeGroup scaling was skipped)")
        print("="*70)
        print(f"   ℹ️  NodeGroup scaling was skipped - proceeding to pod scaling")
    else:
        print("\n" + "="*70)
        print("STEP 4: SKIPPED (No NodeGroup assigned)")
        print("="*70)
        print(f"   ℹ️  No NodeGroup assigned for {app_name} - proceeding to pod scaling")
    
    # STEP 5: Scale Deployments & StatefulSets UP (max(1, current_replicas))
    print("\n" + "="*70)
    print("STEP 5: SCALING DEPLOYMENTS & STATEFULSETS UP")
    print("="*70)
    print(f"   📋 Namespace: {namespace}")
    
    try:
        print(f"   🔄 Loading Kubernetes configuration...")
        load_k8s_config()
        
        if k8s_client is None:
            error_msg = "Kubernetes client not available - cannot scale workloads"
            print(f"   ❌ {error_msg}")
            print(f"   ⚠️  This may be due to:")
            print(f"      - Missing EKS_CLUSTER_NAME environment variable")
            print(f"      - IAM permissions issue")
            print(f"      - Network connectivity issue")
            results['errors'].append(error_msg)
            results['details']['pods_scale'] = 'failed'
        else:
            print(f"   ✅ Kubernetes client loaded successfully")
            apps_v1 = k8s_client.AppsV1Api()
            core_v1 = k8s_client.CoreV1Api()
            
            # Scale Deployments
            print(f"\n   🔄 Scaling Deployments in namespace: {namespace}")
            try:
                deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
                print(f"   📊 Found {len(deployments.items)} Deployments")
                
                deployment_count = 0
                deployment_errors = []
                for deploy in deployments.items:
                    deploy_name = deploy.metadata.name
                    current_replicas = deploy.spec.replicas or 0
                    target_replicas = max(1, current_replicas)  # Use max(1, current_replicas)
                    
                    if current_replicas == target_replicas:
                        print(f"   ℹ️  Deployment {deploy_name}: Already at {target_replicas} replicas - skipping")
                        continue
                    
                    try:
                        apps_v1.patch_namespaced_deployment_scale(
                            name=deploy_name,
                            namespace=namespace,
                            body={'spec': {'replicas': target_replicas}}
                        )
                        deployment_count += 1
                        print(f"   ✅ Scaled Deployment: {deploy_name} from {current_replicas} → {target_replicas} replicas")
                    except Exception as e:
                        error_msg = f"Failed to scale Deployment {deploy_name}: {str(e)}"
                        print(f"   ⚠️  {error_msg}")
                        deployment_errors.append(error_msg)
                
                if deployment_errors:
                    results['warnings'] = results.get('warnings', [])
                    results['warnings'].extend(deployment_errors)
                
                print(f"   ✅ Scaled {deployment_count} Deployments")
            except Exception as e:
                error_msg = f"Failed to list/scale Deployments: {str(e)}"
                print(f"   ❌ {error_msg}")
                import traceback
                traceback.print_exc()
                results['errors'].append(error_msg)
            
            # Scale StatefulSets
            print(f"\n   🔄 Scaling StatefulSets in namespace: {namespace}")
            try:
                statefulsets = apps_v1.list_namespaced_stateful_set(namespace=namespace)
                print(f"   📊 Found {len(statefulsets.items)} StatefulSets")
                
                statefulset_count = 0
                statefulset_errors = []
                for sts in statefulsets.items:
                    sts_name = sts.metadata.name
                    current_replicas = sts.spec.replicas or 0
                    target_replicas = max(1, current_replicas)  # Use max(1, current_replicas)
                    
                    if current_replicas == target_replicas:
                        print(f"   ℹ️  StatefulSet {sts_name}: Already at {target_replicas} replicas - skipping")
                        continue
                    
                    try:
                        apps_v1.patch_namespaced_stateful_set_scale(
                            name=sts_name,
                            namespace=namespace,
                            body={'spec': {'replicas': target_replicas}}
                        )
                        statefulset_count += 1
                        print(f"   ✅ Scaled StatefulSet: {sts_name} from {current_replicas} → {target_replicas} replicas")
                    except Exception as e:
                        error_msg = f"Failed to scale StatefulSet {sts_name}: {str(e)}"
                        print(f"   ⚠️  {error_msg}")
                        statefulset_errors.append(error_msg)
                
                if statefulset_errors:
                    results['warnings'] = results.get('warnings', [])
                    results['warnings'].extend(statefulset_errors)
                
                print(f"   ✅ Scaled {statefulset_count} StatefulSets")
            except Exception as e:
                error_msg = f"Failed to list/scale StatefulSets: {str(e)}"
                print(f"   ❌ {error_msg}")
                import traceback
                traceback.print_exc()
                results['errors'].append(error_msg)
            
            # Check pod status
            print(f"\n   📊 Checking pod status in namespace: {namespace}")
            try:
                pods = core_v1.list_namespaced_pod(namespace=namespace)
                running_pods = sum(1 for p in pods.items if p.status.phase == 'Running')
                pending_pods = sum(1 for p in pods.items if p.status.phase == 'Pending')
                total_pods = len(pods.items)
                print(f"   📈 Pods: {running_pods} Running, {pending_pods} Pending, {total_pods} Total")
            except Exception as e:
                print(f"   ⚠️  Could not check pod status: {str(e)}")
            
            if deployment_count > 0 or statefulset_count > 0:
                results['details']['pods_scale'] = 'done'
            else:
                results['details']['pods_scale'] = 'skipped'
                print(f"   ℹ️  No workloads needed scaling")
    except Exception as e:
        error_msg = f"Failed to scale Kubernetes workloads: {str(e)}"
        print(f"   ❌ {error_msg}")
        import traceback
        traceback.print_exc()
        results['errors'].append(error_msg)
        results['details']['pods_scale'] = 'failed'
    
    # Determine overall success
    results['success'] = len(results['errors']) == 0
    if results['success']:
        results['status'] = 'started'
    else:
        results['status'] = 'failed'
    
    print("\n" + "="*70)
    print(f"{'✅ SUCCESS' if results['success'] else '⚠️  COMPLETED WITH ERRORS'}")
    print("="*70)
    
    return results

def wait_for_pods_terminated(namespace, timeout=300):
    """
    Wait for all pods in a namespace to terminate gracefully.
    Returns True if all pods terminated, False if timeout.
    """
    load_k8s_config()
    
    if k8s_client is None:
        print("⚠️  Kubernetes client not available, skipping pod termination check")
        return False
    
    print(f"⏳ Waiting for pods to terminate gracefully in namespace: {namespace}")
    
    elapsed = 0
    check_interval = 5  # Check every 5 seconds
    
    while elapsed < timeout:
        try:
            core_v1 = k8s_client.CoreV1Api()
            pods = core_v1.list_namespaced_pod(namespace=namespace)
            
            # Count pods that are not in terminal states
            running_pods = []
            for pod in pods.items:
                phase = pod.status.phase
                # Terminal states: Succeeded, Failed
                # Non-terminal: Pending, Running, Unknown
                if phase not in ['Succeeded', 'Failed']:
                    running_pods.append({
                        'name': pod.metadata.name,
                        'phase': phase
                    })
            
            if len(running_pods) == 0:
                print(f"   ✅ All pods terminated gracefully")
                return True
            
            print(f"   ⏳ Waiting for {len(running_pods)} pods to terminate... ({elapsed}s/{timeout}s)")
            if len(running_pods) <= 5:  # Show details if few pods
                for pod in running_pods:
                    print(f"      • {pod['name']}: {pod['phase']}")
            
            time.sleep(check_interval)
            elapsed += check_interval
        except Exception as e:
            print(f"   ⚠️  Error checking pod status: {str(e)}")
            time.sleep(check_interval)
            elapsed += check_interval
    
    print(f"   ⚠️  Timeout waiting for pods to terminate (waited {timeout}s)")
    return False

def stop_application(app_name):
    """
    STOP APPLICATION workflow - GRACEFUL SHUTDOWN:
    1. Scale ALL Deployments in namespace to 0
    2. Scale ALL StatefulSets in namespace to 0
    3. Wait for pods to terminate gracefully
    4. Scale NodeGroup: desired=0, min=0, max=unchanged
    5. Stop EC2 instances (Postgres, Neo4j)
    """
    print("="*70)
    print(f"🛑 STOPPING APPLICATION: {app_name}")
    print("="*70)
    
    app_data = get_app_from_registry(app_name)
    if not app_data:
        return {
            'success': False,
            'error': f'Application {app_name} not found in registry'
        }
    
    namespace = app_data.get('namespace', 'default')
    
    # Initialize DynamoDB table
    table = dynamodb.Table(TABLE_NAME)
    
    # Check for shared resources
    blocking = check_shared_resources_blocking(app_data)
    
    results = {
        'app_name': app_name,
        'namespace': namespace,
        'step1_deployments': [],
        'step2_statefulsets': [],
        'step3_pods_terminated': False,
        'step4_nodegroups': [],
        'postgres': [],
        'neo4j': [],
        'warnings': [],
        'errors': []
    }
    
    # Add warnings for shared resources
    for block in blocking:
        results['warnings'].append(block['message'])
    
    # STEP 1: Scale ALL Deployments and StatefulSets to 0
    print("\n" + "="*70)
    print("STEP 1: SCALING ALL DEPLOYMENTS & STATEFULSETS TO 0")
    print("="*70)
    try:
        workload_results = scale_kubernetes_workloads(namespace, replicas=0)
        results['step1_deployments'] = workload_results.get('deployments', [])
        results['step2_statefulsets'] = workload_results.get('statefulsets', [])
        print(f"   ✅ Scaled {len(results['step1_deployments'])} Deployments to 0")
        print(f"   ✅ Scaled {len(results['step2_statefulsets'])} StatefulSets to 0")
    except Exception as e:
        error_msg = f"Failed to scale Kubernetes workloads: {str(e)}"
        print(f"   ❌ {error_msg}")
        results['errors'].append(error_msg)
    
    # STEP 2: Wait for pods to terminate gracefully
    print("\n" + "="*70)
    print("STEP 2: WAITING FOR PODS TO TERMINATE GRACEFULLY")
    print("="*70)
    pods_terminated = wait_for_pods_terminated(namespace, timeout=300)
    results['step3_pods_terminated'] = pods_terminated
    
    if not pods_terminated:
        print(f"   ⚠️  Some pods may still be terminating, but proceeding with shutdown")
        results['warnings'].append('Some pods may not have terminated gracefully')
    
    # STEP 3: Scale NodeGroup DOWN (if assigned)
    print("\n" + "="*70)
    print("STEP 3: SCALING NODEGROUP DOWN")
    print("="*70)
    
    # Get NodeGroup defaults from mapping
    nodegroup_defaults = get_nodegroup_defaults(app_name)
    
    if nodegroup_defaults is None:
        print(f"   ℹ️  No NodeGroup assigned for {app_name} - skipping NodeGroup scaling")
    else:
        nodegroup_name = nodegroup_defaults['nodegroup']
        
        # Get current max to preserve it
        try:
            response = eks.describe_nodegroup(
                clusterName=EKS_CLUSTER_NAME,
                nodegroupName=nodegroup_name
            )
            current_max = response['nodegroup'].get('scalingConfig', {}).get('maxSize', 2)
        except Exception as e:
            print(f"   ⚠️  Failed to get current max for NodeGroup: {str(e)}")
            current_max = nodegroup_defaults.get('max', 2)
        
        try:
            print(f"   🔄 Scaling NodeGroup {nodegroup_name}: desired=0, min=0, max={current_max} (unchanged)")
            ng_result = scale_nodegroup(
                EKS_CLUSTER_NAME,
                nodegroup_name,
                desired_capacity=0,
                min_size=0,
                max_size=current_max  # Keep max unchanged
            )
            results['step4_nodegroups'].append({
                'name': nodegroup_name,
                'desired_size': 0,
                'min_size': 0,
                'max_size': current_max,
                'status': 'scaled_down'
            })
            print(f"   ✅ NodeGroup {nodegroup_name} scaled down")
        except Exception as e:
            error_msg = f"Failed to scale nodegroup {nodegroup_name}: {str(e)}"
            print(f"   ❌ {error_msg}")
            results['errors'].append(error_msg)
    
    # Update nodegroup_state to "stopped"
    try:
        table = dynamodb.Table(TABLE_NAME)
        table.update_item(
            Key={'app_name': app_name},
            UpdateExpression='SET nodegroup_state = :state',
            ExpressionAttributeValues={':state': 'stopped'}
        )
    except Exception as e:
        print(f"⚠️  Failed to update nodegroup_state: {str(e)}")
    
    # STEP 4: Stop PostgreSQL instances (handle shared vs dedicated)
    print("\n" + "="*70)
    print("STEP 4: STOPPING POSTGRESQL INSTANCES")
    print("="*70)
    
    postgres_host = app_data.get('postgres_host')
    postgres_shared = is_database_shared(app_data, 'postgres')
    
    stopped_pg_count = 0
    if postgres_host:
        if postgres_shared:
            print(f"   ℹ️  PostgreSQL {postgres_host} is SHARED - checking if other apps are UP...")
            # Special case: Stop shared DB only if ALL other apps using it are DOWN
            if is_shared_resource_in_use(postgres_host, 'postgres', app_name):
                print(f"   ⚠️  Shared PostgreSQL {postgres_host} is in use by active applications - SKIPPING STOP")
                results['warnings'].append(f"PostgreSQL {postgres_host} is shared with active applications - database NOT stopped")
            else:
                print(f"   🔄 Shared PostgreSQL {postgres_host} is NOT in use - stopping EC2 instance...")
                # Find EC2 instance by private IP
                try:
                    filters = [
                        {'Name': 'private-ip-address', 'Values': [postgres_host]},
                        {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                    ]
                    response = ec2.describe_instances(Filters=filters)
                    for reservation in response.get('Reservations', []):
                        for instance in reservation.get('Instances', []):
                            instance_id = instance['InstanceId']
                            try:
                                stop_ec2_instance(instance_id)
                                results['postgres'].append({
                                    'host': postgres_host,
                                    'status': 'stopping',
                                    'shared': True,
                                    'reason': 'No other apps using shared resource'
                                })
                                stopped_pg_count += 1
                                print(f"   ✅ Stopped unused shared PostgreSQL instance")
                            except Exception as e:
                                results['errors'].append(f"Failed to stop postgres {postgres_host}: {str(e)}")
                except Exception as e:
                    results['errors'].append(f"Failed to find postgres instance for {postgres_host}: {str(e)}")
        else:
            print(f"   🔄 PostgreSQL is DEDICATED - stopping EC2 instance...")
            # Find EC2 instance by private IP
            try:
                filters = [
                    {'Name': 'private-ip-address', 'Values': [postgres_host]},
                    {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                ]
                response = ec2.describe_instances(Filters=filters)
                for reservation in response.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        instance_id = instance['InstanceId']
                        try:
                            stop_ec2_instance(instance_id)
                            results['postgres'].append({
                                'host': postgres_host,
                                'status': 'stopping',
                                'shared': False
                            })
                            stopped_pg_count += 1
                            print(f"   ✅ Stopped dedicated PostgreSQL instance")
                        except Exception as e:
                            results['errors'].append(f"Failed to stop postgres {postgres_host}: {str(e)}")
            except Exception as e:
                results['errors'].append(f"Failed to find postgres instance for {postgres_host}: {str(e)}")
    
    # Update postgres_state to "stopped" if any were stopped
    if stopped_pg_count > 0:
        try:
            table = dynamodb.Table(TABLE_NAME)
            table.update_item(
                Key={'app_name': app_name},
                UpdateExpression='SET postgres_state = :state',
                ExpressionAttributeValues={':state': 'stopped'}
            )
        except Exception as e:
            print(f"⚠️  Failed to update postgres_state: {str(e)}")
    
    # STEP 5: Stop Neo4j instances (handle shared vs dedicated)
    print("\n" + "="*70)
    print("STEP 5: STOPPING NEO4J INSTANCES")
    print("="*70)
    
    neo4j_host = app_data.get('neo4j_host')
    neo4j_shared = is_database_shared(app_data, 'neo4j')
    
    stopped_neo4j_count = 0
    if neo4j_host:
        if neo4j_shared:
            print(f"   ℹ️  Neo4j {neo4j_host} is SHARED - checking if other apps are UP...")
            # Special case: Stop shared DB only if ALL other apps using it are DOWN
            if is_shared_resource_in_use(neo4j_host, 'neo4j', app_name):
                print(f"   ⚠️  Shared Neo4j {neo4j_host} is in use by active applications - SKIPPING STOP")
                results['warnings'].append(f"Neo4j {neo4j_host} is shared with active applications - database NOT stopped")
            else:
                print(f"   🔄 Shared Neo4j {neo4j_host} is NOT in use - stopping EC2 instance...")
                # Find EC2 instance by private IP
                try:
                    filters = [
                        {'Name': 'private-ip-address', 'Values': [neo4j_host]},
                        {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                    ]
                    response = ec2.describe_instances(Filters=filters)
                    for reservation in response.get('Reservations', []):
                        for instance in reservation.get('Instances', []):
                            instance_id = instance['InstanceId']
                            try:
                                stop_ec2_instance(instance_id)
                                results['neo4j'].append({
                                    'host': neo4j_host,
                                    'status': 'stopping',
                                    'shared': True,
                                    'reason': 'No other apps using shared resource'
                                })
                                stopped_neo4j_count += 1
                                print(f"   ✅ Stopped unused shared Neo4j instance")
                            except Exception as e:
                                results['errors'].append(f"Failed to stop neo4j {neo4j_host}: {str(e)}")
                except Exception as e:
                    results['errors'].append(f"Failed to find neo4j instance for {neo4j_host}: {str(e)}")
        else:
            print(f"   🔄 Neo4j is DEDICATED - stopping EC2 instance...")
            # Find EC2 instance by private IP
            try:
                filters = [
                    {'Name': 'private-ip-address', 'Values': [neo4j_host]},
                    {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                ]
                response = ec2.describe_instances(Filters=filters)
                for reservation in response.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        instance_id = instance['InstanceId']
                        try:
                            stop_ec2_instance(instance_id)
                            results['neo4j'].append({
                                'host': neo4j_host,
                                'status': 'stopping',
                                'shared': False
                            })
                            stopped_neo4j_count += 1
                            print(f"   ✅ Stopped dedicated Neo4j instance")
                        except Exception as e:
                            results['errors'].append(f"Failed to stop neo4j {neo4j_host}: {str(e)}")
            except Exception as e:
                results['errors'].append(f"Failed to find neo4j instance for {neo4j_host}: {str(e)}")
    
    # Update neo4j_state to "stopped" if any were stopped
    if stopped_neo4j_count > 0:
        try:
            table = dynamodb.Table(TABLE_NAME)
            table.update_item(
                Key={'app_name': app_name},
                UpdateExpression='SET neo4j_state = :state',
                ExpressionAttributeValues={':state': 'stopped'}
            )
        except Exception as e:
            print(f"⚠️  Failed to update neo4j_state: {str(e)}")
    
    # Update registry status
    try:
        table = dynamodb.Table(TABLE_NAME)
        table.update_item(
            Key={'app_name': app_name},
            UpdateExpression='SET #status = :status, final_app_status = :final_status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'DOWN',
                ':final_status': 'DOWN'
            }
        )
    except Exception as e:
        print(f"⚠️  Failed to update status: {str(e)}")
    
    results['success'] = len(results['errors']) == 0
    return results

def update_app_status(app_name, status):
    """Update application status in registry."""
    table = dynamodb.Table(TABLE_NAME)
    
    try:
        table.update_item(
            Key={'app_name': app_name},
            UpdateExpression='SET #status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': status}
        )
    except Exception as e:
        print(f"Error updating status for {app_name}: {str(e)}")

def lambda_handler(event, context):
    """
    Main Lambda handler for start/stop operations.
    Supports both synchronous (API Gateway) and asynchronous (self-invocation) calls.
    """
    print("="*70)
    print("🚀 CONTROLLER LAMBDA INVOKED")
    print("="*70)
    print(f"Event type: {type(event)}")
    print(f"Event keys: {list(event.keys()) if isinstance(event, dict) else 'N/A'}")
    print(f"Event (first 500 chars): {str(event)[:500]}")
    print("="*70)
    
    # Validate EKS_CLUSTER_NAME
    if not EKS_CLUSTER_NAME:
        error_msg = "❌ CRITICAL: EKS_CLUSTER_NAME environment variable is not set!"
        print(error_msg)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'EKS_CLUSTER_NAME not configured'})
        }
    print(f"✅ EKS_CLUSTER_NAME: {EKS_CLUSTER_NAME}")
    
    # Check if this is an async invocation (from self-invocation)
    if event.get('action') and event.get('async'):
        # This is an async invocation - run the actual operation
        app_name = event.get('app_name')
        action = event.get('action')
        
        print("="*70)
        print(f"🔄 ASYNC INVOCATION DETECTED")
        print(f"   Action: {action}")
        print(f"   App: {app_name}")
        print("="*70)
        
        try:
            if action == 'start':
                print(f"🚀 Starting async start workflow for {app_name}...")
                result = start_application(app_name, desired_node_count=None)
                print(f"✅ Async start operation completed for {app_name}")
                print(f"   Success: {result.get('success', False)}")
                print(f"   Status: {result.get('status', 'unknown')}")
                if result.get('errors'):
                    print(f"   Errors: {result.get('errors')}")
            elif action == 'stop':
                print(f"🛑 Starting async stop workflow for {app_name}...")
                result = stop_application(app_name)
                print(f"✅ Async stop operation completed for {app_name}")
            else:
                error_msg = f"❌ Unknown action: {action}"
                print(error_msg)
                return {'success': False, 'error': error_msg}
            
            print("="*70)
            return result
        except Exception as e:
            import traceback
            error_msg = f"❌ CRITICAL ERROR in async {action} operation for {app_name}: {str(e)}"
            print(error_msg)
            print("="*70)
            print("FULL TRACEBACK:")
            print("="*70)
            traceback.print_exc()
            print("="*70)
            return {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
    
    # This is a synchronous API Gateway call
    # Extract HTTP method and path from event
    http_method = ''
    if 'httpMethod' in event:
        http_method = event.get('httpMethod', '')
    elif 'requestContext' in event:
        request_context = event.get('requestContext', {})
        if isinstance(request_context, dict):
            http_info = request_context.get('http', {})
            if isinstance(http_info, dict):
                http_method = http_info.get('method', '')
    
    path = event.get('path', '')
    if not path and 'requestContext' in event:
        request_context = event.get('requestContext', {})
        if isinstance(request_context, dict):
            http_info = request_context.get('http', {})
            if isinstance(http_info, dict):
                path = http_info.get('path', '')
    
    # Handle OPTIONS requests (CORS preflight)
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Access-Control-Max-Age': '300'
            },
            'body': ''
        }
    
    # Handle API Gateway event body parsing
    body = {}
    if 'body' in event:
        event_body = event.get('body')
        if event_body:
            try:
                if isinstance(event_body, str):
                    if event_body.strip():  # Only parse if not empty
                        body = json.loads(event_body)
                    else:
                        body = {}
                elif isinstance(event_body, dict):
                    body = event_body
                else:
                    body = {}
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"Error parsing body: {str(e)}")
                body = {}
    elif isinstance(event, dict) and 'app_name' in event:
        # Direct invocation (not via API Gateway)
        body = event
    
    # Ensure body is always a dict (never None)
    if not isinstance(body, dict):
        body = {}
    
    # Extract app_name from body or pathParameters
    app_name = body.get('app_name') if body else None
    if not app_name:
        path_params = event.get('pathParameters')
        if path_params and isinstance(path_params, dict):
            app_name = path_params.get('app_name')
    
    if not app_name:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'app_name is required'})
        }
    
    try:
        if http_method == 'POST' and '/start' in path:
            # Check for dry_run parameter (from query string or body)
            query_params = event.get('queryStringParameters') or {}
            dry_run = query_params.get('dry_run', 'false').lower() == 'true' or body.get('dry_run', False)
            
            if dry_run:
                # Dry run - return preview immediately (synchronous)
                preview = build_start_preview(app_name)
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps(preview)
                }
            
            # Actual start - API Gateway has 30s timeout, so we need async execution
            # Invoke Lambda asynchronously to run the actual operation
            lambda_client = boto3.client('lambda')
            function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'eks-app-controller-controller')
            
            print("="*70)
            print("🔄 INVOKING ASYNC START WORKFLOW")
            print("="*70)
            print(f"   Function: {function_name}")
            print(f"   App: {app_name}")
            print(f"   InvocationType: Event (async)")
            
            async_payload = {
                'action': 'start',
                'app_name': app_name,
                'async': True
            }
            print(f"   Payload: {json.dumps(async_payload)}")
            
            try:
                # Invoke asynchronously
                invoke_response = lambda_client.invoke(
                    FunctionName=function_name,
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps(async_payload)
                )
                print(f"   ✅ Async invocation successful")
                print(f"      StatusCode: {invoke_response.get('StatusCode', 'N/A')}")
                print(f"      ResponseMetadata: {invoke_response.get('ResponseMetadata', {})}")
            except Exception as e:
                error_msg = f"Failed to invoke async start workflow: {str(e)}"
                print(f"   ❌ {error_msg}")
                import traceback
                traceback.print_exc()
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': error_msg
                    })
                }
            
            # Return immediately
            return {
                'statusCode': 202,  # Accepted
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': True,
                    'message': f'Start operation initiated for {app_name}. Operation is running in the background.',
                    'app_name': app_name,
                    'status': 'accepted'
                })
            }
        elif http_method == 'POST' and '/stop' in path:
            # API Gateway has 30s timeout, so we need async execution
            lambda_client = boto3.client('lambda')
            function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'eks-app-controller-controller')
            
            # Invoke asynchronously
            lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='Event',  # Async invocation
                Payload=json.dumps({
                    'action': 'stop',
                    'app_name': app_name,
                    'async': True
                })
            )
            
            # Return immediately
            return {
                'statusCode': 202,  # Accepted
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': True,
                    'message': f'Stop operation initiated for {app_name}. Operation is running in the background.',
                    'app_name': app_name,
                    'status': 'accepted'
                })
            }
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Invalid operation'})
            }
    
    except Exception as e:
        print(f"Controller error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }

