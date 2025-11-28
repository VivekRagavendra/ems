#!/bin/bash
# Test script to validate start workflow for an application
# Usage: ./scripts/test-start-workflow.sh <app-name>

set -e

APP_NAME="${1}"
if [ -z "$APP_NAME" ]; then
    echo "❌ Error: Application name required"
    echo "Usage: $0 <app-name>"
    echo "Example: $0 mi-r1.dev.mareana.com"
    exit 1
fi

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  🧪 TESTING START WORKFLOW FOR: $APP_NAME"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Get EKS cluster name from environment or use default
EKS_CLUSTER_NAME="${EKS_CLUSTER_NAME:-mi-eks-cluster}"
REGION="${AWS_REGION:-us-east-1}"

echo "📋 Configuration:"
echo "   App Name: $APP_NAME"
echo "   EKS Cluster: $EKS_CLUSTER_NAME"
echo "   Region: $REGION"
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &>/dev/null; then
    echo "❌ Error: AWS CLI not configured. Run 'aws configure' first."
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: CHECK EC2 DATABASE INSTANCES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Get app metadata from DynamoDB
TABLE_NAME="eks-app-controller-registry"
echo "   📋 Fetching app metadata from DynamoDB..."
APP_DATA=$(aws dynamodb get-item \
    --table-name "$TABLE_NAME" \
    --key "{\"app_name\": {\"S\": \"$APP_NAME\"}}" \
    --region "$REGION" 2>/dev/null || echo "{}")

if [ "$APP_DATA" == "{}" ]; then
    echo "   ⚠️  Application not found in registry"
else
    POSTGRES_HOST=$(echo "$APP_DATA" | jq -r '.Item.postgres_host.S // empty' 2>/dev/null || echo "")
    NEO4J_HOST=$(echo "$APP_DATA" | jq -r '.Item.neo4j_host.S // empty' 2>/dev/null || echo "")
    NAMESPACE=$(echo "$APP_DATA" | jq -r '.Item.namespace.S // empty' 2>/dev/null || echo "default")
    
    echo "   ✅ Found app metadata"
    echo "      Namespace: $NAMESPACE"
    echo "      Postgres Host: ${POSTGRES_HOST:-N/A}"
    echo "      Neo4j Host: ${NEO4J_HOST:-N/A}"
    
    # Check Postgres EC2 state
    if [ -n "$POSTGRES_HOST" ]; then
        echo ""
        echo "   🔍 Checking Postgres EC2 instance..."
        POSTGRES_INSTANCE=$(aws ec2 describe-instances \
            --filters "Name=private-ip-address,Values=$POSTGRES_HOST" \
            --query 'Reservations[0].Instances[0].[InstanceId,State.Name]' \
            --output text \
            --region "$REGION" 2>/dev/null || echo "None None")
        
        if [ "$POSTGRES_INSTANCE" != "None None" ]; then
            INSTANCE_ID=$(echo "$POSTGRES_INSTANCE" | awk '{print $1}')
            STATE=$(echo "$POSTGRES_INSTANCE" | awk '{print $2}')
            echo "      ✅ Postgres: $INSTANCE_ID - State: $STATE"
            if [ "$STATE" != "running" ]; then
                echo "      ⚠️  Postgres instance is not running"
            fi
        else
            echo "      ⚠️  Postgres EC2 instance not found"
        fi
    fi
    
    # Check Neo4j EC2 state
    if [ -n "$NEO4J_HOST" ]; then
        echo ""
        echo "   🔍 Checking Neo4j EC2 instance..."
        NEO4J_INSTANCE=$(aws ec2 describe-instances \
            --filters "Name=private-ip-address,Values=$NEO4J_HOST" \
            --query 'Reservations[0].Instances[0].[InstanceId,State.Name]' \
            --output text \
            --region "$REGION" 2>/dev/null || echo "None None")
        
        if [ "$NEO4J_INSTANCE" != "None None" ]; then
            INSTANCE_ID=$(echo "$NEO4J_INSTANCE" | awk '{print $1}')
            STATE=$(echo "$NEO4J_INSTANCE" | awk '{print $2}')
            echo "      ✅ Neo4j: $INSTANCE_ID - State: $STATE"
            if [ "$STATE" != "running" ]; then
                echo "      ⚠️  Neo4j instance is not running"
            fi
        else
            echo "      ⚠️  Neo4j EC2 instance not found"
        fi
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: CHECK NODEGROUP CONFIGURATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check NodeGroup defaults (hardcoded mapping)
case "$APP_NAME" in
    "ai360.dev.mareana.com")
        NODEGROUP="ai360"
        DESIRED=1
        MIN=1
        MAX=2
        ;;
    "ebr.dev.mareana.com")
        NODEGROUP="ebr-dev"
        DESIRED=1
        MIN=1
        MAX=2
        ;;
    "flux.dev.mareana.com")
        NODEGROUP="flux"
        DESIRED=1
        MIN=1
        MAX=2
        ;;
    "gtag.dev.mareana.com")
        NODEGROUP="gtag-dev"
        DESIRED=1
        MIN=1
        MAX=2
        ;;
    "mi-r1-airflow.dev.mareana.com")
        NODEGROUP="mi-r1-dev"
        DESIRED=1
        MIN=1
        MAX=2
        ;;
    "mi-app-airflow.cloud.mareana.com")
        NODEGROUP="mi-app-new"
        DESIRED=2
        MIN=1
        MAX=2
        ;;
    "mi-spark.dev.mareana.com")
        NODEGROUP="mi-app"
        DESIRED=1
        MIN=1
        MAX=2
        ;;
    "mi.dev.mareana.com")
        NODEGROUP="mi-app-new"
        DESIRED=1
        MIN=1
        MAX=2
        ;;
    "vsm.dev.mareana.com")
        NODEGROUP="vsm-dev"
        DESIRED=1
        MIN=1
        MAX=2
        ;;
    *)
        NODEGROUP=""
        DESIRED=0
        MIN=0
        MAX=0
        ;;
