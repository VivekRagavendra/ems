# Cost Optimization Guide

This system is designed to be **extremely cost-effective**, with most components staying within AWS free tier or costing pennies per month.

## 💰 Cost Breakdown (Optimized)

### Monthly Costs

| Component | Free Tier | Expected Usage | Cost |
|-----------|-----------|----------------|------|
| **Lambda Functions** | 1M requests + 400K GB-seconds free | ~50K invocations | **$0-1** |
| **DynamoDB** | 25 GB storage + 25 RCU/WCU free | ~100 MB, minimal reads/writes | **$0** |
| **API Gateway (HTTP)** | 1M requests free (first 12 months) | ~5K requests | **$0-1** |
| **EventBridge** | 1M custom events free | ~2K events | **$0** |
| **S3** | 5 GB storage + 20K GET requests free | ~10 MB | **$0** |
| **CloudWatch Logs** | 5 GB ingestion + 5 GB storage free | ~500 MB | **$0** |
| **Data Transfer** | 100 GB free (outbound) | Minimal (same region) | **$0** |
| **TOTAL** | | | **$0-2/month** |

### After Free Tier (Month 13+)

| Component | Cost |
|-----------|------|
| Lambda | $0-2 |
| DynamoDB | $0-1 |
| API Gateway | $1-2 |
| S3 | $0-1 |
| **TOTAL** | **$1-6/month** |

## 🎯 Cost Optimization Strategies

### 1. Lambda Optimization

**Current Usage:**
- Discovery Lambda: Runs hourly = 720 invocations/month
- Health Monitor: Runs every 5 min = 8,640 invocations/month
- Controller Lambda: On-demand (user actions) = ~10-50/month
- API Handler: On-demand (UI loads) = ~100-500/month

**Total: ~10,000 invocations/month** (well within 1M free tier)

**Optimization:**
```hcl
# Reduce discovery frequency
schedule_expression = "rate(2 hours)"  # Instead of 1 hour
# Saves 50% discovery costs

# Reduce health check frequency
schedule_expression = "rate(15 minutes)"  # Instead of 5 minutes
# Saves 66% health check costs
```

**Memory Optimization:**
```python
# Use smaller memory for faster functions
memory_size = 256  # Instead of 512 (cheaper, faster billing)
```

### 2. DynamoDB Optimization

**Current Usage:**
- Storage: ~10-50 MB (tiny)
- Reads: ~10K/month
- Writes: ~1K/month

**Already Optimized:**
- ✅ Pay-per-request mode (no provisioned capacity)
- ✅ Auto-scaling (scales to zero)
- ✅ No unused indexes

**Cost: $0** (well within 25 GB + 25 RCU/WCU free tier)

### 3. API Gateway Optimization

**Use HTTP API (not REST API):**
- ✅ Already using HTTP API
- 70% cheaper than REST API
- $1 per million requests vs $3.50

**First year: FREE** (1M requests free)

**After free tier:**
- 5K requests/month = $0.005 (~$0)
- 50K requests/month = $0.05 (~$0)

### 4. S3 Optimization

**UI Hosting:**
- Static files: ~5-10 MB
- Requests: Minimal (cached by browser)

**Cost: $0** (within 5 GB storage + 20K GET free tier)

**Skip CloudFront:** Use S3 website hosting directly to save costs.

### 5. EventBridge Optimization

**Current Usage:**
- Discovery rule: 720 events/month
- Health check rule: 8,640 events/month
- Total: ~10K events/month

**Cost: $0** (1M events free)

### 6. Data Transfer Optimization

**Keep Everything in Same Region:**
- ✅ All resources in same AWS region
- ✅ No cross-region transfers
- ✅ Minimal data transfer costs

**Cost: $0** (within 100 GB free tier)

## 📊 Cost Reduction Strategies

### Strategy 1: Reduce Polling Frequency

**Change EventBridge schedules in `infrastructure/main.tf`:**

```hcl
# Original (more frequent, higher cost)
resource "aws_cloudwatch_event_rule" "discovery_schedule" {
  schedule_expression = "rate(1 hour)"
}

resource "aws_cloudwatch_event_rule" "health_check_schedule" {
  schedule_expression = "rate(5 minutes)"
}

# Cost-Optimized (less frequent, lower cost)
resource "aws_cloudwatch_event_rule" "discovery_schedule" {
  schedule_expression = "rate(4 hours)"  # Run 4x less often
}

resource "aws_cloudwatch_event_rule" "health_check_schedule" {
  schedule_expression = "rate(30 minutes)"  # Run 6x less often
}
```

**Savings: 70-80% on Lambda invocations**

### Strategy 2: Skip CloudFront

**Use S3 Static Website Hosting Instead:**

Benefits:
- No CloudFront costs
- Simpler setup
- Still fast (regional serving)

Drawback:
- No HTTPS (unless using custom domain with Certificate Manager)
- No global CDN

**For internal use: S3 website hosting is sufficient and FREE**

### Strategy 3: Reduce Lambda Memory

**Lower memory = lower cost:**

```python
# discovery Lambda
memory_size = 256  # Instead of 512

# health-monitor Lambda
memory_size = 256  # Instead of 512

# controller Lambda
memory_size = 384  # Instead of 512
```

**Savings: 25-50% on Lambda costs**

### Strategy 4: On-Demand Discovery

**Instead of scheduled discovery:**
- Remove EventBridge scheduled rule
- Run discovery manually when needed
- Or trigger from UI when user refreshes

