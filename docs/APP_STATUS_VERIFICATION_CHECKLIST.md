# Application Status Verification Checklist (EKS)

**Purpose:** Verify whether an application running on Amazon EKS is UP or DOWN without using a browser.

**Target Audience:** DevOps Engineers, SRE Teams

---

## Prerequisites

```bash
# Set your application namespace
export NAMESPACE="your-app-namespace"
export APP_NAME="your-app-name"

# Verify kubectl access
kubectl cluster-info
kubectl get nodes
```

---

## ✅ STEP-BY-STEP VERIFICATION CHECKLIST

### **STEP 1: Check Namespace Exists**

```bash
kubectl get namespace $NAMESPACE
```

**Expected Output (UP):**
```
NAME              STATUS   AGE
your-namespace    Active   30d
```

**Indicators:**
- ✅ **UP**: Status = `Active`
- ❌ **DOWN**: Namespace not found or Status ≠ `Active`

---

### **STEP 2: Check Pod Status**

```bash
# List all pods in the namespace
kubectl get pods -n $NAMESPACE

# Detailed view with more info
kubectl get pods -n $NAMESPACE -o wide
```

**Expected Output (UP):**
```
NAME                           READY   STATUS    RESTARTS   AGE
app-deployment-7d8f9b-abc12    2/2     Running   0          5h
app-deployment-7d8f9b-def34    2/2     Running   0          5h
```

**Indicators:**
- ✅ **UP**: 
  - Status = `Running`
  - READY = `X/X` (all containers ready, e.g., 2/2, 3/3)
  - At least 1 pod is Running
- ⚠️ **DEGRADED**:
  - Some pods Running, some not
  - READY = `X/Y` where X < Y (e.g., 1/2)
  - Status = `CrashLoopBackOff`, `ImagePullBackOff`
  - High RESTARTS count (> 5)
- ❌ **DOWN**:
  - No pods found
  - All pods in `Terminating`, `Failed`, `Pending` state
  - Status = `Error`, `Unknown`

**Deep Dive (if issues found):**
```bash
# Check specific pod logs
kubectl logs -n $NAMESPACE <pod-name>

# Check previous container logs (if restarted)
kubectl logs -n $NAMESPACE <pod-name> --previous

# Describe pod for events
kubectl describe pod -n $NAMESPACE <pod-name>
```

---

### **STEP 3: Check Deployment Status**

```bash
# List deployments
kubectl get deployments -n $NAMESPACE

# Detailed deployment info
kubectl describe deployment -n $NAMESPACE $APP_NAME
```

**Expected Output (UP):**
```
NAME             READY   UP-TO-DATE   AVAILABLE   AGE
app-deployment   2/2     2            2           30d
```

**Indicators:**
- ✅ **UP**: 
  - READY = `X/X` (e.g., 2/2)
  - AVAILABLE > 0
  - UP-TO-DATE = AVAILABLE
- ⚠️ **DEGRADED**:
  - READY = `X/Y` where X < Y (e.g., 1/2)
  - AVAILABLE < desired replicas
- ❌ **DOWN**:
  - READY = `0/X`
  - AVAILABLE = 0
  - Deployment not found

**Check Replica Sets:**
```bash
kubectl get rs -n $NAMESPACE
```

---

### **STEP 4: Check Service Endpoints**

```bash
# List services
kubectl get svc -n $NAMESPACE

# Check service endpoints (actual pod IPs)
kubectl get endpoints -n $NAMESPACE
```

**Expected Output (UP):**
```
# Service
NAME          TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
app-service   ClusterIP   10.100.50.123   <none>        80/TCP     30d

# Endpoints
NAME          ENDPOINTS                           AGE
app-service   10.244.1.5:8080,10.244.2.3:8080    30d
```

**Indicators:**
- ✅ **UP**: 
  - Service exists
  - Endpoints show pod IPs (not `<none>`)
  - Multiple IPs = multiple healthy pods
- ❌ **DOWN**:
  - Service not found
  - Endpoints = `<none>` or `<empty>`

---

### **STEP 5: Check Readiness & Liveness Probes**

```bash
# Check probe configuration
kubectl describe pod -n $NAMESPACE <pod-name> | grep -A 10 "Liveness\|Readiness"

# Watch probe failures in events
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | grep -i "probe\|health"
```

