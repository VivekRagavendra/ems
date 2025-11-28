# 🔄 Redeploy & Verify Application Status Checking

**Purpose:** Redeploy the system and verify all application status checks are working correctly

**Date:** November 21, 2025

---

## ✅ PRE-DEPLOYMENT CHECKLIST

Before redeploying, verify these prerequisites:

- [ ] AWS credentials are valid and active
- [ ] kubectl access to EKS cluster configured
- [ ] OpenTofu and Terragrunt installed
- [ ] All required tools available (aws-cli, jq, etc.)

**Quick Check:**
```bash
# Verify AWS access
aws sts get-caller-identity

# Verify EKS access
kubectl cluster-info

# Verify tools
which tofu terragrunt jq
```

---

## 🚀 STEP 1: REDEPLOY LAMBDA FUNCTIONS

### 1.1 Rebuild Lambda Packages

```bash
cd /Users/viveks/EMS

# Clean old builds
rm -rf build/
mkdir -p build

# Build Discovery Lambda
cd lambdas/discovery
pip3 install -r requirements.txt -t ../../build/discovery_packages --quiet
cd ../../build
cp -r ../lambdas/discovery/lambda_function.py discovery_packages/
cd discovery_packages && zip -r ../discovery-lambda.zip . -q && cd ../..
echo "✅ Discovery Lambda packaged"

# Build Controller Lambda
cd lambdas/controller
pip3 install -r requirements.txt -t ../../build/controller_packages --quiet
cd ../../build
cp -r ../lambdas/controller/lambda_function.py controller_packages/
cd controller_packages && zip -r ../controller-lambda.zip . -q && cd ../..
echo "✅ Controller Lambda packaged"

# Build Health Monitor Lambda
cd lambdas/health-monitor
pip3 install -r requirements.txt -t ../../build/health_packages --quiet
cd ../../build
cp -r ../lambdas/health-monitor/lambda_function.py health_packages/
cd health_packages && zip -r ../health-monitor-lambda.zip . -q && cd ../..
echo "✅ Health Monitor Lambda packaged"

# Build API Handler Lambda
cd lambdas/api-handler
pip3 install -r requirements.txt -t ../../build/api_packages --quiet
cd ../../build
cp -r ../lambdas/api-handler/lambda_function.py api_packages/
cd api_packages && zip -r ../api-handler-lambda.zip . -q && cd ../..
echo "✅ API Handler Lambda packaged"

cd ..
```

### 1.2 Deploy Lambda Updates

```bash
# Deploy Discovery Lambda
aws lambda update-function-code \
  --function-name eks-app-controller-discovery \
  --zip-file fileb://build/discovery-lambda.zip \
  --region us-east-1 \
  --no-cli-pager

# Wait for update to complete
sleep 5

# Deploy Controller Lambda
aws lambda update-function-code \
  --function-name eks-app-controller-controller \
  --zip-file fileb://build/controller-lambda.zip \
  --region us-east-1 \
  --no-cli-pager

# Wait for update to complete
sleep 5

# Deploy Health Monitor Lambda (with fixed status logic)
aws lambda update-function-code \
  --function-name eks-app-controller-health-monitor \
  --zip-file fileb://build/health-monitor-lambda.zip \
  --region us-east-1 \
  --no-cli-pager

# Wait for update to complete
sleep 5

# Deploy API Handler Lambda
aws lambda update-function-code \
  --function-name eks-app-controller-api-handler \
  --zip-file fileb://build/api-handler-lambda.zip \
  --region us-east-1 \
  --no-cli-pager

echo ""
echo "✅ All Lambda functions updated!"
```

### 1.3 Verify Lambda Deployments

```bash
# Check all Lambda functions are active
for FUNC in discovery controller health-monitor api-handler; do
  echo "Checking eks-app-controller-$FUNC..."
  aws lambda get-function \
    --function-name eks-app-controller-$FUNC \
    --region us-east-1 \
    --query '{Name:Configuration.FunctionName,State:Configuration.State,LastModified:Configuration.LastModified}' \
    --output table
done
```

