# 🚀 Complete START APPLICATION Workflow Implementation

**Date:** November 23, 2025  
**Status:** ✅ **FULLY IMPLEMENTED**

---

## 📋 Overview

This document describes the complete START APPLICATION workflow that executes when a user clicks "Start" on an application in the dashboard.

---

## 🔄 Complete Workflow

### **User Action → Dashboard → API Gateway → Controller Lambda**

```
User clicks "Start" 
  → UI prompts for desired_node_count
  → POST /start { app_name, desired_node_count }
  → Controller Lambda executes 5-step workflow
```

---

## 📝 Step-by-Step Workflow

### **STEP 1: Start PostgreSQL Instances**

**Actions:**
1. For each PostgreSQL instance in `postgres_instances`:
   - Call `ec2.start_instances(InstanceIds=[instance_id])`
   - Poll `ec2.describe_instances()` every 10 seconds
   - Wait until `State.Name == "running"` (max 5 minutes)
   - Capture `PrivateIpAddress`, `State.Name`, `InstanceId`

**Updates:**
- Updates `registry.postgres_instances` with new details:
  ```json
  {
    "instance_id": "i-123...",
    "private_ip": "10.0.1.5",
    "state": "running"
  }
  ```

**Result:**
- Returns list of started instances with IPs and states
- Continues even if some instances fail

---

### **STEP 2: Start Neo4j Instances**

**Actions:**
- Identical to Step 1
- For each Neo4j instance in `neo4j_instances`

**Updates:**
- Updates `registry.neo4j_instances` with new details

---

### **STEP 3: Scale EKS NodeGroups**

**Actions:**
1. For each NodeGroup in `nodegroups`:
   - Use `desired_node_count` from API (or default to 1)
   - Get current NodeGroup config: `eks.describe_nodegroup()`
   - Update scaling: `eks.update_nodegroup_config(scalingConfig={ desiredSize: N })`
   - Poll every 15 seconds until:
     - `status == "ACTIVE"`
     - `health.issues.length == 0` (no health issues)
     - `scalingConfig.desiredSize == target` (max 10 minutes)

**Verification:**
- Checks NodeGroup status and health
- Verifies desired capacity matches target
- Returns health status

**Result:**
```json
{
  "name": "mi-nodegroup",
  "status": "ACTIVE",
  "desired_size": 2,
  "healthy": true
}
```

---

### **STEP 4: Scale Kubernetes Workloads**

**Actions:**
1. **Scale Deployments:**
   - List all Deployments in namespace
   - For each: `kubectl scale deploy <name> --replicas=1`
   - Uses Kubernetes API: `patch_namespaced_deployment_scale()`

2. **Scale ReplicaSets:**
   - List standalone ReplicaSets (skip those owned by Deployments)
   - For each: `kubectl scale rs <name> --replicas=1`
   - Uses Kubernetes API: `patch_namespaced_replica_set_scale()`

3. **Restart DaemonSets:**
   - List all DaemonSets in namespace
   - For each: `kubectl rollout restart ds <name>`
   - Uses Kubernetes API: `patch_namespaced_daemon_set()` with restart annotation

4. **Wait for Pods:**
   - Poll pods every 5 seconds
   - Wait until all pods are `Ready` (max 5 minutes)
   - Check: `pod.status.phase == "Running"` AND all containers `ready == true`

5. **Collect Pod Statuses:**
   - Count `running`, `pending`, `crashloop`, `total`

**Result:**
```json
{
  "deployments": [
    { "name": "app-deployment", "replicas": 1 }
  ],
  "replicasets": [
    { "name": "standalone-rs", "replicas": 1 }
  ],
  "daemonsets": [
    { "name": "app-daemonset", "status": "restarted" }
  ],
  "pods": {
    "running": 3,
    "pending": 0,
    "crashloop": 0,
    "total": 3
  }
}
```

---

### **STEP 5: Verify HTTP Accessibility**

**Actions:**
1. Construct URL: `https://{hostname}{health_url}`
2. Perform HTTP HEAD request:
   - Timeout: 5 seconds
   - SSL verification: disabled (for internal certs)