**Expected Output (UP):**
```
Liveness:   http-get http://:8080/healthz delay=30s timeout=5s period=10s #success=1 #failure=3
Readiness:  http-get http://:8080/ready delay=5s timeout=3s period=5s #success=1 #failure=3

Events:
<no probe failures>
```

**Indicators:**
- ✅ **UP**: 
  - No probe failure events in recent events
  - Pods in `Ready` state (from Step 2)
- ❌ **DOWN**:
  - Events show: `Liveness probe failed`, `Readiness probe failed`
  - Pods show `0/X` Ready (containers not ready)

**Manual Probe Test:**
```bash
# Execute health check inside the pod
kubectl exec -n $NAMESPACE <pod-name> -- curl -s http://localhost:8080/healthz
kubectl exec -n $NAMESPACE <pod-name> -- curl -s http://localhost:8080/ready
```

Expected: HTTP 200 and healthy response body

---

### **STEP 6: Test Internal Service (ClusterIP)**

```bash
# Option 1: Create a temporary pod to test from inside cluster
kubectl run test-curl --image=curlimages/curl:latest -i --tty --rm -n $NAMESPACE -- sh

# Inside the pod:
curl -v http://app-service.your-namespace.svc.cluster.local:80
curl -v http://app-service:80  # If in same namespace
exit
```

```bash
# Option 2: Use kubectl port-forward
kubectl port-forward -n $NAMESPACE svc/app-service 8080:80

# In another terminal:
curl -v http://localhost:8080
# Press Ctrl+C to stop port-forward
```

**Expected Output (UP):**
```
< HTTP/1.1 200 OK
< Content-Type: application/json
{
  "status": "healthy",
  "version": "1.2.3"
}
```

**Indicators:**
- ✅ **UP**: 
  - HTTP status 200 or 2xx
  - Response body returned
  - Connection successful
- ⚠️ **DEGRADED**:
  - HTTP status 500, 502, 503
  - Connection succeeds but app errors
- ❌ **DOWN**:
  - Connection refused
  - Connection timeout
  - HTTP 404 (service not routing)

---

### **STEP 7: Test External Access (LoadBalancer/Ingress)**

#### **A. For LoadBalancer Services:**

```bash
# Get LoadBalancer external IP/DNS
kubectl get svc -n $NAMESPACE -o wide | grep LoadBalancer

# Test the endpoint
export LB_URL=$(kubectl get svc -n $NAMESPACE app-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl -v http://$LB_URL

# Or with IP:
export LB_IP=$(kubectl get svc -n $NAMESPACE app-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl -v http://$LB_IP
```

#### **B. For Ingress:**

```bash
# Get Ingress details
kubectl get ingress -n $NAMESPACE

# Get Ingress host and path
export INGRESS_HOST=$(kubectl get ingress -n $NAMESPACE app-ingress -o jsonpath='{.spec.rules[0].host}')
export INGRESS_PATH=$(kubectl get ingress -n $NAMESPACE app-ingress -o jsonpath='{.spec.rules[0].http.paths[0].path}')

# Test the endpoint
curl -v https://$INGRESS_HOST$INGRESS_PATH

# Check Ingress backend status
kubectl describe ingress -n $NAMESPACE app-ingress
```

**Expected Output (UP):**
```
# Ingress
NAME          CLASS   HOSTS                 ADDRESS                                    PORTS   AGE
app-ingress   nginx   mi.dev.mareana.com    a1b2c3.us-east-1.elb.amazonaws.com         80,443  30d

# Curl response
< HTTP/1.1 200 OK
< Content-Type: text/html
<!DOCTYPE html>...
```

**Indicators:**
- ✅ **UP**: 
  - Ingress shows ADDRESS (LoadBalancer provisioned)
  - Curl returns HTTP 200-299
  - Response body contains expected content
- ⚠️ **DEGRADED**:
  - HTTP 500, 502, 503 (app errors)
  - Slow response (> 5 seconds)
- ❌ **DOWN**:
  - Ingress ADDRESS = `<none>` or `<pending>`
  - Connection timeout
  - HTTP 404, 502, 503, 504
  - SSL/TLS errors
  - DNS resolution failure

**Check Ingress Controller:**
```bash
# Verify ingress controller is running
kubectl get pods -n ingress-nginx

# Check ingress controller logs
kubectl logs -n ingress-nginx <ingress-controller-pod>
```