**Expected Output:**
- State: `Active`
- LastModified: Recent timestamp

---

## 🔍 STEP 2: TRIGGER DISCOVERY & HEALTH CHECK

### 2.1 Run Discovery

```bash
echo "Running application discovery..."
aws lambda invoke \
  --function-name eks-app-controller-discovery \
  --region us-east-1 \
  --log-type Tail \
  /tmp/discovery-result.json \
  --no-cli-pager

echo ""
echo "Discovery Result:"
cat /tmp/discovery-result.json | jq
```

**Expected Output:**
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Discovery completed\", \"apps_discovered\": 15, ...}"
}
```

### 2.2 Run Health Monitor

```bash
echo ""
echo "Running health check..."
aws lambda invoke \
  --function-name eks-app-controller-health-monitor \
  --region us-east-1 \
  --log-type Tail \
  /tmp/health-result.json \
  --no-cli-pager

echo ""
echo "Health Check Result:"
cat /tmp/health-result.json | jq
```

**Expected Output:**
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Health check completed\", \"apps_checked\": 15, \"results\": [...]}"
}
```

---

## ✅ STEP 3: VERIFY APPLICATION STATUS CHECKS

### 3.1 Check All Applications in DynamoDB

```bash
echo "Fetching all applications from registry..."
aws dynamodb scan \
  --table-name eks-app-controller-registry \
  --region us-east-1 \
  --projection-expression "app_name,#s,last_health_check,hostnames" \
  --expression-attribute-names '{"#s":"status"}' \
  --output json | jq -r '.Items[] | "\(.app_name.S): \(.status.S)"' | sort
```

**Expected Output:**
```
ai360.dev.mareana.com: UP
ebr.dev.mareana.com: UP
flux.dev.mareana.com: UP
grafana.dev.mareana.com: UP
gtag.dev.mareana.com: UP
k8s-dashboard.dev.mareana.com: UP
mi-app-airflow.cloud.mareana.com: UP
mi-r1-airflow.dev.mareana.com: UP
mi-r1-spark.dev.mareana.com: UP
mi-r1.dev.mareana.com: UP
mi-spark.dev.mareana.com: UP
mi.dev.mareana.com: UP
prometheus.dev.mareana.com: UP
vsm-bms.dev.mareana.com: UP
vsm.dev.mareana.com: UP
```

### 3.2 Verify Specific Application Details

Pick a few key applications to verify in detail:

**Check mi.dev.mareana.com:**
```bash
aws dynamodb get-item \
  --table-name eks-app-controller-registry \
  --key '{"app_name": {"S": "mi.dev.mareana.com"}}' \
  --region us-east-1 | jq '{
    app_name: .Item.app_name.S,
    status: .Item.status.S,
    hostnames: .Item.hostnames.L[].S,
    nodegroups: [.Item.nodegroups.L[]?.M | {name: .name.S, desired: .desired_size.N}],
    postgres: .Item.postgres_instances.L[].S,
    neo4j: .Item.neo4j_instances.L[].S,
    last_check: .Item.last_health_check.S
  }'
```

**Check grafana.dev.mareana.com:**
```bash
aws dynamodb get-item \
  --table-name eks-app-controller-registry \
  --key '{"app_name": {"S": "grafana.dev.mareana.com"}}' \
  --region us-east-1 | jq '{
    app_name: .Item.app_name.S,
    status: .Item.status.S,
    hostnames: .Item.hostnames.L[].S,
    nodegroups: [.Item.nodegroups.L[]?.M | {name: .name.S, desired: .desired_size.N}],
    last_check: .Item.last_health_check.S
  }'
```

---

## 🧪 STEP 4: VERIFY STATUS LOGIC (CRITICAL TESTS)

### Test 1: Verify Apps with Ingress Show as UP

**Applications with Ingress should show as UP:**