esac

if [ -z "$NODEGROUP" ]; then
    echo "   ℹ️  No NodeGroup assigned for $APP_NAME"
else
    echo "   📋 NodeGroup Configuration:"
    echo "      Name: $NODEGROUP"
    echo "      Desired: $DESIRED, Min: $MIN, Max: $MAX"
    echo ""
    echo "   🔍 Checking NodeGroup in EKS..."
    
    NODEGROUP_INFO=$(aws eks describe-nodegroup \
        --cluster-name "$EKS_CLUSTER_NAME" \
        --nodegroup-name "$NODEGROUP" \
        --region "$REGION" 2>&1)
    NODEGROUP_EXIT_CODE=$?
    
    if [ $NODEGROUP_EXIT_CODE -eq 0 ]; then
        # Check if jq is available
        if command -v jq &> /dev/null; then
            CURRENT_DESIRED=$(echo "$NODEGROUP_INFO" | jq -r '.nodegroup.scalingConfig.desiredSize // 0' 2>/dev/null || echo "0")
            CURRENT_MIN=$(echo "$NODEGROUP_INFO" | jq -r '.nodegroup.scalingConfig.minSize // 0' 2>/dev/null || echo "0")
            CURRENT_MAX=$(echo "$NODEGROUP_INFO" | jq -r '.nodegroup.scalingConfig.maxSize // 0' 2>/dev/null || echo "0")
            STATUS=$(echo "$NODEGROUP_INFO" | jq -r '.nodegroup.status // "UNKNOWN"' 2>/dev/null || echo "UNKNOWN")
        else
            # Fallback if jq is not available - try to extract from JSON manually
            CURRENT_DESIRED=$(echo "$NODEGROUP_INFO" | grep -o '"desiredSize":[0-9]*' | grep -o '[0-9]*' | head -1 || echo "0")
            CURRENT_MIN=$(echo "$NODEGROUP_INFO" | grep -o '"minSize":[0-9]*' | grep -o '[0-9]*' | head -1 || echo "0")
            CURRENT_MAX=$(echo "$NODEGROUP_INFO" | grep -o '"maxSize":[0-9]*' | grep -o '[0-9]*' | head -1 || echo "0")
            STATUS=$(echo "$NODEGROUP_INFO" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 | head -1 || echo "UNKNOWN")
        fi
        
        echo "      ✅ NodeGroup exists"
        echo "         Current: Desired=$CURRENT_DESIRED, Min=$CURRENT_MIN, Max=$CURRENT_MAX"
        echo "         Status: $STATUS"
        
        if [ "$CURRENT_DESIRED" != "$DESIRED" ] || [ "$CURRENT_MIN" != "$MIN" ] || [ "$CURRENT_MAX" != "$MAX" ]; then
            echo "      ⚠️  NodeGroup needs scaling"
            echo "         Target: Desired=$DESIRED, Min=$MIN, Max=$MAX"
        else
            echo "      ✅ NodeGroup is at target size"
        fi
    else
        # Check if it's a ResourceNotFoundException
        if echo "$NODEGROUP_INFO" | grep -q "ResourceNotFoundException"; then
            echo "      ❌ NodeGroup $NODEGROUP does not exist in cluster $EKS_CLUSTER_NAME"
            echo "      ⚠️  This will cause the start workflow to skip NodeGroup scaling"
            echo "      ⚠️  The application will start without NodeGroup scaling (pods only)"
        else
            echo "      ❌ Error checking NodeGroup:"
            echo "$NODEGROUP_INFO" | head -5
        fi
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3: CHECK KUBERNETES WORKLOADS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "$NAMESPACE" ] || [ "$NAMESPACE" == "null" ]; then
    echo "   ⚠️  Namespace not found - cannot check Kubernetes workloads"
