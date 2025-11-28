# Kubernetes RBAC Configuration for Controller Lambda

## Problem

The Controller Lambda is getting `403 Forbidden` errors when trying to scale StatefulSets and ReplicaSets:
- Cannot patch `statefulsets/scale`
- Cannot list `replicasets`

## Solution

Apply the RBAC configuration to grant the Lambda the necessary permissions.

## Option 1: Using ServiceAccount with IRSA (Recommended)

If your EKS cluster supports IAM Roles for Service Accounts (IRSA):

1. **Apply the RBAC manifest:**
   ```bash
   kubectl apply -f controller-lambda-rbac.yaml
   ```

2. **Update the Lambda to use the ServiceAccount:**
   - The Lambda needs to be configured to assume the IAM role
   - The ServiceAccount annotation should match the Lambda's IAM role ARN

## Option 2: Using IAM User Mapping (Current Setup)

Since the Lambda authenticates via IAM bearer token, you need to map the IAM role to a Kubernetes user in the `aws-auth` ConfigMap:

1. **Get the current aws-auth ConfigMap:**
   ```bash
   kubectl get configmap aws-auth -n kube-system -o yaml > aws-auth-backup.yaml
   ```

2. **Add the Lambda's IAM role to the mapUsers section:**
   ```yaml
   mapUsers: |
     - userarn: arn:aws:iam::420464349284:role/eks-app-controller-controller-lambda-role
       username: eks-controller-lambda
       groups:
         - eks-controller-lambda-group
   ```

3. **Update the ClusterRoleBinding to reference the user:**
   ```yaml
   subjects:
     - kind: User
       name: eks-controller-lambda
       apiGroup: rbac.authorization.k8s.io
   ```

4. **Apply the updated ConfigMap:**
   ```bash
   kubectl apply -f aws-auth-updated.yaml
   ```

5. **Apply the RBAC manifest:**
   ```bash
   kubectl apply -f controller-lambda-rbac.yaml
   ```

## Option 3: Quick Fix - Update Existing Role

If there's already a Role/ClusterRole for the Lambda, you can patch it:

```bash
kubectl patch clusterrole <existing-role-name> --type='json' -p='[
  {
    "op": "add",
    "path": "/rules/-",
    "value": {
      "apiGroups": ["apps"],
      "resources": ["statefulsets/scale", "replicasets", "replicasets/scale"],
      "verbs": ["get", "list", "patch", "update"]
    }
  }
]'
```

## Verify Permissions

After applying, test by running:
```bash
kubectl auth can-i patch statefulsets/scale --as=system:serviceaccount:kube-system:eks-controller-lambda -n mi-r1-dev
kubectl auth can-i list replicasets --as=system:serviceaccount:kube-system:eks-controller-lambda -n mi-r1-dev
```

## IAM Role ARN

The Lambda's IAM role ARN should be:
```
arn:aws:iam::420464349284:role/eks-app-controller-controller-lambda-role
```

Verify with:
```bash
aws iam get-role --role-name eks-app-controller-controller-lambda-role --query 'Role.Arn'
```

