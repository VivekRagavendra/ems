#!/bin/bash
# Tag EKS NodeGroups for Application Discovery
# This script tags all NodeGroups with AppName based on discovered applications

set -e

CLUSTER_NAME="mi-eks-cluster"
REGION="us-east-1"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Tagging EKS NodeGroups for Application Discovery             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Function to tag a NodeGroup
tag_nodegroup() {
    local nodegroup=$1
    local appname=$2
    
    echo "  Tagging NodeGroup: $nodegroup → AppName=$appname"
    
    # Get the NodeGroup ARN
    ARN=$(aws eks describe-nodegroup \
        --cluster-name "$CLUSTER_NAME" \
        --nodegroup-name "$nodegroup" \
        --region "$REGION" \
        --query 'nodegroup.nodegroupArn' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$ARN" ]; then
        echo "    ⚠️  NodeGroup $nodegroup not found, skipping"
        return
    fi
    
    # Tag the NodeGroup
    aws eks tag-resource \
        --resource-arn "$ARN" \
        --tags "AppName=$appname,Component=nodegroup" \
        --region "$REGION" 2>/dev/null && echo "    ✅ Tagged successfully" || echo "    ⚠️  Failed to tag"
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Tagging NodeGroups with AppName..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Tag NodeGroups based on discovered applications
tag_nodegroup "ai360" "ai360.dev.mareana.com"
tag_nodegroup "ai360-ondemand" "ai360.dev.mareana.com"
tag_nodegroup "flux" "mi.dev.mareana.com"
tag_nodegroup "gtag-dev" "gtag.dev.mareana.com"
tag_nodegroup "mi-app" "mi.dev.mareana.com"
tag_nodegroup "mi-app-new" "mi.dev.mareana.com"
tag_nodegroup "mi-r1-dev" "mi-r1.dev.mareana.com"
tag_nodegroup "vsm-dev" "vsm.dev.mareana.com"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ NodeGroup tagging complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Verifying tags..."
echo ""

# Verify tags
for ng in ai360 ai360-ondemand flux gtag-dev mi-app mi-app-new mi-r1-dev vsm-dev; do
    ARN=$(aws eks describe-nodegroup \
        --cluster-name "$CLUSTER_NAME" \
        --nodegroup-name "$ng" \
        --region "$REGION" \
        --query 'nodegroup.nodegroupArn' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$ARN" ]; then
        TAGS=$(aws eks list-tags-for-resource \
            --resource-arn "$ARN" \
            --region "$REGION" \
            --query 'tags' \
            --output json 2>/dev/null || echo "{}")
        
        APPNAME=$(echo "$TAGS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('AppName', 'NOT SET'))" 2>/dev/null || echo "NOT SET")
        echo "  $ng: AppName=$APPNAME"
    fi
done

echo ""
echo "Done! NodeGroups are now tagged for auto-discovery."


