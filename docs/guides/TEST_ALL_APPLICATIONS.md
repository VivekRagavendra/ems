# 🧪 Test All Applications - Complete Guide

**Purpose:** Comprehensive testing of all 15 applications individually

**Created:** November 22, 2025

---

## 📋 Quick Start

### Test All Applications (Interactive)
```bash
cd /Users/viveks/EMS
./scripts/test-each-application.sh
```

### Test Specific Application
```bash
./scripts/test-each-application.sh mi.dev.mareana.com
```

### Test All Applications (Batch Mode)
```bash
./scripts/test-each-application.sh 2>&1 | tee test-results-$(date +%Y%m%d-%H%M%S).txt
```

---

## 🔍 What Each Test Checks

### TEST 1: DynamoDB Registry Check ✅
**What it checks:**
- Application exists in DynamoDB registry
- Status field is valid (UP/DOWN/DEGRADED)
- Last health check timestamp

**Success criteria:**
- App found in registry
- Status is one of: UP, DOWN, DEGRADED

### TEST 2: Kubernetes Pods Check ✅
**What it checks:**
- Namespace exists
- Pods are running
- Pod readiness status

**Success criteria:**
- At least 1 pod running (for UP apps)
- Pods in Running/Ready state

### TEST 3: Kubernetes Services Check ✅
**What it checks:**
- Services configured in namespace
- Service endpoints exist

**Success criteria:**
- Services found
- Services properly configured

### TEST 4: Kubernetes Ingress Check ✅
**What it checks:**
- Ingress resource exists
- Hostname matches application
- Ingress rules configured

**Success criteria:**
- Ingress found for application hostname
- Proper routing configured

### TEST 5: Ingress HTTP Accessibility ✅
**What it checks:**
- Application accessible via HTTPS
- HTTP response code
- Connection success

**Success criteria:**
- HTTP 200, 301, or 302 response
- No connection timeout

### TEST 6: NodeGroup Status Check ✅
**What it checks:**
- NodeGroups associated with app
- NodeGroup desired size
- Scaling configuration

**Success criteria:**
- NodeGroup exists and queryable
- Desired size > 0 for UP apps

### TEST 7: Database Status Check ✅
**What it checks:**
- PostgreSQL instances
- Neo4j instances
- EC2 instance state
- Shared database tags

**Success criteria:**
- Database instances running (for UP apps)
- Shared databases properly tagged

### TEST 8: API Gateway Endpoint Check ✅
**What it checks:**
- API Gateway responds
- App data returned
- Status field present

**Success criteria:**
- API returns valid response
- App data matches DynamoDB

### TEST 9: Status Consistency Verification ✅
**What it checks:**
- DynamoDB status matches Kubernetes reality
- Expected vs actual status
- Cross-system consistency

**Success criteria:**
- Status is consistent across all systems
- No mismatches detected

---

## 📊 Expected Results for Each Application

### 1. mi.dev.mareana.com
**Expected Status:** UP
- ✅ DynamoDB: UP
- ✅ Kubernetes: Running pods
- ✅ Ingress: Configured
- ✅ HTTP: Accessible
- ⚠️  NodeGroups: May be shared or none
- ✅ Databases: May have dedicated or shared

### 2. ai360.dev.mareana.com
**Expected Status:** UP
- ✅ DynamoDB: UP
- ✅ Kubernetes: Running pods
- ✅ Ingress: Configured
- ✅ HTTP: Accessible

### 3. mi-r1.dev.mareana.com
**Expected Status:** UP
- ✅ DynamoDB: UP
- ✅ Kubernetes: Running pods
- ✅ Ingress: Configured
- ✅ HTTP: Accessible

### 4. grafana.dev.mareana.com
**Expected Status:** UP
- ✅ DynamoDB: UP
- ✅ Kubernetes: Running pods
- ✅ Ingress: Configured
- ✅ HTTP: Accessible (may require auth)

### 5. prometheus.dev.mareana.com
**Expected Status:** UP
- ✅ DynamoDB: UP
- ✅ Kubernetes: Running pods
- ✅ Ingress: Configured
- ✅ HTTP: Accessible

### 6. k8s-dashboard.dev.mareana.com
**Expected Status:** UP
- ✅ DynamoDB: UP
- ✅ Kubernetes: Running pods
- ✅ Ingress: Configured
- ✅ HTTP: Accessible (may require token)

### 7-15. Other Applications
Similar patterns expected for:
- gtag.dev.mareana.com
- vsm.dev.mareana.com
- vsm-bms.dev.mareana.com
- ebr.dev.mareana.com
- flux.dev.mareana.com
- mi-spark.dev.mareana.com
- mi-r1-spark.dev.mareana.com
- mi-app-airflow.cloud.mareana.com
- mi-r1-airflow.dev.mareana.com

---

## 🎯 Running Complete Test Suite

### Step 1: Prepare Environment
```bash
cd /Users/viveks/EMS

# Ensure AWS credentials are valid
aws sts get-caller-identity

# Ensure kubectl access
kubectl cluster-info
```

### Step 2: Run Tests for All Applications
```bash
# Interactive mode (pauses between apps)
./scripts/test-each-application.sh

# Batch mode (saves to file)
./scripts/test-each-application.sh 2>&1 | tee test-results-$(date +%Y%m%d-%H%M%S).txt
```