```bash
echo "=== Test 1: Apps with Ingress ==="
for APP in mi.dev.mareana.com grafana.dev.mareana.com prometheus.dev.mareana.com; do
  STATUS=$(aws dynamodb get-item \
    --table-name eks-app-controller-registry \
    --key "{\"app_name\": {\"S\": \"$APP\"}}" \
    --region us-east-1 \
    --query 'Item.status.S' \
    --output text 2>/dev/null)
  
  if [ "$STATUS" = "UP" ]; then
    echo "✅ $APP: $STATUS"
  else
    echo "❌ $APP: $STATUS (EXPECTED: UP)"
  fi
done
```

### Test 2: Verify NodeGroup Status Detection

**Check if NodeGroups are being monitored correctly:**

```bash
echo ""
echo "=== Test 2: NodeGroup Status ==="

# Get an app with NodeGroups
APP="mi.dev.mareana.com"

# Get NodeGroup info from DynamoDB
NG_NAME=$(aws dynamodb get-item \
  --table-name eks-app-controller-registry \
  --key "{\"app_name\": {\"S\": \"$APP\"}}" \
  --region us-east-1 \
  --query 'Item.nodegroups.L[0].M.name.S' \
  --output text 2>/dev/null)

if [ -n "$NG_NAME" ] && [ "$NG_NAME" != "None" ]; then
  echo "NodeGroup: $NG_NAME"
  
  # Check actual NodeGroup desired size
  DESIRED=$(aws eks describe-nodegroup \
    --cluster-name mi-eks-cluster \
    --nodegroup-name "$NG_NAME" \
    --region us-east-1 \
    --query 'nodegroup.scalingConfig.desiredSize' \
    --output text 2>/dev/null)
  
  echo "Desired Size: $DESIRED"
  
  if [ "$DESIRED" -gt 0 ]; then
    echo "✅ NodeGroup is scaled UP (desired=$DESIRED)"
  else
    echo "⚠️  NodeGroup is scaled DOWN (desired=$DESIRED)"
  fi
else
  echo "⚠️  No NodeGroup found for $APP (Ingress-only app)"
fi
```

### Test 3: Verify Database Tagging

**Check if databases are properly tagged:**

```bash
echo ""
echo "=== Test 3: Database Tagging ==="

# Get all EC2 instances tagged as databases
aws ec2 describe-instances \
  --filters "Name=tag:Component,Values=postgres,neo4j" \
  --region us-east-1 \
  --query 'Reservations[].Instances[].[InstanceId,State.Name,Tags[?Key==`AppName`].Value|[0],Tags[?Key==`Component`].Value|[0],Tags[?Key==`Shared`].Value|[0]]' \
  --output table

echo ""
echo "Shared Databases (should NOT be stopped):"
aws ec2 describe-instances \
  --filters "Name=tag:Shared,Values=true" \
  --region us-east-1 \
  --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`AppName`].Value|[0],Tags[?Key==`Component`].Value|[0],State.Name]' \
  --output table
```

### Test 4: API Endpoint Testing

**Test all API endpoints:**

```bash
echo ""
echo "=== Test 4: API Endpoints ==="

API_URL="https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com"

# Test 1: List all apps
echo "Test: GET /apps"
curl -s "$API_URL/apps" | jq -r '.[] | "\(.app_name): \(.status)"' | head -5
echo ""

# Test 2: Get specific app
echo "Test: GET /apps/{app_name}"
curl -s "$API_URL/apps/mi.dev.mareana.com" | jq '{app_name, status, nodegroups: [.nodegroups[]?.name]}'
echo ""

# Test 3: Health endpoint
echo "Test: GET /health"
curl -s "$API_URL/health" | jq
```

---

## 📊 STEP 5: COMPREHENSIVE STATUS VERIFICATION

### 5.1 Verify Using Kubectl (Ground Truth)

For each critical application, verify status using kubectl:

