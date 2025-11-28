"""
Discovery Lambda Function
Scans Kubernetes Ingress resources to automatically detect applications
and map them to NodeGroups, EC2 database instances, pods, services, and certificates.
"""

import json
import os
import base64
import time
import boto3
from datetime import datetime
from kubernetes import client, config
from botocore.exceptions import ClientError
from botocore.signers import RequestSigner

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ec2 = boto3.client('ec2')
eks_client = boto3.client('eks')
sts = boto3.client('sts')

# DynamoDB table name
TABLE_NAME = os.environ.get('REGISTRY_TABLE_NAME', 'eks-app-registry')
EKS_CLUSTER_NAME = os.environ.get('EKS_CLUSTER_NAME')

# Hard-coded application → namespace mapping (authoritative)
# These values override any auto-discovered or inferred namespaces
APP_NAMESPACE_MAPPING = {
    "ai360.dev.mareana.com": "ai360",
    "ebr.dev.mareana.com": "ebr-dev",
    "flux.dev.mareana.com": "flux-system",
    "grafana.dev.mareana.com": "monitoring",
    "gtag.dev.mareana.com": "gtag-dev",
    "k8s-dashboard.dev.mareana.com": "kubernetes-dashboard",
    "mi-app-airflow.cloud.mareana.com": "mi-app",
    "mi-r1-airflow.dev.mareana.com": "mi-r1-dev",
    "mi-r1-spark.dev.mareana.com": "mi-r1-dev",
    "mi-r1.dev.mareana.com": "mi-r1-dev",
    "mi-spark.dev.mareana.com": "mi-app",
    "mi.dev.mareana.com": "mi-app",
    "prometheus.dev.mareana.com": "monitoring",
    "vsm-bms.dev.mareana.com": "vsm-bms",
    "vsm.dev.mareana.com": "vsm-dev",
    "lab.dev.mareana.com": "lab-dev"
}

def get_namespace_for_app(app_name, discovered_namespace=None):
    """
    Get the correct namespace for an application.
    Uses hard-coded mapping if available, otherwise falls back to discovered namespace.
    
    Args:
        app_name: Application hostname (e.g., "mi.dev.mareana.com")
        discovered_namespace: Namespace discovered from Ingress (fallback)
    
    Returns:
        Correct namespace string
    """
    # Check if app_name is in the mapping
    if app_name in APP_NAMESPACE_MAPPING:
        mapped_namespace = APP_NAMESPACE_MAPPING[app_name]
        if discovered_namespace and discovered_namespace != mapped_namespace:
            print(f"  🔄 Overriding namespace: {discovered_namespace} → {mapped_namespace} (from mapping)")
        return mapped_namespace
    
    # Fallback to discovered namespace
    return discovered_namespace or 'default'

def get_bearer_token(cluster_name):
    """Generate EKS authentication token."""
    STS_TOKEN_EXPIRES_IN = 60
    session = boto3.session.Session()
    client = session.client('sts')
    service_id = client.meta.service_model.service_id

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

def load_k8s_config():
    """Load Kubernetes configuration using AWS EKS authentication."""
    try:
        # Try to load from Lambda environment (if running in EKS)
        config.load_incluster_config()
        print("Loaded in-cluster config")
    except Exception:
        try:
            # Get EKS cluster information
            cluster_info = eks_client.describe_cluster(name=EKS_CLUSTER_NAME)
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
            print(f"Loaded EKS config for cluster: {EKS_CLUSTER_NAME}")
        except Exception as e:
            # Final fallback to kubeconfig (for local testing)
            try:
                config.load_kube_config()
                print("Loaded kubeconfig")
            except Exception:
                raise Exception(f"Unable to load Kubernetes configuration: {str(e)}")