### Step 3: Review Results
```bash
# Count total tests
grep "Total Tests Run" test-results-*.txt

# Count passed tests
grep "Passed:" test-results-*.txt

# Find failures
grep "❌" test-results-*.txt

# Find warnings
grep "⚠️" test-results-*.txt
```

---

## 📝 Test Results Template

Use this template to document test results:

```markdown
# Application Test Results

**Date:** [Date/Time]
**Tested By:** [Your Name]
**Test Script Version:** 1.0

## Summary
- Total Applications Tested: 15
- Total Tests Run: [Number]
- Passed: [Number]
- Failed: [Number]
- Warnings: [Number]

## Individual Application Results

### mi.dev.mareana.com
- [ ] DynamoDB Registry Check
- [ ] Kubernetes Pods Check
- [ ] Kubernetes Services Check
- [ ] Kubernetes Ingress Check
- [ ] Ingress HTTP Accessibility
- [ ] NodeGroup Status Check
- [ ] Database Status Check
- [ ] API Gateway Endpoint Check
- [ ] Status Consistency Verification
- **Overall Status:** [PASS/FAIL/WARNING]
- **Notes:** [Any observations]

[Repeat for each application...]

## Issues Found
[List any issues discovered]

## Recommendations
[List any recommendations for fixes]
```

---

## 🐛 Common Issues & Fixes

### Issue: "Namespace not found"
**Meaning:** App may not have dedicated namespace or uses different naming
**Fix:** Normal for some apps, check if app shares namespace

### Issue: "No NodeGroups associated"
**Meaning:** App may be Ingress-only or share NodeGroups
**Fix:** Normal for lightweight apps, verify Ingress exists

### Issue: "No running pods"
**Meaning:** Pods may be scaled to 0 or in different namespace
**Fix:** Check if app is intentionally stopped

### Issue: "Connection timeout"
**Meaning:** Ingress not accessible or SSL issues
**Fix:** Check ingress configuration and DNS

### Issue: "Status MISMATCH"
**Meaning:** DynamoDB status doesn't match Kubernetes reality
**Fix:** Trigger health monitor manually:
```bash
aws lambda invoke \
  --function-name eks-app-controller-health-monitor \
  --region us-east-1 \
  /tmp/health.json
```

### Issue: "API endpoint not responding"
**Meaning:** API Gateway issue or app not in registry
**Fix:** Check API Gateway logs, verify app in DynamoDB

---

## 📊 Test Metrics to Track

### Key Performance Indicators
- **Test Pass Rate:** (Passed / Total) × 100%
- **Status Accuracy:** Percentage of apps with consistent status
- **Discovery Coverage:** Percentage of apps in registry
- **Health Check Accuracy:** Percentage of correct UP/DOWN determinations

### Target Metrics
- Test Pass Rate: > 95%
- Status Accuracy: 100%
- Discovery Coverage: 100%
- Health Check Accuracy: 100%

---

## 🔄 Automated Testing Schedule

### Recommended Testing Frequency

**Daily:**
- Quick status check of all apps
- Verify critical apps (mi.dev.mareana.com, etc.)

**Weekly:**
- Full 9-test suite for all apps
- Document and review failures
- Update monitoring if needed

**After Changes:**
- Deploy: Full test suite
- Configuration change: Affected apps only
- New app added: Test discovery and monitoring

---

## 📈 Sample Test Run

### Quick Test (One App)
```bash
time ./scripts/test-each-application.sh mi.dev.mareana.com
```
**Expected Duration:** 30-60 seconds

### Full Test (All Apps)
```bash
time ./scripts/test-each-application.sh 2>&1 | tee full-test-$(date +%Y%m%d).txt
```
**Expected Duration:** 10-15 minutes

---

## ✅ Success Criteria

### Individual Application
✅ All 9 tests pass
✅ Status is consistent
✅ No critical failures
⚠️  Warnings are acceptable for some tests

### Full Test Suite
✅ 100% discovery coverage (15/15 apps)
✅ > 95% test pass rate
✅ Status consistency for all apps
✅ No API endpoint failures

---

## 🎯 Next Steps After Testing

### If All Tests Pass ✅
1. Document results
2. Share with team
3. Schedule regular testing
4. Monitor for changes

### If Tests Fail ❌
1. Review failure details
2. Check logs (CloudWatch, kubectl logs)
3. Verify configurations
4. Re-run health monitor
5. Update registry if needed
6. Retest after fixes

### If Warnings Appear ⚠️
1. Investigate cause
2. Determine if expected
3. Document as known behavior
4. Update test expectations if needed

---

## 📚 Related Documentation

- `APP_STATUS_VERIFICATION_CHECKLIST.md` - Manual verification steps
- `APP_STATUS_QUICK_CHEAT_SHEET.md` - Quick reference
- `REDEPLOY_AND_VERIFY.md` - Redeployment guide
- `TEST_GUIDE.md` - General testing guide

---

## 🔧 Troubleshooting the Test Script

### Script won't run
```bash
chmod +x /Users/viveks/EMS/scripts/test-each-application.sh
```

### Missing dependencies
```bash
# Check required tools
which aws kubectl jq curl

# Install if missing (macOS)
brew install awscli kubectl jq
```

### AWS credentials expired
```bash
aws configure
# or
aws sso login
```

### Kubernetes access issues
```bash
aws eks update-kubeconfig --name mi-eks-cluster --region us-east-1
```

---

**Version:** 1.0  
**Last Updated:** November 22, 2025  
**Maintainer:** DevOps Team

