# EKS App Status - Quick Cheat Sheet

**1-Page Reference for DevOps Engineers**

---

## 🚀 Quick Status Check (30 seconds)

```bash
# Set namespace
export NS="your-namespace"

# One command to see everything
kubectl get pods,deploy,svc,ingress -n $NS

# Quick UP/DOWN check
kubectl get pods -n $NS --field-selector=status.phase=Running | grep -q Running && echo "✅ UP" || echo "❌ DOWN"
```

---

## ✅ App is UP when:

| Check | Command | Expected |
|-------|---------|----------|
| Pods Running | `kubectl get pods -n $NS` | Status=`Running`, READY=`2/2` |
| Deployment OK | `kubectl get deploy -n $NS` | AVAILABLE > 0 |
| Service Routed | `kubectl get endpoints -n $NS` | Shows pod IPs (not empty) |
| Internal Works | `kubectl run test --rm -i --image=curlimages/curl -- curl http://svc:80` | HTTP 200 |
| External Works | `curl https://your-app.com` | HTTP 200 |

---

## ❌ App is DOWN when:

- No running pods
- READY = `0/X`
- No service endpoints
- Curl fails (timeout/refused)
- All pods: `Failed`, `Pending`, `CrashLoopBackOff`

---

## ⚠️ App is DEGRADED when:

- Some pods running, some failing (1/2 pods)
- HTTP 5xx errors from service
- Probe failures but still running
- High restarts (> 5)

---

## 🔍 Essential Commands

```bash
# Check pod details
kubectl describe pod -n $NS <pod-name>
kubectl logs -n $NS <pod-name> --tail=50

# Check probes
kubectl describe pod -n $NS <pod> | grep -A5 "Liveness\|Readiness"

# Test internal service (port-forward)
kubectl port-forward -n $NS svc/<service> 8080:80
curl http://localhost:8080

# Test from inside cluster
kubectl run test-$RANDOM --rm -i --image=curlimages/curl -n $NS -- curl -v http://svc:80

# Check recent events
kubectl get events -n $NS --sort-by='.lastTimestamp' | tail -20
```

---

## 🎯 Decision Tree (Simple)

```
Pods Running? ──[NO]──> ❌ DOWN
     │
    [YES]
     ↓
Containers Ready (X/X)? ──[NO]──> ⚠️ DEGRADED
     │
    [YES]
     ↓
Service Endpoints? ──[NO]──> ❌ DOWN
     │
    [YES]
     ↓
Internal Curl 200? ──[NO]──> ⚠️ DEGRADED
     │
    [YES]
     ↓
External Curl 200? ──[NO]──> Check Ingress/LB
     │
    [YES]
     ↓
   ✅ UP
```

---

## 🛠️ Troubleshooting Red Flags

| Event/Status | Meaning | Action |
|--------------|---------|--------|
| `ImagePullBackOff` | Can't pull image | Check image name/credentials |
| `CrashLoopBackOff` | App keeps crashing | Check logs: `kubectl logs` |
| `Pending` | Can't schedule | Check node resources |
| `0/1 Ready` | Container not ready | Check readiness probe |
| Endpoint `<none>` | No healthy pods | Check pod selector |
| HTTP 502/503/504 | Backend issue | Check app logs, probes |

---

## 📋 Complete Check Script

```bash
#!/bin/bash
NS="${1:-default}"

echo "━━━ Checking $NS ━━━"

# Pods
RUNNING=$(kubectl get pods -n $NS --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
echo "Running Pods: $RUNNING"

# Deployment
AVAIL=$(kubectl get deploy -n $NS -o jsonpath='{.items[0].status.availableReplicas}' 2>/dev/null || echo 0)
echo "Available Replicas: $AVAIL"

# Endpoints
EP=$(kubectl get endpoints -n $NS -o jsonpath='{.items[0].subsets[0].addresses[*].ip}' 2>/dev/null | wc -w)
echo "Endpoints: $EP"

# Result
if [ "$RUNNING" -gt 0 ] && [ "$AVAIL" -gt 0 ] && [ "$EP" -gt 0 ]; then
    echo "✅ STATUS: UP"
else
    echo "❌ STATUS: DOWN/DEGRADED"
fi
```

Save as `check.sh`, then: `chmod +x check.sh && ./check.sh my-namespace`

---

## 🔗 Related Docs

- **Full Guide**: `docs/APP_STATUS_VERIFICATION_CHECKLIST.md`
- **Runbook**: `docs/RUNBOOK.md`
- **Test Guide**: `TEST_GUIDE.md`

---

**Quick Help:**
```bash
kubectl get pods -h      # Pod commands
kubectl describe pod -h  # Describe help
kubectl logs -h          # Logs help
```

---

**Version:** 1.0 | **Created:** 2025-11-21