def get_all_ingresses():
    """Scan all namespaces for Ingress resources."""
    v1 = client.NetworkingV1Api()
    ingresses = []
    
    try:
        # Get all namespaces
        core_v1 = client.CoreV1Api()
        namespaces = core_v1.list_namespace()
        
        for ns in namespaces.items:
            try:
                ns_ingresses = v1.list_namespaced_ingress(ns.metadata.name)
                ingresses.extend(ns_ingresses.items)
            except Exception as e:
                print(f"Error listing ingresses in {ns.metadata.name}: {str(e)}")
                continue
    except Exception as e:
        print(f"Error getting namespaces: {str(e)}")
        return []
    
    return ingresses

def extract_hostnames(ingress):
    """Extract hostnames from Ingress resource."""
    hostnames = []
    if ingress.spec and ingress.spec.rules:
        for rule in ingress.spec.rules:
            if rule.host:
                hostnames.append(rule.host)
    return hostnames

def extract_certificate_expiry(ingress):
    """Extract certificate expiry date from Ingress TLS configuration."""
    if not ingress.spec or not ingress.spec.tls:
        return None
    
    # Get TLS secrets
    tls_secrets = []
    for tls in ingress.spec.tls:
        if tls.secret_name:
            tls_secrets.append(tls.secret_name)
    
    if not tls_secrets:
        return None
    
    # Try to get certificate expiry from first secret
    try:
        core_v1 = client.CoreV1Api()
        namespace = ingress.metadata.namespace
        
        for secret_name in tls_secrets:
            try:
                secret = core_v1.read_namespaced_secret(secret_name, namespace)
                if secret.data and 'tls.crt' in secret.data:
                    import ssl
                    import socket
                    from cryptography import x509
                    from cryptography.hazmat.backends import default_backend
                    
                    cert_data = base64.b64decode(secret.data['tls.crt'])
                    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
                    expiry = cert.not_valid_after
                    return expiry.isoformat()
            except Exception as e:
                print(f"Error reading certificate from secret {secret_name}: {str(e)}")
                continue
    except Exception as e:
        print(f"Error extracting certificate expiry: {str(e)}")
    
    return None

def get_nodegroups_for_app(app_name, cluster_name):
    """Find NodeGroups tagged with the application name with enhanced details."""
    nodegroups = []
    
    try:
        # List all nodegroups in the cluster
        response = eks_client.list_nodegroups(clusterName=cluster_name)
        
        for ng_name in response.get('nodegroups', []):
            try:
                ng_details = eks_client.describe_nodegroup(
                    clusterName=cluster_name,
                    nodegroupName=ng_name
                )
                
                tags = ng_details['nodegroup'].get('tags', {})
                if tags.get('AppName') == app_name:
                    nodegroup_info = ng_details['nodegroup']
                    scaling = nodegroup_info.get('scalingConfig', {})
                    
                    # Get node labels from launch template or instance types
                    labels = {}
                    if 'labels' in nodegroup_info:
                        labels = nodegroup_info['labels']
                    
                    # Store only NodeGroup metadata (name, labels, ARN)
                    # DO NOT store scaling values - they will be fetched live from AWS
                    nodegroups.append({
                        'name': ng_name,
                        'labels': labels,
                        'arn': nodegroup_info.get('nodegroupArn', '')
                        # Note: scaling values are NOT stored to avoid stale data
                        # They will be fetched live from AWS EKS by the API Handler
                    })
            except Exception as e:
                print(f"Error describing nodegroup {ng_name}: {str(e)}")
                continue
    except Exception as e:
        print(f"Error listing nodegroups: {str(e)}")
    
    return nodegroups