3. Determine accessibility:
   - **UP**: 200, 301, 302, 401, 403
   - **DOWN**: 500, 502, 503, 504, timeout, connection error
4. Capture metrics:
   - `http_status`: Response code
   - `response_time_ms`: Latency in milliseconds
   - `timestamp`: Unix timestamp

**Updates:**
- Updates `registry.http_latency_ms`
- Updates `registry.last_health_check`

**Result:**
```json
{
  "http_status": 200,
  "response_time_ms": 123,
  "accessible": true,
  "timestamp": 1234567890
}
```

---

## 🔧 Technical Implementation

### **Lambda Configuration**

**Timeout:** 900 seconds (15 minutes)
- Step 1: Up to 5 minutes (EC2 instances)
- Step 2: Up to 5 minutes (EC2 instances)
- Step 3: Up to 10 minutes (NodeGroups)
- Step 4: Up to 5 minutes (Kubernetes workloads)
- Step 5: 5 seconds (HTTP check)
- **Total: ~25 minutes max, but typically 5-10 minutes**

**Memory:** 512 MB
- Increased from 256 MB for Kubernetes operations

**Dependencies:**
- `boto3>=1.28.0`
- `kubernetes>=28.1.0`
- `requests>=2.31.0`
- `urllib3>=2.0.0`

### **IAM Permissions**

**Required:**
- `eks:DescribeCluster` (for Kubernetes auth)
- `eks:DescribeNodegroup`
- `eks:UpdateNodegroupConfig`
- `ec2:StartInstances`
- `ec2:DescribeInstances`
- `dynamodb:GetItem`
- `dynamodb:UpdateItem`

**Kubernetes RBAC:**
- Controller Lambda needs permissions to:
  - `get`, `list`, `patch` Deployments
  - `get`, `list`, `patch` ReplicaSets
  - `get`, `list`, `patch` DaemonSets
  - `get`, `list`, `watch` Pods

---

## 📊 API Specification

### **Request**

```http
POST /start
Content-Type: application/json

{
  "app_name": "mi.dev.mareana.com",
  "desired_node_count": 2  // Optional, defaults to 1
}
```

### **Response**

```json
{
  "success": true,
  "app_name": "mi.dev.mareana.com",
  "namespace": "ingress-nginx",
  "step1_postgres": [
    {
      "instance_id": "i-1234567890abcdef0",
      "private_ip": "10.0.1.5",
      "state": "running"
    }
  ],
  "step2_neo4j": [
    {
      "instance_id": "i-0987654321fedcba0",
      "private_ip": "10.0.1.6",
      "state": "running"
    }
  ],
  "step3_nodegroups": [
    {
      "name": "mi-nodegroup",
      "status": "ACTIVE",
      "desired_size": 2,
      "healthy": true
    }
  ],
  "step4_workloads": {
    "deployments": [
      { "name": "app-deployment", "replicas": 1 }
    ],
    "replicasets": [],
    "daemonsets": [],
    "pods": {
      "running": 3,
      "pending": 0,
      "crashloop": 0,
      "total": 3
    }
  },
  "step5_http": {
    "http_status": 200,
    "response_time_ms": 123,
    "accessible": true,
    "timestamp": 1234567890
  },
  "errors": [],
  "warnings": []
}
```

---

## 🎨 UI Integration

### **User Experience**

1. **User clicks "▶ Start" button**
2. **Prompt appears:**
   ```
   Enter desired node count for NodeGroups:
   
   (Leave empty to use default: 1)
   [Input: 2] [OK] [Cancel]
   ```
3. **Request sent with `desired_node_count`**
4. **Success message shows:**
   ```
   Application mi.dev.mareana.com started successfully!
   
   PostgreSQL: 1 started
   Neo4j: 1 started
   NodeGroups: 1 scaled
   Pods: 3 running
   HTTP: 200 (123ms)
   ```
5. **Dashboard auto-refreshes** (every 15s)

---

## ⏱️ Timeline

**Typical Execution Time:**
- Step 1 (PostgreSQL): 30-60 seconds
- Step 2 (Neo4j): 30-60 seconds
- Step 3 (NodeGroups): 2-5 minutes
- Step 4 (K8s Workloads): 1-3 minutes
- Step 5 (HTTP Check): < 1 second

