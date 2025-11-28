# 🧪 Testing Guide - EKS Application Controller

## ✅ System Status

**All components deployed successfully!**

- ✅ 4 Lambda Functions
- ✅ DynamoDB Registry (15 apps discovered)
- ✅ API Gateway
- ✅ EventBridge Rules (auto-discovery & health monitoring)

---

## 🌐 API Gateway Information

**Base URL:** `https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com`

**Endpoints:**
- `GET /apps` - List all applications
- `POST /start` - Start an application
- `POST /stop` - Stop an application

---

## 🧪 Testing Steps

### 1. Start the Dashboard (Recommended)

```bash
cd /Users/viveks/EMS/ui
npm run dev
```

Access at: **http://localhost:5173**

The dashboard will show:
- All 15 discovered applications
- Current status (UP/DOWN)
- One-click start/stop buttons
- Shared resource warnings

---

### 2. Test via API (Alternative)

#### List All Applications:
```bash
curl -s https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com/apps | jq
```

#### Stop an Application:
```bash
curl -X POST https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com/stop \
  -H "Content-Type: application/json" \
  -d '{"app_name": "ai360.dev.mareana.com"}' | jq
```

**Expected Response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Application stop initiated",
    "app_name": "ai360.dev.mareana.com",
    "nodegroups": ["ai360", "ai360-ondemand"],
    "warnings": [
      "PostgreSQL i-xxx is SHARED - left running",
      "Neo4j i-yyy is SHARED - left running"
    ]
  }
}
```

#### Start an Application:
```bash
curl -X POST https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com/start \
  -H "Content-Type: application/json" \
  -d '{"app_name": "ai360.dev.mareana.com"}' | jq
```

---

### 3. Verify NodeGroup Scaling

After stopping an app, check NodeGroup status:

```bash
aws eks describe-nodegroup \
  --cluster-name mi-eks-cluster \
  --nodegroup-name ai360 \
  --region us-east-1 \
  --query 'nodegroup.scalingConfig' | jq
```

You should see `desiredSize: 0` for stopped apps.

---

### 4. Check DynamoDB Registry

```bash
aws dynamodb scan \
  --table-name eks-app-controller-registry \
  --region us-east-1 \
  --max-items 5 | jq '.Items[] | {app: .app_name.S, status: .status.S}'
```

---

## 🛡️ Shared Database Protection

**3 Shared Databases (Protected):**
- `mi_db` (PostgreSQL) → Used by: ai360, mi, mi-r1
- `vsm_postgres` (PostgreSQL) → Used by: ebr, gtag, vsm-bms, vsm
- `midev_neo4j` (Neo4j) → Used by: ai360, mi, mi-r1

**These will NEVER be stopped automatically!**

When you stop an app using a shared database, you'll see warnings like:
```
⚠️ PostgreSQL i-0be05e57598860101 is SHARED - left running to protect other applications
```

---

## 📊 Discovered Applications

1. ai360.dev.mareana.com
2. ebr.dev.mareana.com
3. flux.dev.mareana.com
4. gtag.dev.mareana.com
5. mi.dev.mareana.com
6. mi-r1.dev.mareana.com
7. vsm.dev.mareana.com
8. vsm-bms.dev.mareana.com
9. mi-app-airflow.cloud.mareana.com
10. mi-spark.dev.mareana.com
11. mi-r1-spark.dev.mareana.com
12. mi-r1-airflow.dev.mareana.com
13. k8s-dashboard.dev.mareana.com
14. grafana.dev.mareana.com
15. prometheus.dev.mareana.com

---

## 🔄 Automatic Operations

**Discovery Lambda** (runs every 2 hours):
- Scans Kubernetes Ingresses
- Maps to NodeGroups and databases
- Updates DynamoDB registry

**Health Monitor Lambda** (runs every 15 minutes):
- Checks NodeGroup status
- Monitors database instances
- Updates application health status

---

## 💰 Cost Summary

**Monthly Cost: ~$5-10**
- Lambda: $2-3 (based on usage)
- DynamoDB: $1-2 (PAY_PER_REQUEST)
- API Gateway: $1-2
- EventBridge: $0 (within free tier)

---

## 📚 Documentation

- `README.md` - Overview and architecture
- `EXECUTIVE_PROPOSAL.md` - Business case (for managers)
- `COMPARISON_EXISTING_VS_NEW.md` - vs Jenkins approach
- `docs/DEPLOYMENT.md` - Deployment guide
- `docs/USER_ACCESS.md` - Access & permissions

---

## 🎯 Next Steps

1. **Test the Dashboard** - Visual interface for all operations
2. **Test Start/Stop** - Try stopping a non-critical app first
3. **Monitor Costs** - Check AWS Cost Explorer after 24 hours
4. **Production Deployment** - Deploy dashboard to S3+CloudFront

---

## 🆘 Troubleshooting

### Dashboard won't load:
```bash
# Check if API is accessible
curl https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com/apps
```

### Lambda errors:
```bash
# Check Lambda logs
aws logs tail /aws/lambda/eks-app-controller-discovery --region us-east-1 --follow
```

### NodeGroup not scaling:
```bash
# Verify IAM permissions
aws iam get-role-policy \
  --role-name eks-app-controller-controller-lambda-role \
  --policy-name eks-app-controller-controller-lambda-policy
```

---

**System fully operational! 🎉**