**Savings: 100% of discovery Lambda costs**

### Strategy 5: Batch Health Checks

**Check health less frequently:**
- Change from 5 minutes to 30 minutes
- Or only check when user opens dashboard

**Savings: 80-90% of health monitor costs**

## 🆓 Free Tier Usage

### Always Free (No Expiration)

- **Lambda**: 1M requests + 400K GB-seconds **every month**
- **DynamoDB**: 25 GB storage + 25 RCU/WCU **always**
- **EventBridge**: 1M custom events **always**

### 12 Months Free (New AWS Accounts)

- **API Gateway**: 1M HTTP API requests **first 12 months**
- **S3**: 5 GB storage + 20K GET requests **first 12 months**
- **CloudWatch**: 5 GB logs **first 12 months**

**This system stays FREE for first year with new AWS account!**

## 💡 Ultra-Low-Cost Configuration

For absolute minimal cost, use this configuration:

```hcl
# infrastructure/main.tf

# Run discovery once per day only
resource "aws_cloudwatch_event_rule" "discovery_schedule" {
  schedule_expression = "rate(1 day)"
}

# Run health checks once per hour only
resource "aws_cloudwatch_event_rule" "health_check_schedule" {
  schedule_expression = "rate(1 hour)"
}
```

**Monthly invocations:**
- Discovery: 30 invocations/month
- Health checks: 720 invocations/month
- On-demand: ~100 invocations/month
- **Total: ~850 invocations/month**

**Cost: $0** (well within free tier)

## 📈 Cost Scaling

### 10 Applications
- Lambda: ~15K invocations/month
- DynamoDB: ~200 MB storage
- **Cost: $0-1/month**

### 50 Applications
- Lambda: ~50K invocations/month
- DynamoDB: ~1 GB storage
- **Cost: $1-3/month**

### 100 Applications
- Lambda: ~100K invocations/month
- DynamoDB: ~2 GB storage
- **Cost: $2-5/month**

**Still incredibly cheap!**

## 🎯 Recommended Configuration by Use Case

### Development/Testing
```hcl
# Very infrequent checks
discovery_schedule = "rate(12 hours)"
health_check_schedule = "rate(2 hours)"
lambda_memory = 256

# Cost: $0/month
```

### Production (Low Traffic)
```hcl
# Moderate frequency
discovery_schedule = "rate(2 hours)"
health_check_schedule = "rate(15 minutes)"
lambda_memory = 256

# Cost: $0-1/month
```

### Production (High Traffic)
```hcl
# Frequent checks
discovery_schedule = "rate(1 hour)"
health_check_schedule = "rate(5 minutes)"
lambda_memory = 512

# Cost: $1-2/month
```

## 🚀 Extreme Cost Optimization

### Option 1: Serverless Cron Alternative

Instead of EventBridge, use external free services:
- **cron-job.org** (free)
- **Uptime Robot** (free tier)
- Trigger Lambda via webhook

**Savings: Removes EventBridge costs (already free though)**

### Option 2: S3 Only (No CloudFront)

For internal tools:
- Use S3 website hosting
- Skip CloudFront entirely
- Access via S3 URL

**Savings: $0.01-0.50/month**

### Option 3: Manual Discovery

Remove scheduled discovery:
- Add "Refresh" button in UI
- Manually trigger discovery when needed

**Savings: 70% of Lambda costs**

## 💸 Cost Monitoring

### Set Up Billing Alerts

```bash
# Create billing alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "EKS-Controller-Cost-Alert" \
  --alarm-description "Alert when costs exceed $5" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 21600 \
  --evaluation-periods 1 \
  --threshold 5.0 \
  --comparison-operator GreaterThanThreshold
```

### Monitor Costs

```bash
# Check current month costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -d "month start" +%Y-%m-01),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=SERVICE
```

## 📊 Real-World Cost Example

**Scenario:** 20 applications, checking every hour, moderate usage

| Component | Usage | Cost |
|-----------|-------|------|
| Lambda | 20K invocations | $0.00 (free tier) |
| DynamoDB | 500 MB storage, 50K requests | $0.00 (free tier) |
| API Gateway | 2K requests | $0.00 (free tier) |
| S3 | 10 MB storage | $0.00 (free tier) |
| EventBridge | 20K events | $0.00 (free tier) |
| **TOTAL** | | **$0.00/month** |

**After 12 months (free tier expires):**
- API Gateway: ~$0.002
- S3: ~$0.001
- Lambda: ~$0.00 (still in free tier)
- **TOTAL: ~$0.003/month** (less than a penny!)

## ✅ Cost Optimization Checklist

- [x] Use HTTP API (not REST API)
- [x] Use pay-per-request DynamoDB
- [x] Keep all resources in same region
- [x] Use appropriate Lambda memory sizes
- [x] Leverage free tiers
- [ ] Adjust polling frequency as needed
- [ ] Skip CloudFront if not needed
- [ ] Set up billing alerts
- [ ] Monitor actual usage

## 🎯 Summary

**This system is designed to be extremely cost-effective:**

✅ **First 12 months: $0-1/month** (mostly free tier)
✅ **After free tier: $1-5/month** (still very cheap)
✅ **No provisioned capacity** (pay only for what you use)
✅ **Auto-scales to zero** (no cost when idle)
✅ **No servers to maintain** (no EC2 costs)

**For most use cases, this system will cost less than a cup of coffee per month! ☕**