else
    echo "   📋 Namespace: $NAMESPACE"
    echo ""
    echo "   🔍 Checking Deployments..."
    
    # Check if kubectl is configured
    if ! kubectl cluster-info &>/dev/null; then
        echo "      ⚠️  kubectl not configured - cannot check Kubernetes workloads"
        echo "      💡 Run: aws eks update-kubeconfig --name $EKS_CLUSTER_NAME --region $REGION"
    else
        DEPLOYMENTS=$(kubectl get deployments -n "$NAMESPACE" -o json 2>/dev/null || echo "{}")
        DEPLOYMENT_COUNT=$(echo "$DEPLOYMENTS" | jq -r '.items | length // 0')
        
        if [ "$DEPLOYMENT_COUNT" -gt 0 ]; then
            echo "      ✅ Found $DEPLOYMENT_COUNT Deployments"
            echo "$DEPLOYMENTS" | jq -r '.items[] | "         - \(.metadata.name): \(.spec.replicas // 0) replicas"' || true
        else
            echo "      ℹ️  No Deployments found"
        fi
        
        echo ""
        echo "   🔍 Checking StatefulSets..."
        STATEFULSETS=$(kubectl get statefulsets -n "$NAMESPACE" -o json 2>/dev/null || echo "{}")
        STATEFULSET_COUNT=$(echo "$STATEFULSETS" | jq -r '.items | length // 0')
        
        if [ "$STATEFULSET_COUNT" -gt 0 ]; then
            echo "      ✅ Found $STATEFULSET_COUNT StatefulSets"
            echo "$STATEFULSETS" | jq -r '.items[] | "         - \(.metadata.name): \(.spec.replicas // 0) replicas"' || true
        else
            echo "      ℹ️  No StatefulSets found"
        fi
        
        echo ""
        echo "   🔍 Checking Pods..."
        PODS=$(kubectl get pods -n "$NAMESPACE" -o json 2>/dev/null || echo "{}")
        RUNNING_PODS=$(echo "$PODS" | jq -r '[.items[] | select(.status.phase == "Running")] | length // 0')
        PENDING_PODS=$(echo "$PODS" | jq -r '[.items[] | select(.status.phase == "Pending")] | length // 0')
        TOTAL_PODS=$(echo "$PODS" | jq -r '.items | length // 0')
        
        echo "      📊 Pods: $RUNNING_PODS Running, $PENDING_PODS Pending, $TOTAL_PODS Total"
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ TEST COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Summary:"
echo "   • Check CloudWatch logs for detailed workflow execution:"
echo "     aws logs tail /aws/lambda/eks-app-controller-controller --follow"
echo ""
echo "   • To start the application, use the dashboard or API:"
echo "     POST https://<api-gateway-url>/start"
echo "     Body: {\"app_name\": \"$APP_NAME\"}"
echo ""