---

### **STEP 8: Check Resource Utilization (Optional)**

```bash
# Check if pods are resource-throttled
kubectl top pods -n $NAMESPACE

# Check node resources
kubectl top nodes
```

**Indicators:**
- ⚠️ **DEGRADED**: CPU/Memory near limits (> 80%)
- ❌ **DOWN**: Pods evicted due to resources (check events)

---

### **STEP 9: Check Recent Events**

```bash
# Get recent events for the namespace
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -20

# Filter for errors/warnings
kubectl get events -n $NAMESPACE --field-selector type=Warning --sort-by='.lastTimestamp'
```

**Red Flags (DOWN indicators):**
- `FailedScheduling`: Not enough resources
- `ImagePullBackOff`: Cannot pull container image
- `CrashLoopBackOff`: Application keeps crashing
- `Unhealthy`: Probe failures
- `FailedMount`: Volume mount issues

---

## 🎯 DECISION TREE: IS THE APP UP OR DOWN?

```
┌─────────────────────────────────────────────────────────┐
│ START: Verify Application Status                        │
└─────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │ Are there any Running pods?     │
        │ (kubectl get pods)              │
        └─────────────────────────────────┘
                 ↓                  ↓
              [YES]               [NO]
                 ↓                  ↓
        ┌──────────────┐    ┌──────────────┐
        │ Go to Step 2 │    │ APP IS DOWN  │
        └──────────────┘    │ ❌ No pods   │
                 ↓          └──────────────┘
        ┌─────────────────────────────────┐
        │ Are ALL containers Ready?        │
        │ (READY = X/X, e.g., 2/2)        │
        └─────────────────────────────────┘
                 ↓                  ↓
              [YES]               [NO]
                 ↓                  ↓
        ┌──────────────┐    ┌──────────────┐
        │ Go to Step 3 │    │ APP DEGRADED │
        └──────────────┘    │ ⚠️ Check logs│
                 ↓          └──────────────┘
        ┌─────────────────────────────────┐
        │ Does Service have Endpoints?     │
        │ (kubectl get endpoints)          │
        └─────────────────────────────────┘
                 ↓                  ↓
              [YES]               [NO]
                 ↓                  ↓
        ┌──────────────┐    ┌──────────────┐
        │ Go to Step 4 │    │ APP IS DOWN  │
        └──────────────┘    │ ❌ No routing│
                 ↓          └──────────────┘
        ┌─────────────────────────────────┐
        │ Does internal curl succeed?      │
        │ (ClusterIP test - Step 6)       │
        └─────────────────────────────────┘
                 ↓                  ↓
              [YES]               [NO]
                 ↓                  ↓
        ┌──────────────┐    ┌──────────────┐
        │ Go to Step 5 │    │ APP DEGRADED │
        └──────────────┘    │ ⚠️ App error │
                 ↓          └──────────────┘
        ┌─────────────────────────────────┐
        │ Does external curl succeed?      │
        │ (Ingress/LB test - Step 7)      │
        └─────────────────────────────────┘
                 ↓                  ↓
              [YES]               [NO]
                 ↓                  ↓
        ┌──────────────┐    ┌──────────────┐
        │  APP IS UP   │    │ Check Ingress│
        │  ✅ HEALTHY  │    │ or LoadBalancer
        └──────────────┘    └──────────────┘
```

---

## 📋 QUICK REFERENCE: ONE-LINER STATUS CHECKS

```bash
# Complete health check in one command
kubectl get pods,deployments,svc,ingress -n $NAMESPACE

# Quick pod status
kubectl get pods -n $NAMESPACE --field-selector=status.phase=Running

# Check if ANY pod is ready
kubectl get pods -n $NAMESPACE -o jsonpath='{.items[*].status.containerStatuses[*].ready}' | grep -q true && echo "✅ UP" || echo "❌ DOWN"

# Test internal service
kubectl run test-$RANDOM --image=curlimages/curl:latest --rm -i -n $NAMESPACE -- curl -s -o /dev/null -w "%{http_code}" http://app-service:80

# Test external ingress
curl -s -o /dev/null -w "%{http_code}\n" https://mi.dev.mareana.com
```

---

