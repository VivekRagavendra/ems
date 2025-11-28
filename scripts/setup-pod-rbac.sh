#!/bin/bash
# Script to set up RBAC permissions for API Handler Lambda to list pods

set -e

echo "🔧 Setting up RBAC permissions for API Handler Lambda to list pods..."
echo ""

# Step 1: Apply RBAC manifest
echo "Step 1: Applying RBAC manifest..."
kubectl apply -f k8s-rbac/api-handler-rbac.yaml

# Step 2: Get current aws-auth ConfigMap
echo ""
echo "Step 2: Updating aws-auth ConfigMap..."
CURRENT_MAP=$(kubectl get configmap aws-auth -n kube-system -o jsonpath='{.data.mapRoles}')

# Check if entry already exists
if echo "$CURRENT_MAP" | grep -q "eks-app-controller-api-handler-lambda-role"; then
    echo "   ⚠️  Entry already exists in aws-auth ConfigMap"
    echo "   Removing old entry..."
    # Remove the old entry
    NEW_MAP=$(echo "$CURRENT_MAP" | grep -v "eks-app-controller-api-handler-lambda-role" | grep -v "eks-api-handler-lambda")
else
    NEW_MAP="$CURRENT_MAP"
fi

# Add the new entry with proper formatting
NEW_ENTRY="    - rolearn: arn:aws:iam::420464349284:role/eks-app-controller-api-handler-lambda-role
      username: eks-api-handler-lambda
      groups:
        - system:authenticated"

# Append the new entry
FINAL_MAP="${NEW_MAP}
${NEW_ENTRY}"

# Update the ConfigMap
kubectl patch configmap aws-auth -n kube-system --type merge -p "{\"data\":{\"mapRoles\":\"${FINAL_MAP}\"}}"

echo ""
echo "✅ RBAC configuration complete!"
echo ""
echo "📋 Verification:"
echo "   - ClusterRole: eks-api-handler-lambda-role"
echo "   - ClusterRoleBinding: eks-api-handler-lambda-binding"
echo "   - aws-auth ConfigMap: Updated with IAM role mapping"
echo ""
echo "🔄 Next steps:"
echo "   1. Wait 10-15 seconds for Kubernetes to propagate changes"
echo "   2. Refresh the dashboard"
echo "   3. Pod counts should now appear!"
echo ""

