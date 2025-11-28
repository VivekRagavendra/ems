# Pod Status RBAC Setup Guide

This guide explains how to grant the API Handler Lambda permission to list pods so the dashboard can display pod counts.

## Prerequisites

- `kubectl` configured to access your EKS cluster
- Permissions to modify Kubernetes RBAC resources and the `aws-auth` ConfigMap

## Quick Setup

Run the setup script:
```bash
./scripts/setup-pod-rbac.sh
```

## Manual Setup

### Step 1: Apply RBAC Manifest

```bash
kubectl apply -f k8s-rbac/api-handler-rbac.yaml
```

This creates:
- **ClusterRole**: `eks-api-handler-lambda-role` with permissions to list pods
- **ClusterRoleBinding**: `eks-api-handler-lambda-binding` that binds the role to the Lambda's Kubernetes user

### Step 2: Update aws-auth ConfigMap

Edit the `aws-auth` ConfigMap to map the Lambda's IAM role to a Kubernetes user:

```bash
kubectl edit configmap aws-auth -n kube-system
```

Add this entry to the `mapRoles` section (maintain proper YAML indentation):

```yaml
data:
  mapRoles: |
    # ... existing entries ...
    
    - rolearn: arn:aws:iam::420464349284:role/eks-app-controller-api-handler-lambda-role
      username: eks-api-handler-lambda
      groups:
        - system:authenticated
```

**Important**: 
- The entry must be in the `mapRoles` section (not `mapUsers`)
- Maintain proper YAML indentation (2 spaces)
- The `username` must match the subject in the ClusterRoleBinding (`eks-api-handler-lambda`)

### Step 3: Verify Configuration

Check that the RBAC resources exist:
```bash
kubectl get clusterrole eks-api-handler-lambda-role
kubectl get clusterrolebinding eks-api-handler-lambda-binding
```

Verify the aws-auth ConfigMap:
```bash
kubectl get configmap aws-auth -n kube-system -o yaml | grep -A 4 "api-handler"
```

Test permissions:
```bash
kubectl auth can-i list pods --namespace=ebr-dev --as=eks-api-handler-lambda
# Should return: yes
```

### Step 4: Wait and Refresh

1. Wait 10-15 seconds for Kubernetes to propagate the changes
2. Refresh the dashboard
3. Pod counts should now appear!

## Troubleshooting

### Still seeing 401 Unauthorized errors?

1. **Verify aws-auth ConfigMap format**:
   ```bash
   kubectl get configmap aws-auth -n kube-system -o yaml
   ```
   Check that:
   - The entry is in `mapRoles` (not `mapUsers`)
   - The `rolearn` matches exactly: `arn:aws:iam::420464349284:role/eks-app-controller-api-handler-lambda-role`
   - The `username` is exactly: `eks-api-handler-lambda`
   - YAML indentation is correct (2 spaces)

2. **Check ClusterRoleBinding**:
   ```bash
   kubectl get clusterrolebinding eks-api-handler-lambda-binding -o yaml
   ```
   Verify the subject matches:
   ```yaml
   subjects:
   - kind: User
     name: eks-api-handler-lambda
     apiGroup: rbac.authorization.k8s.io
   ```

3. **Test authentication**:
   ```bash
   kubectl auth can-i list pods --namespace=ebr-dev --as=eks-api-handler-lambda
   ```

4. **Check Lambda logs**:
   ```bash
   aws logs tail /aws/lambda/eks-app-controller-api-handler --follow
   ```
   Look for "✅ Pod state" messages instead of "401 Unauthorized"

### Pod counts still showing 0?

- Verify pods exist in the namespace: `kubectl get pods -n <namespace>`
- Check Lambda logs for errors
- Ensure the namespace mapping is correct in the API Handler Lambda

## What Gets Created

- **ClusterRole** (`eks-api-handler-lambda-role`): Grants `list`, `get`, `watch` permissions on pods and namespaces
- **ClusterRoleBinding** (`eks-api-handler-lambda-binding`): Binds the ClusterRole to the Kubernetes user `eks-api-handler-lambda`
- **aws-auth ConfigMap entry**: Maps the Lambda's IAM role ARN to the Kubernetes username `eks-api-handler-lambda`

## Security Notes

- The Lambda only has read-only permissions (list, get, watch)
- Permissions are scoped to pods and namespaces only
- No write or delete permissions are granted