**App: mi.dev.mareana.com**
```bash
echo "=== Kubernetes Verification: mi.dev.mareana.com ==="

# Check namespace
kubectl get namespace mi

# Check pods
kubectl get pods -n mi

# Check services
kubectl get svc -n mi

# Check ingress
kubectl get ingress -n mi

# Summary
PODS=$(kubectl get pods -n mi --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
if [ "$PODS" -gt 0 ]; then
  echo "✅ Kubernetes: $PODS pod(s) running"
else
  echo "❌ Kubernetes: No pods running"
fi

# Compare with DynamoDB status
DB_STATUS=$(aws dynamodb get-item \
  --table-name eks-app-controller-registry \
  --key '{"app_name": {"S": "mi.dev.mareana.com"}}' \
  --region us-east-1 \
  --query 'Item.status.S' \
  --output text)

echo "DynamoDB Status: $DB_STATUS"

if [ "$PODS" -gt 0 ] && [ "$DB_STATUS" = "UP" ]; then
  echo "✅ STATUS MATCH: Kubernetes and DynamoDB agree (UP)"
elif [ "$PODS" -eq 0 ] && [ "$DB_STATUS" = "DOWN" ]; then
  echo "✅ STATUS MATCH: Kubernetes and DynamoDB agree (DOWN)"
else
  echo "❌ STATUS MISMATCH: Kubernetes ($PODS pods) vs DynamoDB ($DB_STATUS)"
fi
```

### 5.2 Verify Ingress Accessibility

Test if applications are actually accessible:

```bash
echo ""
echo "=== Ingress Accessibility Test ==="

for APP in mi.dev.mareana.com grafana.dev.mareana.com prometheus.dev.mareana.com; do
  echo -n "Testing $APP: "
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$APP" 2>/dev/null || echo "000")
  
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "✅ HTTP $HTTP_CODE (Accessible)"
  elif [ "$HTTP_CODE" = "000" ]; then
    echo "⚠️  Timeout/Connection refused"
  else
    echo "⚠️  HTTP $HTTP_CODE"
  fi
done
```

---

## 🎯 STEP 6: FINAL VERIFICATION CHECKLIST

Run this comprehensive verification:

```bash
#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  FINAL VERIFICATION CHECKLIST                                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# 1. Lambda Functions
echo "✓ Checking Lambda Functions..."
LAMBDA_COUNT=$(aws lambda list-functions --region us-east-1 --query 'Functions[?starts_with(FunctionName, `eks-app-controller-`)].FunctionName' --output text | wc -w)
if [ "$LAMBDA_COUNT" -eq 4 ]; then
  echo "  ✅ All 4 Lambda functions deployed"
else
  echo "  ❌ Expected 4 Lambda functions, found $LAMBDA_COUNT"
fi

# 2. DynamoDB Table
echo "✓ Checking DynamoDB Table..."
TABLE_STATUS=$(aws dynamodb describe-table --table-name eks-app-controller-registry --region us-east-1 --query 'Table.TableStatus' --output text 2>/dev/null)
if [ "$TABLE_STATUS" = "ACTIVE" ]; then
  echo "  ✅ DynamoDB table is ACTIVE"
else
  echo "  ❌ DynamoDB table status: $TABLE_STATUS"
fi

# 3. Application Count
echo "✓ Checking Application Discovery..."
APP_COUNT=$(aws dynamodb scan --table-name eks-app-controller-registry --region us-east-1 --select COUNT --output json | jq -r '.Count')
if [ "$APP_COUNT" -ge 15 ]; then
  echo "  ✅ $APP_COUNT applications discovered"
else
  echo "  ⚠️  Only $APP_COUNT applications discovered (expected 15)"
fi

# 4. Health Status Accuracy
echo "✓ Checking Health Status Accuracy..."
UP_COUNT=$(aws dynamodb scan --table-name eks-app-controller-registry --region us-east-1 --filter-expression "#s = :status" --expression-attribute-names '{"#s":"status"}' --expression-attribute-values '{":status":{"S":"UP"}}' --select COUNT --output json | jq -r '.Count')
echo "  ✅ $UP_COUNT applications showing as UP"

# 5. API Gateway
echo "✓ Checking API Gateway..."
API_RESPONSE=$(curl -s "https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com/health" | jq -r '.status' 2>/dev/null)
if [ "$API_RESPONSE" = "healthy" ]; then
  echo "  ✅ API Gateway is accessible"
else
  echo "  ⚠️  API Gateway response: $API_RESPONSE"
fi

# 6. Shared Database Protection
echo "✓ Checking Shared Database Protection..."
SHARED_DB_COUNT=$(aws ec2 describe-instances --filters "Name=tag:Shared,Values=true" "Name=instance-state-name,Values=running" --region us-east-1 --query 'Reservations[].Instances[]' --output json | jq '. | length')
if [ "$SHARED_DB_COUNT" -gt 0 ]; then
  echo "  ✅ $SHARED_DB_COUNT shared database(s) identified and protected"
else
  echo "  ⚠️  No shared databases found"
fi

# 7. EventBridge Rules
echo "✓ Checking EventBridge Rules..."
RULE_COUNT=$(aws events list-rules --region us-east-1 --name-prefix eks-app-controller --query 'Rules' --output json | jq '. | length')
if [ "$RULE_COUNT" -ge 2 ]; then
  echo "  ✅ $RULE_COUNT EventBridge rules configured"
else
  echo "  ⚠️  Only $RULE_COUNT EventBridge rules found (expected 2)"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  VERIFICATION COMPLETE                                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
```