**Total: 4-10 minutes** (typically)

**Maximum Time:**
- All timeouts combined: ~25 minutes
- Lambda timeout: 15 minutes (safety limit)

---

## 🔍 Error Handling

### **Partial Failures**

The workflow continues even if individual steps fail:

- **Step 1 fails:** Logs error, continues to Step 2
- **Step 2 fails:** Logs error, continues to Step 3
- **Step 3 fails:** Logs error, continues to Step 4
- **Step 4 fails:** Logs error, continues to Step 5
- **Step 5 fails:** Logs error, completes workflow

**Success Criteria:**
- `success: true` if no errors occurred
- `success: false` if any critical errors occurred
- `errors: []` contains all error messages

### **Timeout Handling**

- **EC2 instances:** Returns `state: "pending"` if timeout
- **NodeGroups:** Returns `healthy: false` with warning if timeout
- **Kubernetes pods:** Returns current pod counts even if not all ready
- **HTTP check:** Returns `error: "Timeout"` if timeout

---

## 📝 Registry Updates

The workflow updates DynamoDB registry with:

1. **PostgreSQL instances:** Updated with `private_ip` and `state`
2. **Neo4j instances:** Updated with `private_ip` and `state`
3. **Status:** Set to `"UP"`
4. **HTTP latency:** Updated from Step 5
5. **Last health check:** Updated timestamp

---

## 🧪 Testing

### **Manual Test**

```bash
# Test via API
curl -X POST https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com/start \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "mi.dev.mareana.com",
    "desired_node_count": 2
  }'
```

### **Verify Results**

```bash
# Check DynamoDB
aws dynamodb get-item \
  --table-name eks-app-controller-registry \
  --key '{"app_name": {"S": "mi.dev.mareana.com"}}' \
  --region us-east-1

# Check NodeGroup
aws eks describe-nodegroup \
  --cluster-name mi-eks-cluster \
  --nodegroup-name mi-nodegroup \
  --region us-east-1

# Check EC2 instances
aws ec2 describe-instances \
  --instance-ids i-123... \
  --region us-east-1

# Check Kubernetes pods
kubectl get pods -n <namespace>
```

---

## ✅ Verification Checklist

After starting an application, verify:

- [ ] PostgreSQL instances are `running` with private IPs
- [ ] Neo4j instances are `running` with private IPs
- [ ] NodeGroups are `ACTIVE` and `HEALTHY`
- [ ] NodeGroups have correct `desiredSize`
- [ ] Deployments are scaled to 1 replica
- [ ] Pods are `Running` and `Ready`
- [ ] HTTP endpoint returns 200/30x
- [ ] Registry updated with all new details
- [ ] Dashboard shows status as "UP"

---

## 🚀 Deployment

### **1. Update Infrastructure**

```bash
cd infrastructure
terragrunt apply
# Updates IAM permissions and Lambda timeout/memory
```

### **2. Rebuild Lambda**

```bash
./build-lambdas.sh
```

### **3. Deploy Controller Lambda**

```bash
aws lambda update-function-code \
  --function-name eks-app-controller-controller \
  --zip-file fileb://build/controller.zip \
  --region us-east-1
```

### **4. Update Lambda Configuration**

```bash
aws lambda update-function-configuration \
  --function-name eks-app-controller-controller \
  --timeout 900 \
  --memory-size 512 \
  --region us-east-1
```

---

## 📊 Cost Impact

**Lambda Execution:**
- **Before:** ~5-10 seconds per start
- **After:** ~4-10 minutes per start
- **Cost increase:** ~$0.001 per start (negligible)

**Still well within free tier!**

---

## 🎉 Summary

The complete START APPLICATION workflow is now fully implemented with:

✅ **5-step sequential workflow**  
✅ **EC2 instance waiting and IP capture**  
✅ **NodeGroup polling for ACTIVE/HEALTHY**  
✅ **Kubernetes workload scaling**  
✅ **HTTP accessibility verification**  
✅ **Comprehensive error handling**  
✅ **Registry updates with all details**  
✅ **UI integration with node count input**

**Status:** ✅ **READY FOR DEPLOYMENT**


