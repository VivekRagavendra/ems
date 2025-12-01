"""
Cost Tracker Lambda Function
Calculates daily costs for each application and stores in DynamoDB.
Runs daily via EventBridge at 00:30 UTC.
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from decimal import Decimal
import pytz

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
    COSTS_TABLE_NAME = os.environ.get('COSTS_TABLE_NAME', 'eks-app-controller-app-costs')
    COST_CONFIG = CONFIG.get('cost', {})
    AWS_REGION = COST_CONFIG.get('region', 'us-east-1')
    NETWORK_PRICE_PER_GB = Decimal(str(COST_CONFIG.get('aws_price_per_gb', 0.09)))
except Exception as e:
    print(f"⚠️ Warning: Could not load config: {e}")
    REGISTRY_TABLE_NAME = os.environ.get('REGISTRY_TABLE_NAME', 'eks-app-controller-registry')
    COSTS_TABLE_NAME = os.environ.get('COSTS_TABLE_NAME', 'eks-app-controller-app-costs')
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    NETWORK_PRICE_PER_GB = Decimal('0.09')

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ec2 = boto3.client('ec2', region_name=AWS_REGION)
eks = boto3.client('eks', region_name=AWS_REGION)
autoscaling = boto3.client('autoscaling', region_name=AWS_REGION)
cloudwatch = boto3.client('cloudwatch', region_name=AWS_REGION)
ce = boto3.client('ce', region_name='us-east-1')  # Cost Explorer is only in us-east-1

# Static instance type pricing (USD per hour) - fallback when Pricing API unavailable
# Common instance types used in EKS NodeGroups
INSTANCE_PRICE_MAP = {
    't3.small': Decimal('0.0208'),
    't3.medium': Decimal('0.0416'),
    't3.large': Decimal('0.0832'),
    't3.xlarge': Decimal('0.1664'),
    't3.2xlarge': Decimal('0.3328'),
    'm5.large': Decimal('0.096'),
    'm5.xlarge': Decimal('0.192'),
    'm5.2xlarge': Decimal('0.384'),
    'm5.4xlarge': Decimal('0.768'),
    'c5.large': Decimal('0.085'),
    'c5.xlarge': Decimal('0.17'),
    'c5.2xlarge': Decimal('0.34'),
    'c5.4xlarge': Decimal('0.68'),
    'r5.large': Decimal('0.126'),
    'r5.xlarge': Decimal('0.252'),
    'r5.2xlarge': Decimal('0.504'),
}

# EBS pricing per GB per month (us-east-1) - convert to daily
EBS_GP3_PRICE_PER_GB_MONTH = Decimal('0.08')
EBS_GP2_PRICE_PER_GB_MONTH = Decimal('0.10')
EBS_IO1_PRICE_PER_GB_MONTH = Decimal('0.125')

def get_instance_hourly_price(instance_type, region=AWS_REGION):
    """Get hourly price for instance type. Uses static map or fallback estimate."""
    if instance_type in INSTANCE_PRICE_MAP:
        return INSTANCE_PRICE_MAP[instance_type]
    
    # Fallback: estimate based on vCPU (rough approximation)
    # Most instances: ~$0.01-0.02 per vCPU per hour
    vcpu_estimate_map = {
        'small': 2, 'medium': 2, 'large': 2, 'xlarge': 4,
        '2xlarge': 8, '4xlarge': 16, '8xlarge': 32
    }
    
    instance_family = instance_type.split('.')[0]
    size = instance_type.split('.')[1] if '.' in instance_type else 'medium'
    vcpu = vcpu_estimate_map.get(size, 2)
    
    # Rough estimate: $0.015 per vCPU per hour
    return Decimal(str(vcpu * 0.015))

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
        print(f"   ⚠️  Error finding instance by IP {ip_address}: {e}")
        return None, None

def get_all_apps():
    """Get all applications from registry."""
    table = dynamodb.Table(REGISTRY_TABLE_NAME)
    try:
        response = table.scan()
        return response.get('Items', [])
    except Exception as e:
        print(f"Error scanning registry: {str(e)}")
        return []

def calculate_nodegroup_cost(app_name, nodegroup_name, cluster_name):
    """Calculate daily cost for NodeGroup EC2 instances."""
    try:
        # Get NodeGroup details
        response = eks.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name
        )
        
        nodegroup = response['nodegroup']
        scaling_config = nodegroup.get('scalingConfig', {})
        desired_size = scaling_config.get('desiredSize', 0)
        current_size = scaling_config.get('desiredSize', 0)  # Use desired as current
        
        if current_size == 0:
            return Decimal('0')
        
        # Get instance types from ASG
        resources = nodegroup.get('resources', {})
        asg_names = resources.get('autoScalingGroups', [])
        
        if not asg_names:
            print(f"   ⚠️  No ASG found for nodegroup {nodegroup_name}")
            return Decimal('0')
        
        asg_name = asg_names[0].get('name')
        
        # Get ASG instance details
        asg_response = autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        
        if not asg_response.get('AutoScalingGroups'):
            return Decimal('0')
        
        asg = asg_response['AutoScalingGroups'][0]
        instances = asg.get('Instances', [])
        
        # Group by instance type
        instance_type_counts = {}
        for instance in instances:
            instance_id = instance.get('InstanceId')
            if instance_id:
                try:
                    ec2_response = ec2.describe_instances(InstanceIds=[instance_id])
                    if ec2_response.get('Reservations'):
                        instance_type = ec2_response['Reservations'][0]['Instances'][0].get('InstanceType')
                        instance_type_counts[instance_type] = instance_type_counts.get(instance_type, 0) + 1
                except Exception as e:
                    print(f"   ⚠️  Error getting instance type for {instance_id}: {e}")
        
        # If no instances found, use desired size with default instance type
        if not instance_type_counts:
            # Try to get launch template instance type
            launch_template = asg.get('LaunchTemplate', {})
            if launch_template:
                # Default to common type
                instance_type_counts['t3.medium'] = current_size
            else:
                instance_type_counts['t3.medium'] = current_size
        
        # Calculate hourly cost
        hourly_cost = Decimal('0')
        for instance_type, count in instance_type_counts.items():
            price_per_hour = get_instance_hourly_price(instance_type)
            hourly_cost += price_per_hour * Decimal(str(count))
        
        # Daily cost = hourly * 24
        daily_cost = hourly_cost * Decimal('24')
        
        print(f"   ✅ NodeGroup {nodegroup_name}: {current_size} instances, ${daily_cost:.2f}/day")
        return daily_cost
        
    except Exception as e:
        print(f"   ❌ Error calculating nodegroup cost for {nodegroup_name}: {str(e)}")
        return Decimal('0')

def calculate_database_cost(instance_id):
    """Calculate daily cost for database EC2 instance."""
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        if not response.get('Reservations'):
            return Decimal('0'), Decimal('0')  # instance_cost, ebs_cost
        
        instance = response['Reservations'][0]['Instances'][0]
        instance_type = instance.get('InstanceType')
        state = instance.get('State', {}).get('Name', 'stopped')
        
        # Instance cost: running 24h if running, 0 if stopped
        hours_running = Decimal('24') if state == 'running' else Decimal('0')
        hourly_price = get_instance_hourly_price(instance_type)
        instance_cost = hourly_price * hours_running
        
        # EBS cost: get attached volumes
        volumes = instance.get('BlockDeviceMappings', [])
        ebs_cost = Decimal('0')
        
        for volume_mapping in volumes:
            volume_id = volume_mapping.get('Ebs', {}).get('VolumeId')
            if volume_id:
                try:
                    vol_response = ec2.describe_volumes(VolumeIds=[volume_id])
                    if vol_response.get('Volumes'):
                        volume = vol_response['Volumes'][0]
                        size_gb = Decimal(str(volume.get('Size', 0)))
                        volume_type = volume.get('VolumeType', 'gp3')
                        
                        # Get price per GB per month based on type
                        if volume_type == 'gp2':
                            price_per_gb_month = EBS_GP2_PRICE_PER_GB_MONTH
                        elif volume_type == 'io1' or volume_type == 'io2':
                            price_per_gb_month = EBS_IO1_PRICE_PER_GB_MONTH
                        else:  # gp3 or default
                            price_per_gb_month = EBS_GP3_PRICE_PER_GB_MONTH
                        
                        # Daily cost = (size_gb * price_per_gb_month) / 30
                        daily_ebs_cost = (size_gb * price_per_gb_month) / Decimal('30')
                        ebs_cost += daily_ebs_cost
                except Exception as e:
                    print(f"   ⚠️  Error getting volume {volume_id}: {e}")
        
        return instance_cost, ebs_cost
        
    except Exception as e:
        print(f"   ❌ Error calculating database cost for {instance_id}: {str(e)}")
        return Decimal('0'), Decimal('0')

def calculate_network_cost(instance_ids, app_name):
    """Calculate daily network cost from CloudWatch metrics."""
    try:
        if not instance_ids:
            return Decimal('0')
        
        # Get NetworkIn and NetworkOut for last 24 hours
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=1)
        
        total_bytes = Decimal('0')
        
        # Query CloudWatch for each instance
        for instance_id in instance_ids[:10]:  # Limit to 10 instances per query
            try:
                # NetworkIn
                response_in = cloudwatch.get_metric_statistics(
                    Namespace='AWS/EC2',
                    MetricName='NetworkIn',
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,  # 1 hour periods
                    Statistics=['Sum']
                )
                
                # NetworkOut
                response_out = cloudwatch.get_metric_statistics(
                    Namespace='AWS/EC2',
                    MetricName='NetworkOut',
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                # Sum all datapoints
                for datapoint in response_in.get('Datapoints', []):
                    total_bytes += Decimal(str(datapoint.get('Sum', 0)))
                
                for datapoint in response_out.get('Datapoints', []):
                    total_bytes += Decimal(str(datapoint.get('Sum', 0)))
                    
            except Exception as e:
                print(f"   ⚠️  Error getting network metrics for {instance_id}: {e}")
        
        # Convert bytes to GB and multiply by price
        total_gb = total_bytes / Decimal('1073741824')  # 1024^3
        network_cost = total_gb * NETWORK_PRICE_PER_GB
        
        return network_cost
        
    except Exception as e:
        print(f"   ⚠️  Error calculating network cost: {e}")
        return Decimal('0')

def calculate_app_cost(app_data):
    """Calculate total daily cost for an application."""
    app_name = app_data.get('app_name') or app_data.get('name') or 'unknown'
    print(f"\n📊 Calculating cost for {app_name}")
    
    nodegroup_cost = Decimal('0')
    db_instance_cost = Decimal('0')
    db_ebs_cost = Decimal('0')
    network_cost = Decimal('0')
    
    # Get cluster name from config
    try:
        cluster_name = CONFIG.get('eks', {}).get('cluster_name', os.environ.get('EKS_CLUSTER_NAME', ''))
    except:
        cluster_name = os.environ.get('EKS_CLUSTER_NAME', '')
    
    # 1. NodeGroup cost
    nodegroups = app_data.get('nodegroups', [])
    if isinstance(nodegroups, list) and nodegroups:
        for ng_data in nodegroups:
            if isinstance(ng_data, dict):
                ng_name = ng_data.get('name') or ng_data.get('nodegroup')
                if ng_name:
                    nodegroup_cost += calculate_nodegroup_cost(app_name, ng_name, cluster_name)
    elif isinstance(nodegroups, dict):
        ng_name = nodegroups.get('name') or nodegroups.get('nodegroup')
        if ng_name:
            nodegroup_cost += calculate_nodegroup_cost(app_name, ng_name, cluster_name)
    
    # 2. Database EC2 costs - calculate separately for PostgreSQL and Neo4j
    instance_ids = []
    postgres_instance_cost = Decimal('0')
    postgres_ebs_cost = Decimal('0')
    neo4j_instance_cost = Decimal('0')
    neo4j_ebs_cost = Decimal('0')
    
    # PostgreSQL - try instance_id first, then find by host IP
    postgres_instance_id = app_data.get('postgres_instance_id')
    if not postgres_instance_id:
        # Try to find instance ID from host IP
        postgres_host = app_data.get('postgres_host')
        if postgres_host:
            print(f"   🔍 Looking up PostgreSQL instance ID for host {postgres_host}...")
            postgres_instance_id, _ = find_ec2_instance_by_ip(postgres_host)
            if postgres_instance_id:
                print(f"   ✅ Found PostgreSQL instance: {postgres_instance_id}")
            else:
                print(f"   ⚠️  Could not find EC2 instance for PostgreSQL host {postgres_host}")
    
    if postgres_instance_id:
        instance_ids.append(postgres_instance_id)
        inst_cost, ebs_cost = calculate_database_cost(postgres_instance_id)
        postgres_instance_cost = inst_cost
        postgres_ebs_cost = ebs_cost
        db_instance_cost += inst_cost
        db_ebs_cost += ebs_cost
        print(f"   💰 PostgreSQL cost: Instance=${inst_cost:.2f}, EBS=${ebs_cost:.2f}")
    else:
        print(f"   ℹ️  No PostgreSQL instance ID found - skipping PostgreSQL cost calculation")
    
    # Neo4j - try instance_id first, then find by host IP
    neo4j_instance_id = app_data.get('neo4j_instance_id')
    if not neo4j_instance_id:
        # Try to find instance ID from host IP
        neo4j_host = app_data.get('neo4j_host')
        if neo4j_host:
            print(f"   🔍 Looking up Neo4j instance ID for host {neo4j_host}...")
            neo4j_instance_id, _ = find_ec2_instance_by_ip(neo4j_host)
            if neo4j_instance_id:
                print(f"   ✅ Found Neo4j instance: {neo4j_instance_id}")
            else:
                print(f"   ⚠️  Could not find EC2 instance for Neo4j host {neo4j_host}")
    
    if neo4j_instance_id:
        instance_ids.append(neo4j_instance_id)
        inst_cost, ebs_cost = calculate_database_cost(neo4j_instance_id)
        neo4j_instance_cost = inst_cost
        neo4j_ebs_cost = ebs_cost
        db_instance_cost += inst_cost
        db_ebs_cost += ebs_cost
        print(f"   💰 Neo4j cost: Instance=${inst_cost:.2f}, EBS=${ebs_cost:.2f}")
    else:
        print(f"   ℹ️  No Neo4j instance ID found - skipping Neo4j cost calculation")
    
    # 3. Network cost (for all instances)
    network_cost = calculate_network_cost(instance_ids, app_name)
    
    # Total daily cost
    daily_cost = nodegroup_cost + db_instance_cost + db_ebs_cost + network_cost
    
    # Projected monthly cost (simplified: use 30 days)
    projected_monthly_cost = daily_cost * Decimal('30')
    
    # Savings estimate (basic: if app is currently DOWN, estimate savings)
    # For MVP: simplified calculation
    savings_month_to_date = Decimal('0')  # TODO: Implement based on operation logs
    
    # Build detailed breakdown with separate PostgreSQL and Neo4j costs
    # (postgres_instance_cost, postgres_ebs_cost, neo4j_instance_cost, neo4j_ebs_cost already calculated above)
    cost_breakdown = {
        'nodegroups': float(nodegroup_cost),
        'databases': float(db_instance_cost),  # Total for backward compatibility
        'postgres_ec2': float(postgres_instance_cost),  # PostgreSQL EC2 instance cost
        'postgres_ebs': float(postgres_ebs_cost),  # PostgreSQL EBS cost
        'neo4j_ec2': float(neo4j_instance_cost),  # Neo4j EC2 instance cost
        'neo4j_ebs': float(neo4j_ebs_cost),  # Neo4j EBS cost
        'ebs': float(db_ebs_cost),  # Total EBS for backward compatibility
        'network': float(network_cost)
    }
    
    print(f"   💰 Daily Cost: ${daily_cost:.2f}")
    print(f"   📈 Projected Monthly: ${projected_monthly_cost:.2f}")
    
    return {
        'daily_cost': float(daily_cost),
        'projected_monthly_cost': float(projected_monthly_cost),
        'savings_month_to_date': float(savings_month_to_date),
        'cost_breakdown': cost_breakdown
    }

def get_cost_for_date(table, app_name, date_str):
    """Get cost for a specific date (YYYY-MM-DD format)."""
    try:
        response = table.get_item(
            Key={'PK': app_name, 'SK': date_str}
        )
        
        if 'Item' in response:
            item = response['Item']
            daily_cost = item.get('daily_cost', Decimal('0'))
            if isinstance(daily_cost, Decimal):
                return daily_cost
            else:
                return Decimal(str(daily_cost))
        return Decimal('0')
    except Exception as e:
        print(f"   ⚠️  Error getting cost for date {date_str}: {e}")
        return Decimal('0')

def calculate_mtd_cost(table, app_name, current_month):
    """Calculate Month-To-Date cost by summing all daily costs for current month."""
    try:
        # Query all items for this app where SK starts with current month (YYYY-MM)
        response = table.query(
            KeyConditionExpression='PK = :app AND begins_with(SK, :month)',
            ExpressionAttributeValues={
                ':app': app_name,
                ':month': current_month
            }
        )
        
        mtd_cost = Decimal('0')
        for item in response.get('Items', []):
            # Skip the 'latest' item
            if item.get('SK') == 'latest':
                continue
            daily_cost = item.get('daily_cost', Decimal('0'))
            if isinstance(daily_cost, Decimal):
                mtd_cost += daily_cost
            else:
                mtd_cost += Decimal(str(daily_cost))
        
        return mtd_cost
    except Exception as e:
        print(f"   ⚠️  Error calculating MTD cost: {e}")
        return Decimal('0')

def get_days_in_month(year, month):
    """Get number of days in a month."""
    from calendar import monthrange
    return monthrange(year, month)[1]

def store_cost_record(app_name, cost_data):
    """Store cost record in DynamoDB and update latest summary."""
    table = dynamodb.Table(COSTS_TABLE_NAME)
    
    now = datetime.utcnow()
    today = now.strftime('%Y-%m-%d')
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    current_month = now.strftime('%Y-%m')  # YYYY-MM
    current_year = now.year
    current_month_num = now.month
    
    try:
        # 1. Get yesterday's cost (from previous day's record if it exists)
        yesterday_cost = get_cost_for_date(table, app_name, yesterday)
        print(f"   📅 Yesterday's cost ({yesterday}): ${yesterday_cost:.2f}")
        
        # 2. Store daily record (PK=app, SK=YYYY-MM-DD)
        daily_item = {
            'PK': app_name,
            'SK': today,
            'daily_cost': Decimal(str(cost_data['daily_cost'])),
            'yesterday_cost': yesterday_cost,  # Store yesterday's cost in today's record
            'cost_breakdown': json.dumps(cost_data['cost_breakdown']),
            'timestamp': now.isoformat() + 'Z'
        }
        
        table.put_item(Item=daily_item)
        print(f"   ✅ Stored daily cost record for {app_name} on {today}")
        
        # 3. Get existing latest record to check if month changed
        try:
            latest_response = table.get_item(
                Key={'PK': app_name, 'SK': 'latest'}
            )
            existing_latest = latest_response.get('Item')
            existing_month = existing_latest.get('month') if existing_latest else None
        except Exception as e:
            print(f"   ⚠️  Error reading existing latest: {e}")
            existing_month = None
        
        # 4. Calculate MTD cost (keep for backward compatibility, but not used in UI)
        # If month changed, MTD = today's daily_cost (reset)
        # Otherwise, sum all daily costs for current month
        if existing_month != current_month:
            # Month changed - reset MTD to today's cost
            mtd_cost = Decimal(str(cost_data['daily_cost']))
            print(f"   🔄 Month changed ({existing_month} → {current_month}), resetting MTD")
        else:
            # Same month - calculate MTD from all daily records
            mtd_cost = calculate_mtd_cost(table, app_name, current_month)
            print(f"   📊 MTD cost for {current_month}: ${mtd_cost:.2f}")
        
        # 5. Calculate projected monthly cost
        days_in_month = get_days_in_month(current_year, current_month_num)
        daily_cost_decimal = Decimal(str(cost_data['daily_cost']))
        projected_monthly_cost = daily_cost_decimal * Decimal(str(days_in_month))
        
        # 6. Store/update latest summary (PK=app, SK=latest)
        latest_item = {
            'PK': app_name,
            'SK': 'latest',
            'month': current_month,
            'daily_cost': daily_cost_decimal,
            'yesterday_cost': yesterday_cost,  # Add yesterday's cost
            'mtd_cost': mtd_cost,  # Keep for backward compatibility
            'projected_monthly_cost': projected_monthly_cost,
            'breakdown': json.dumps(cost_data['cost_breakdown']),
            'updated_at': now.isoformat() + 'Z'
        }
        
        table.put_item(Item=latest_item)
        print(f"   ✅ Updated latest summary: Yesterday=${yesterday_cost:.2f}, Daily=${daily_cost_decimal:.2f}, Projected=${projected_monthly_cost:.2f}")
        
    except Exception as e:
        print(f"   ❌ Error storing cost record: {e}")
        import traceback
        traceback.print_exc()

def lambda_handler(event, context):
    """Main Lambda handler."""
    print("="*70)
    print("💰 COST TRACKER - Daily Cost Calculation")
    print("="*70)
    
    try:
        apps = get_all_apps()
        print(f"Found {len(apps)} applications")
        
        for app_data in apps:
            app_name = app_data.get('app_name') or app_data.get('name') or 'unknown'
            
            try:
                cost_data = calculate_app_cost(app_data)
                store_cost_record(app_name, cost_data)
            except Exception as e:
                print(f"❌ Error processing {app_name}: {e}")
                continue
        
        print("\n✅ Cost tracking completed successfully")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Cost tracking completed',
                'apps_processed': len(apps)
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