def get_pods_for_app(namespace, app_name):
    """Get pod statistics for the application."""
    try:
        core_v1 = client.CoreV1Api()
        
        # Try to find pods by labels or namespace
        # Common label selectors: app, app.kubernetes.io/name, name
        label_selectors = [
            f"app={app_name}",
            f"app.kubernetes.io/name={app_name}",
            f"name={app_name}"
        ]
        
        pods = []
        for selector in label_selectors:
            try:
                pod_list = core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=selector
                )
                pods.extend(pod_list.items)
                if pods:
                    break
            except:
                continue
        
        # If no pods found with selectors, get all pods in namespace
        if not pods:
            try:
                pod_list = core_v1.list_namespaced_pod(namespace=namespace)
                pods = pod_list.items
            except Exception as e:
                print(f"Error listing pods in {namespace}: {str(e)}")
                return {'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0}
        
        # Count pod statuses
        running = 0
        pending = 0
        crashloop = 0
        
        for pod in pods:
            phase = pod.status.phase
            if phase == 'Running':
                running += 1
            elif phase == 'Pending':
                pending += 1
            
            # Check for CrashLoopBackOff
            if pod.status.container_statuses:
                for container_status in pod.status.container_statuses:
                    if container_status.state and container_status.state.waiting:
                        if 'CrashLoopBackOff' in container_status.state.waiting.reason:
                            crashloop += 1
                            break
        
        return {
            'running': running,
            'pending': pending,
            'crashloop': crashloop,
            'total': len(pods)
        }
    except Exception as e:
        print(f"Error getting pods for {app_name} in {namespace}: {str(e)}")
        return {'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0}

def get_services_for_app(namespace, app_name):
    """Get Kubernetes services for the application."""
    try:
        core_v1 = client.CoreV1Api()
        
        # Try to find services by labels
        label_selectors = [
            f"app={app_name}",
            f"app.kubernetes.io/name={app_name}",
            f"name={app_name}"
        ]
        
        services = []
        for selector in label_selectors:
            try:
                svc_list = core_v1.list_namespaced_service(
                    namespace=namespace,
                    label_selector=selector
                )
                services.extend(svc_list.items)
                if services:
                    break
            except:
                continue
        
        # If no services found, get all services in namespace
        if not services:
            try:
                svc_list = core_v1.list_namespaced_service(namespace=namespace)
                services = svc_list.items
            except Exception as e:
                print(f"Error listing services in {namespace}: {str(e)}")
                return []
        
        # Format service details
        service_details = []
        for svc in services:
            service_info = {
                'name': svc.metadata.name,
                'type': svc.spec.type if svc.spec else 'Unknown',
                'cluster_ip': svc.spec.cluster_ip if svc.spec else None,
                'external_ip': None
            }
            
            # Get external IP for LoadBalancer services
            if svc.spec and svc.spec.type == 'LoadBalancer':
                if svc.status and svc.status.load_balancer:
                    if svc.status.load_balancer.ingress:
                        service_info['external_ip'] = svc.status.load_balancer.ingress[0].hostname or \
                                                      svc.status.load_balancer.ingress[0].ip
            
            service_details.append(service_info)
        
        return service_details
    except Exception as e:
        print(f"Error getting services for {app_name} in {namespace}: {str(e)}")
        return []

def get_ec2_instances_for_app(app_name, component_type, namespace=None):
    """Find EC2 instances tagged for the application with enhanced details.
    Also checks ConfigMaps for database IPs if namespace is provided."""
    instances = []
    
    # Method 1: Find by EC2 tags
    try:
        filters = [
            {'Name': 'tag:AppName', 'Values': [app_name]},
            {'Name': 'tag:Component', 'Values': [component_type]},
            {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
        ]
        
        response = ec2.describe_instances(Filters=filters)
        
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                shared = tags.get('Shared', 'false').lower() == 'true'
                
                instances.append({
                    'instance_id': instance['InstanceId'],
                    'private_ip': instance.get('PrivateIpAddress'),
                    'state': instance['State']['Name'],
                    'shared': shared,
                    'tags': tags
                })
    except Exception as e:
        print(f"Error finding EC2 instances by tags for {app_name} ({component_type}): {str(e)}")
    
    # Method 2: Find by ConfigMap database IPs (if namespace provided and no instances found)
    if namespace and len(instances) == 0:
        try:
            core_v1 = client.CoreV1Api()
            
            # Try to get database IP from common-config ConfigMap
            try:
                configmap = core_v1.read_namespaced_config_map('common-config', namespace)
                db_ip = None
                
                if component_type == 'postgres':
                    db_ip = configmap.data.get('POSTGRES_HOST', '').strip()
                elif component_type == 'neo4j':
                    neo4j_uri = configmap.data.get('NEO4J_URI', '').strip()
                    if neo4j_uri:
                        # Extract IP from URI (e.g., "bolt://10.0.1.5:7687" -> "10.0.1.5")
                        import re
                        match = re.search(r'//([^:/]+)', neo4j_uri)
                        if match:
                            db_ip = match.group(1)
                
                if db_ip:
                    print(f"  Found {component_type} IP from ConfigMap: {db_ip}")
                    # Find EC2 instance with this private IP
                    ip_filters = [
                        {'Name': 'private-ip-address', 'Values': [db_ip]},
                        {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                    ]
                    
                    ip_response = ec2.describe_instances(Filters=ip_filters)
                    
                    for reservation in ip_response.get('Reservations', []):
                        for instance in reservation.get('Instances', []):
                            # Avoid duplicates
                            if not any(inst['instance_id'] == instance['InstanceId'] for inst in instances):
                                tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                                shared = tags.get('Shared', 'false').lower() == 'true'
                                
                                instances.append({
                                    'instance_id': instance['InstanceId'],
                                    'private_ip': instance.get('PrivateIpAddress') or db_ip,
                                    'state': instance['State']['Name'],
                                    'shared': shared,
                                    'tags': tags
                                })
                                print(f"  ✅ Found {component_type} instance: {instance['InstanceId']} (IP: {db_ip})")
            except Exception as e:
                print(f"  ⚠️  Could not read ConfigMap common-config in {namespace}: {str(e)}")
        except Exception as e:
            print(f"Error finding EC2 instances by ConfigMap for {app_name} ({component_type}): {str(e)}")
    
    return instances

def get_configmap_database_details(namespace):
    """
    Read common-config ConfigMap from namespace and extract database connection details.
    Returns normalized database configuration.
    """
    db_config = {
        'postgres_host': None,
        'postgres_port': None,
        'postgres_db': None,
        'postgres_user': None,
        'neo4j_host': None,
        'neo4j_port': None,
        'neo4j_username': None
    }
    
    try:
        core_v1 = client.CoreV1Api()
        configmap = core_v1.read_namespaced_config_map('common-config', namespace)
        
        data = configmap.data or {}
        
        # Extract PostgreSQL details
        # Support both POSTGRES_HOST and POSTGRES_IP
        postgres_host = data.get('POSTGRES_HOST') or data.get('POSTGRES_IP', '').strip()
        if postgres_host:
            db_config['postgres_host'] = postgres_host
        
        postgres_port = data.get('POSTGRES_PORT', '').strip()
        if postgres_port:
            try:
                db_config['postgres_port'] = int(postgres_port)
            except ValueError:
                db_config['postgres_port'] = 5432  # Default PostgreSQL port
        
        db_config['postgres_db'] = data.get('POSTGRES_DB', '').strip() or None
        db_config['postgres_user'] = data.get('POSTGRES_USER', '').strip() or None
        
        # Extract Neo4j details
        neo4j_uri = data.get('NEO4J_URI', '').strip()
        if neo4j_uri:
            # Parse URI format: bolt://IP:PORT or bolt://HOST:PORT
            import re
            # Match bolt://HOST:PORT or bolt://IP:PORT
            match = re.search(r'bolt://([^:/]+)(?::(\d+))?', neo4j_uri)
            if match:
                db_config['neo4j_host'] = match.group(1)
                if match.group(2):
                    db_config['neo4j_port'] = int(match.group(2))
                else:
                    db_config['neo4j_port'] = 7687  # Default Neo4j bolt port
        
        # Support legacy NEO4J_USER key
        neo4j_username = data.get('NEO4J_USERNAME') or data.get('NEO4J_USER', '').strip()
        if neo4j_username:
            db_config['neo4j_username'] = neo4j_username
        
        print(f"  📋 ConfigMap extracted: PG={db_config['postgres_host']}, Neo4j={db_config['neo4j_host']}")
        
    except Exception as e:
        print(f"  ⚠️  Could not read ConfigMap common-config in {namespace}: {str(e)}")
    
    return db_config

def check_shared_resources(app_name, postgres_instances, neo4j_instances):
    """Check if any database instances are shared with other applications."""
    shared_info = {
        'postgres': [],
        'neo4j': []
    }
    
    # Check PostgreSQL instances
    for pg in postgres_instances:
        if pg['shared']:
            try:
                all_apps_filter = [
                    {'Name': 'tag:Component', 'Values': ['postgres']},
                    {'Name': 'instance-id', 'Values': [pg['instance_id']]}
                ]
                all_apps_response = ec2.describe_instances(Filters=all_apps_filter)
                
                linked_apps = set()
                for res in all_apps_response.get('Reservations', []):
                    for inst in res.get('Instances', []):
                        inst_tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
                        linked_app = inst_tags.get('AppName')
                        if linked_app and linked_app != app_name:
                            linked_apps.add(linked_app)
                
                if linked_apps:
                    shared_info['postgres'].append({
                        'host': pg.get('private_ip'),  # Use host/IP instead of instance_id
                        'linked_apps': list(linked_apps)
                    })
            except Exception as e:
                print(f"Error checking shared postgres {pg['instance_id']}: {str(e)}")
    
    # Check Neo4j instances
    for neo4j in neo4j_instances:
        if neo4j['shared']:
            try:
                all_apps_filter = [
                    {'Name': 'tag:Component', 'Values': ['neo4j']},
                    {'Name': 'instance-id', 'Values': [neo4j['instance_id']]}
                ]
                all_apps_response = ec2.describe_instances(Filters=all_apps_filter)
                
                linked_apps = set()
                for res in all_apps_response.get('Reservations', []):
                    for inst in res.get('Instances', []):
                        inst_tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
                        linked_app = inst_tags.get('AppName')
                        if linked_app and linked_app != app_name:
                            linked_apps.add(linked_app)
                
                if linked_apps:
                    shared_info['neo4j'].append({
                        'host': neo4j.get('private_ip'),  # Use host/IP instead of instance_id
                        'linked_apps': list(linked_apps)
                    })
            except Exception as e:
                print(f"Error checking shared neo4j {neo4j['instance_id']}: {str(e)}")
    
    return shared_info

def update_registry(app_name, namespace, hostnames, nodegroups, pods, services, 
                   postgres_instances, neo4j_instances, shared_info, certificate_expiry, db_config=None):
    """Update DynamoDB registry with enhanced application information."""
    table = dynamodb.Table(TABLE_NAME)
    
    # Ensure hostnames is a list and deduplicated
    if isinstance(hostnames, set):
        hostnames = sorted(list(hostnames))
    elif isinstance(hostnames, list):
        hostnames = sorted(list(set(hostnames)))
    
    # Ensure we have at least one hostname
    if not hostnames:
        print(f"⚠️  Warning: No hostnames for {app_name}, skipping registry update")
        return False
    
    # Determine status
    status = 'DOWN'
    if nodegroups:
        for ng in nodegroups:
            if ng.get('scaling', {}).get('desired', 0) > 0:
                status = 'UP'
                break
    
    # Build registry item with all enhanced fields
    try:
        # Use ConfigMap values if available, otherwise fall back to EC2 instance IPs
        postgres_host = db_config.get('postgres_host') if db_config else None
        if not postgres_host and postgres_instances:
            postgres_host = postgres_instances[0].get('private_ip')
        
        neo4j_host = db_config.get('neo4j_host') if db_config else None
        if not neo4j_host and neo4j_instances:
            neo4j_host = neo4j_instances[0].get('private_ip')
        
        item = {
            'app_name': app_name,
            'namespace': namespace,
            'hostnames': hostnames,
            'nodegroups': nodegroups if nodegroups else [],
            'pods': pods if pods else {'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0},
            'services': services if services else [],
            # EC2 instances removed - not stored in registry
            # DB state is determined by EC2 instance state internally but not exposed
            'shared_resources': shared_info if shared_info else {'postgres': [], 'neo4j': []},
            'certificate_expiry': certificate_expiry,
            'http_latency_ms': None,  # Will be updated by health monitor
            'status': status,
            'health_url': '/healthz',
            'last_updated': int(time.time()),
            # Database connection details from ConfigMap
            'postgres_host': postgres_host,
            'postgres_port': db_config.get('postgres_port') if db_config else None,
            'postgres_db': db_config.get('postgres_db') if db_config else None,
            'postgres_user': db_config.get('postgres_user') if db_config else None,
            'neo4j_host': neo4j_host,
            'neo4j_port': db_config.get('neo4j_port') if db_config else None,
            'neo4j_username': db_config.get('neo4j_username') if db_config else None,
            # Database states (will be updated by health monitor)
            'postgres_state': None,  # Will be set by health monitor: 'running', 'stopped', 'starting'
            'neo4j_state': None,     # Will be set by health monitor: 'running', 'stopped', 'starting'
            'nodegroup_state': None, # Will be set by controller: 'ready', 'stopped', 'scaling'
            'final_app_status': None  # Will be set by health monitor: 'UP', 'DOWN', 'WAITING'
        }
        
        table.put_item(Item=item)
        print(f"✅ Updated registry for {app_name}: {len(hostnames)} hostname(s), {len(nodegroups)} nodegroup(s), {pods.get('total', 0)} pod(s)")
        return True
    except Exception as e:
        print(f"❌ Error updating registry for {app_name}: {str(e)}")
        return False

def lambda_handler(event, context):
    """Main Lambda handler."""
    cluster_name = os.environ.get('EKS_CLUSTER_NAME')
    if not cluster_name:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'EKS_CLUSTER_NAME not configured'})
        }
    
    try:
        # Load Kubernetes config
        load_k8s_config()
        
        # Get all Ingress resources
        ingresses = get_all_ingresses()
        
        # Map hostnames to applications
        app_map = {}
        for ingress in ingresses:
            hostnames = extract_hostnames(ingress)
            discovered_namespace = ingress.metadata.namespace
            
            for hostname in hostnames:
                # Apply hard-coded namespace mapping (overrides Ingress namespace)
                correct_namespace = get_namespace_for_app(hostname, discovered_namespace)
                
                if hostname not in app_map:
                    app_map[hostname] = {
                        'hostnames': set(),
                        'ingress_names': [],
                        'namespace': correct_namespace
                    }
                app_map[hostname]['hostnames'].add(hostname)
                if ingress.metadata.name not in app_map[hostname]['ingress_names']:
                    app_map[hostname]['ingress_names'].append(ingress.metadata.name)
        
        # Process each application
        discovered_apps = []
        failed_apps = []
        
        for app_name, app_info in app_map.items():
            try:
                print(f"\n🔍 Processing: {app_name}")
                # Apply hard-coded namespace mapping (ensures correct namespace)
                discovered_namespace = app_info['namespace']
                namespace = get_namespace_for_app(app_name, discovered_namespace)
                
                # Convert hostnames set to sorted list (deduplicated)
                unique_hostnames = sorted(list(app_info['hostnames']))
                print(f"  📋 Hostnames: {len(unique_hostnames)} unique, Namespace: {namespace}")
                
                # Get NodeGroups (with error handling)
                try:
                    nodegroups = get_nodegroups_for_app(app_name, cluster_name)
                    print(f"  📦 NodeGroups: {len(nodegroups)} found")
                except Exception as e:
                    print(f"  ⚠️  NodeGroup lookup failed: {str(e)}")
                    nodegroups = []
                
                # Get Pods (with error handling)
                try:
                    pods = get_pods_for_app(namespace, app_name)
                    print(f"  🪟 Pods: {pods.get('total', 0)} total ({pods.get('running', 0)} running, {pods.get('pending', 0)} pending, {pods.get('crashloop', 0)} crashloop)")
                except Exception as e:
                    print(f"  ⚠️  Pod lookup failed: {str(e)}")
                    pods = {'running': 0, 'pending': 0, 'crashloop': 0, 'total': 0}
                
                # Get Services (with error handling)
                try:
                    services = get_services_for_app(namespace, app_name)
                    print(f"  🔌 Services: {len(services)} found")
                except Exception as e:
                    print(f"  ⚠️  Service lookup failed: {str(e)}")
                    services = []
                
                # Get ConfigMap database details
                db_config = {}
                try:
                    db_config = get_configmap_database_details(namespace)
                except Exception as e:
                    print(f"  ⚠️  ConfigMap read failed: {str(e)}")
                    db_config = {}
                
                # Get EC2 instances (with error handling)
                try:
                    postgres_instances = get_ec2_instances_for_app(app_name, 'postgres', namespace)
                    print(f"  💾 PostgreSQL: {len(postgres_instances)} found")
                except Exception as e:
                    print(f"  ⚠️  PostgreSQL lookup failed: {str(e)}")
                    postgres_instances = []
                
                try:
                    neo4j_instances = get_ec2_instances_for_app(app_name, 'neo4j', namespace)
                    print(f"  💾 Neo4j: {len(neo4j_instances)} found")
                except Exception as e:
                    print(f"  ⚠️  Neo4j lookup failed: {str(e)}")
                    neo4j_instances = []
                
                # Check shared resources
                try:
                    shared_info = check_shared_resources(app_name, postgres_instances, neo4j_instances)
                except Exception as e:
                    print(f"  ⚠️  Shared resource check failed: {str(e)}")
                    shared_info = {'postgres': [], 'neo4j': []}
                
                # Extract certificate expiry from first ingress
                certificate_expiry = None
                try:
                    for ingress in ingresses:
                        if ingress.metadata.namespace == namespace:
                            hostnames_in_ingress = extract_hostnames(ingress)
                            if app_name in hostnames_in_ingress:
                                certificate_expiry = extract_certificate_expiry(ingress)
                                if certificate_expiry:
                                    break
                except Exception as e:
                    print(f"  ⚠️  Certificate expiry extraction failed: {str(e)}")
                
                # Update registry
                if update_registry(
                    app_name,
                    namespace,
                    unique_hostnames,
                    nodegroups,
                    pods,
                    services,
                    postgres_instances,
                    neo4j_instances,
                    shared_info,
                    certificate_expiry,
                    db_config
                ):
                    discovered_apps.append(app_name)
                    print(f"  ✅ Successfully registered: {app_name}")
                else:
                    failed_apps.append(app_name)
                    print(f"  ❌ Failed to register: {app_name}")
                    
            except Exception as e:
                print(f"❌ Error processing app {app_name}: {str(e)}")
                import traceback
                traceback.print_exc()
                failed_apps.append(app_name)
                continue
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Discovery completed',
                'apps_discovered': len(discovered_apps),
                'apps_failed': len(failed_apps),
                'apps': discovered_apps,
                'failed': failed_apps
            })
        }
    
    except Exception as e:
        print(f"Discovery error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