## 🎯 FINAL DETERMINATION SUMMARY

### **✅ Application is UP when:**
1. ✅ At least 1 pod is `Running` with all containers `Ready` (X/X)
2. ✅ Deployment shows `AVAILABLE > 0`
3. ✅ Service has endpoints (not empty)
4. ✅ Internal curl (ClusterIP) returns HTTP 2xx
5. ✅ External curl (Ingress/LB) returns HTTP 2xx
6. ✅ No probe failures in recent events

### **⚠️ Application is DEGRADED when:**
1. ⚠️ Some pods running, some failing
2. ⚠️ Containers not all ready (e.g., 1/2)
3. ⚠️ Internal service works, but returns 5xx errors
4. ⚠️ High restart count (> 5)
5. ⚠️ Probe failures but pods still running
6. ⚠️ Ingress works but slow responses (> 5s)

### **❌ Application is DOWN when:**
1. ❌ No pods running or all pods failing
2. ❌ Deployment shows `0/X` available
3. ❌ Service has no endpoints
4. ❌ Internal curl fails (connection refused/timeout)
5. ❌ External curl fails (404, 502, 503, 504, timeout)
6. ❌ Persistent probe failures causing pod termination

---

## 🔧 TROUBLESHOOTING COMMANDS

```bash
# Complete diagnostic
kubectl describe deployment -n $NAMESPACE $APP_NAME
kubectl describe pod -n $NAMESPACE <pod-name>
kubectl logs -n $NAMESPACE <pod-name> --all-containers --tail=100

# Check all resources at once
kubectl get all -n $NAMESPACE

# Export full status to file
kubectl get pods,deployments,svc,ingress,endpoints -n $NAMESPACE -o yaml > app-status.yaml

# Check if NodeGroup is scaled to 0 (EKS specific)
aws eks describe-nodegroup \
  --cluster-name your-cluster \
  --nodegroup-name your-nodegroup \
  --query 'nodegroup.scalingConfig.desiredSize' \
  --output text
```

---

## 📝 CHECKLIST TEMPLATE (Copy & Use)

```
Application: ___________________
Namespace: _____________________
Date/Time: _____________________

□ STEP 1: Namespace Active
□ STEP 2: Pods Running (X/X Ready)
□ STEP 3: Deployment Available (X/X)
□ STEP 4: Service Endpoints Exist
□ STEP 5: Probes Passing (No Failures)
□ STEP 6: Internal Curl Success (HTTP 2xx)
□ STEP 7: External Curl Success (HTTP 2xx)
□ STEP 8: Resources Within Limits
□ STEP 9: No Warning Events

FINAL STATUS: [ ] UP  [ ] DEGRADED  [ ] DOWN

Notes:
_________________________________________________
_________________________________________________
```

---

## 🚀 AUTOMATION SCRIPT (Optional)

Save this as `check-app-status.sh`:

```bash
#!/bin/bash
NAMESPACE="${1:-default}"
APP_NAME="${2:-app}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Application Status Check"
echo "Namespace: $NAMESPACE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check Pods
RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
echo "✓ Running Pods: $RUNNING_PODS"

# Check Deployment
AVAILABLE=$(kubectl get deployment -n "$NAMESPACE" "$APP_NAME" -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")
echo "✓ Available Replicas: $AVAILABLE"

# Check Service Endpoints
ENDPOINTS=$(kubectl get endpoints -n "$NAMESPACE" "$APP_NAME" -o jsonpath='{.subsets[0].addresses[*].ip}' 2>/dev/null | wc -w)
echo "✓ Service Endpoints: $ENDPOINTS"

# Determine Status
if [ "$RUNNING_PODS" -gt 0 ] && [ "$AVAILABLE" -gt 0 ] && [ "$ENDPOINTS" -gt 0 ]; then
    echo ""
    echo "✅ STATUS: UP"
    exit 0
elif [ "$RUNNING_PODS" -gt 0 ]; then
    echo ""
    echo "⚠️  STATUS: DEGRADED"
    exit 1
else
    echo ""
    echo "❌ STATUS: DOWN"
    exit 2
fi
```

Usage:
```bash
chmod +x check-app-status.sh
./check-app-status.sh my-namespace my-app
```

---

**Created:** 2025-11-21  
**Version:** 1.0  
**Maintainer:** DevOps Team