---

## ✅ SUCCESS CRITERIA

Your deployment is successful if:

- [x] All 4 Lambda functions show State = `Active`
- [x] DynamoDB table shows Status = `ACTIVE`
- [x] 15 applications discovered
- [x] All running applications show status = `UP`
- [x] Applications with Ingress show as `UP` (fixed logic)
- [x] Stopped applications show status = `DOWN`
- [x] Shared databases are tagged with `Shared=true`
- [x] API Gateway returns valid responses
- [x] Kubernetes status matches DynamoDB status
- [x] Ingress endpoints are accessible

---

## 🚨 TROUBLESHOOTING

### Issue: App shows DOWN but pods are running

**Diagnosis:**
```bash
# Check health monitor Lambda logs
aws logs tail /aws/lambda/eks-app-controller-health-monitor --follow --region us-east-1
```

**Solution:**
The health monitor logic should detect apps via Ingress. Verify the fix is deployed:
```bash
# Check if fixed code is deployed
aws lambda get-function --function-name eks-app-controller-health-monitor --region us-east-1 --query 'Configuration.LastModified'
```

### Issue: NodeGroup not found

**Diagnosis:**
```bash
# Check if NodeGroups are tagged
aws eks list-nodegroups --cluster-name mi-eks-cluster --region us-east-1
```

**Solution:**
Run the tagging script:
```bash
/Users/viveks/EMS/scripts/tag-nodegroups.sh
```

### Issue: Databases not tagged

**Diagnosis:**
```bash
# Check EC2 tags
aws ec2 describe-instances --region us-east-1 --filters "Name=tag:Component,Values=postgres,neo4j" --query 'Reservations[].Instances[].Tags'
```

**Solution:**
Run the database tagging script:
```bash
/Users/viveks/EMS/scripts/smart-tag-databases.sh
```

---

## 📝 VERIFICATION REPORT TEMPLATE

After completing all checks, document your results:

```markdown
# Verification Report

**Date:** [Date/Time]
**Performed By:** [Your Name]

## Deployment Status
- [ ] Lambda functions redeployed
- [ ] Discovery executed successfully
- [ ] Health monitor executed successfully

## Application Status Verification
- [ ] 15 applications discovered
- [ ] All running apps show as UP
- [ ] Status logic working correctly
- [ ] Kubernetes status matches DynamoDB

## Database Protection
- [ ] PostgreSQL databases tagged
- [ ] Neo4j databases tagged
- [ ] Shared databases identified

## API Testing
- [ ] List apps endpoint working
- [ ] Get app details endpoint working
- [ ] Health endpoint responding

## Issues Found
[None / List any issues]

## Conclusion
✅ System verified and operational
⚠️  Minor issues (list)
❌ Critical issues (list)
```

---

**Created:** November 21, 2025  
**Version:** 1.0  
**Purpose:** Redeploy and verify application status checking

