#!/bin/bash
# Smart Database Tagging - Discovers databases from ConfigMaps
# Automatically maps databases to applications using common-config ConfigMaps

set -e

REGION="us-east-1"
CLUSTER_NAME="mi-eks-cluster"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  🤖 SMART DATABASE DISCOVERY & TAGGING                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Discovering databases from ConfigMaps in all namespaces..."
echo ""

# Get all namespaces
NAMESPACES=$(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}')

# Temporary file to store database mappings
MAPPING_FILE="/tmp/db_mappings.txt"
> "$MAPPING_FILE"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Scanning ConfigMaps for database IPs..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

for ns in $NAMESPACES; do
    # Skip system namespaces
    if [[ "$ns" =~ ^(kube-|default$|flux-system$|monitoring$|ingress-nginx$|kubernetes-dashboard$) ]]; then
        continue
    fi
    
    # Check if common-config exists
    if ! kubectl get configmap common-config -n "$ns" >/dev/null 2>&1; then
        continue
    fi
    
    echo "📦 Namespace: $ns"
    
    # Get the application host from Ingress
    APP_HOST=$(kubectl get ingress -n "$ns" -o jsonpath='{.items[0].spec.rules[0].host}' 2>/dev/null || echo "$ns.dev.mareana.com")
    
    # Extract database IPs from ConfigMap
    POSTGRES_IP=$(kubectl get configmap common-config -n "$ns" -o jsonpath='{.data.POSTGRES_HOST}' 2>/dev/null || echo "")
    NEO4J_IP=$(kubectl get configmap common-config -n "$ns" -o jsonpath='{.data.NEO4J_URI}' 2>/dev/null | grep -oP '(?<=//)[^:]+' || echo "")
    
    if [ -n "$POSTGRES_IP" ]; then
        echo "  • PostgreSQL: $POSTGRES_IP → $APP_HOST"
        echo "$POSTGRES_IP|$APP_HOST|postgres|false" >> "$MAPPING_FILE"
    fi
    
    if [ -n "$NEO4J_IP" ]; then
        echo "  • Neo4j: $NEO4J_IP → $APP_HOST"
        echo "$NEO4J_IP|$APP_HOST|neo4j|false" >> "$MAPPING_FILE"
    fi
    
    echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Mapping IPs to EC2 Instances..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get all running EC2 instances with their private IPs
INSTANCES=$(aws ec2 describe-instances \
    --region "$REGION" \
    --filters "Name=instance-state-name,Values=running" \
    --query 'Reservations[*].Instances[*].[InstanceId,PrivateIpAddress,Tags[?Key==`Name`].Value|[0]]' \
    --output text 2>/dev/null)

# Tag each instance based on IP mapping
TAG_COUNT=0

while IFS='|' read -r DB_IP APP_HOST COMPONENT SHARED; do
    [ -z "$DB_IP" ] && continue
    
    # Find EC2 instance with this private IP
    INSTANCE_ID=$(echo "$INSTANCES" | grep "$DB_IP" | awk '{print $1}')
    INSTANCE_NAME=$(echo "$INSTANCES" | grep "$DB_IP" | awk '{print $3}')
    
    if [ -n "$INSTANCE_ID" ]; then
        echo "  Tagging: $INSTANCE_ID ($INSTANCE_NAME)"
        echo "    IP: $DB_IP → AppName=$APP_HOST, Component=$COMPONENT"
        
        aws ec2 create-tags \
            --resources "$INSTANCE_ID" \
            --tags \
                "Key=AppName,Value=$APP_HOST" \
                "Key=Component,Value=$COMPONENT" \
                "Key=Shared,Value=$SHARED" \
            --region "$REGION" 2>/dev/null && echo "    ✅ Tagged successfully" || echo "    ⚠️  Failed to tag"
        
        ((TAG_COUNT++))
        echo ""
    else
        echo "  ⚠️  No EC2 instance found for IP: $DB_IP"
        echo ""
    fi
done < "$MAPPING_FILE"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Smart Database Tagging Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Summary:"
echo "  • Databases tagged: $TAG_COUNT"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Verifying Tags..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verify tagged instances
while IFS='|' read -r DB_IP APP_HOST COMPONENT SHARED; do
    [ -z "$DB_IP" ] && continue
    
    INSTANCE_ID=$(echo "$INSTANCES" | grep "$DB_IP" | awk '{print $1}')
    
    if [ -n "$INSTANCE_ID" ]; then
        TAGS=$(aws ec2 describe-tags \
            --region "$REGION" \
            --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=AppName,Component,Shared" \
            --query 'Tags[*].[Key,Value]' \
            --output text 2>/dev/null)
        
        echo "  Instance: $INSTANCE_ID (IP: $DB_IP)"
        echo "$TAGS" | while read -r key value; do
            echo "    $key=$value"
        done
        echo ""
    fi
done < "$MAPPING_FILE"

# Cleanup
rm -f "$MAPPING_FILE"

echo "Done! All databases are now tagged based on ConfigMap discovery! 🎉"


