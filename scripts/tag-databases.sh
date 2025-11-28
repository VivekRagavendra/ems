#!/bin/bash
# Tag EC2 Database Instances for Application Discovery
# This script tags database instances with AppName, Component, and Shared status

set -e

REGION="us-east-1"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Tagging EC2 Database Instances for Application Discovery     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Function to tag a database instance
tag_database() {
    local instance_id=$1
    local appname=$2
    local component=$3
    local shared=$4
    local description=$5
    
    echo "  Tagging Instance: $instance_id ($description)"
    echo "    AppName=$appname, Component=$component, Shared=$shared"
    
    aws ec2 create-tags \
        --resources "$instance_id" \
        --tags \
            "Key=AppName,Value=$appname" \
            "Key=Component,Value=$component" \
            "Key=Shared,Value=$shared" \
        --region "$REGION" 2>/dev/null && echo "    ✅ Tagged successfully" || echo "    ⚠️  Failed to tag"
    echo ""
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Finding and Tagging Database Instances..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get instance IDs by name pattern
INSTANCE_DATA=$(aws ec2 describe-instances \
    --region "$REGION" \
    --filters "Name=instance-state-name,Values=running" \
    --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0]]' \
    --output text 2>/dev/null || echo "")

# Parse and tag instances
while IFS=$'\t' read -r INSTANCE_ID NAME; do
    case "$NAME" in
        *vsm_postgres*)
            tag_database "$INSTANCE_ID" "vsm.dev.mareana.com" "postgres" "false" "VSM PostgreSQL"
            ;;
        *midev_neo4j*)
            tag_database "$INSTANCE_ID" "mi.dev.mareana.com" "neo4j" "false" "MI Dev Neo4j"
            ;;
        *vsm_neo4j*)
            tag_database "$INSTANCE_ID" "vsm.dev.mareana.com" "neo4j" "false" "VSM Neo4j"
            ;;
        *mir1dev_neo4j*)
            tag_database "$INSTANCE_ID" "mi-r1.dev.mareana.com" "neo4j" "false" "MI R1 Dev Neo4j"
            ;;
        *mi_db*)
            tag_database "$INSTANCE_ID" "mi.dev.mareana.com" "postgres" "false" "MI PostgreSQL"
            ;;
        *)
            # Skip non-database instances
            ;;
    esac
done <<< "$INSTANCE_DATA"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Database tagging complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Verifying tags..."
echo ""

# Verify tags on database instances
while IFS=$'\t' read -r INSTANCE_ID NAME; do
    if [[ "$NAME" =~ (postgres|neo4j|mi_db) ]]; then
        TAGS=$(aws ec2 describe-tags \
            --region "$REGION" \
            --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=AppName,Component,Shared" \
            --query 'Tags[*].[Key,Value]' \
            --output text 2>/dev/null || echo "")
        
        echo "  $INSTANCE_ID ($NAME):"
        echo "$TAGS" | while read -r key value; do
            echo "    $key=$value"
        done
        echo ""
    fi
done <<< "$INSTANCE_DATA"

echo "Done! Database instances are now tagged for auto-discovery."


