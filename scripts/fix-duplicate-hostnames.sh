#!/bin/bash

###############################################################################
# Fix Duplicate Hostnames in DynamoDB Registry
# 
# Purpose: Remove duplicate hostnames from existing registry entries
# Usage: ./scripts/fix-duplicate-hostnames.sh
###############################################################################

set -e

REGION="us-east-1"
TABLE_NAME="eks-app-controller-registry"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  🔧 FIXING DUPLICATE HOSTNAMES IN DYNAMODB                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Get all apps
echo "Fetching all applications from registry..."
APPS=$(aws dynamodb scan \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --projection-expression "app_name,hostnames" \
    --output json)

APP_COUNT=$(echo "$APPS" | jq -r '.Items | length')
echo "Found $APP_COUNT applications"
echo ""

FIXED_COUNT=0

# Process each app
echo "$APPS" | jq -r '.Items[] | @json' | while read -r app_json; do
    APP_NAME=$(echo "$app_json" | jq -r '.app_name.S')
    HOSTNAMES_RAW=$(echo "$app_json" | jq -r '.hostnames.L[]?.S // empty')
    
    if [ -z "$HOSTNAMES_RAW" ]; then
        echo "⚠️  $APP_NAME: No hostnames found"
        continue
    fi
    
    # Count duplicates
    HOSTNAME_COUNT=$(echo "$HOSTNAMES_RAW" | wc -l | tr -d ' ')
    UNIQUE_COUNT=$(echo "$HOSTNAMES_RAW" | sort -u | wc -l | tr -d ' ')
    
    if [ "$HOSTNAME_COUNT" -eq "$UNIQUE_COUNT" ]; then
        echo "✅ $APP_NAME: No duplicates ($HOSTNAME_COUNT hostnames)"
        continue
    fi
    
    echo "🔧 $APP_NAME: Found $HOSTNAME_COUNT hostnames, $UNIQUE_COUNT unique"
    echo "   Fixing duplicates..."
    
    # Get unique hostnames (sorted)
    UNIQUE_HOSTNAMES=$(echo "$HOSTNAMES_RAW" | sort -u | jq -R -s -c 'split("\n") | map(select(length > 0)) | map({S: .})')
    
    # Update DynamoDB
    aws dynamodb update-item \
        --table-name "$TABLE_NAME" \
        --region "$REGION" \
        --key "{\"app_name\": {\"S\": \"$APP_NAME\"}}" \
        --update-expression "SET hostnames = :hostnames" \
        --expression-attribute-values "{\":hostnames\": {\"L\": $UNIQUE_HOSTNAMES}}" \
        --no-cli-pager > /dev/null
    
    echo "   ✅ Fixed: $UNIQUE_COUNT unique hostnames"
    ((FIXED_COUNT++))
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Duplicate hostname fix completed!"
echo "   Fixed $FIXED_COUNT applications"
echo ""
echo "Next: Run discovery again to ensure no new duplicates:"
echo "  aws lambda invoke --function-name eks-app-controller-discovery --region us-east-1 /tmp/discovery.json"
echo ""


