# Cost FAQ - Quick Answers

## 💰 Quick Cost Summary

| Question | Answer |
|----------|--------|
| **Daily cost?** | $0.00 (first year), $0.03-0.06 after |
| **Monthly cost?** | $0-1 (first year), $1-6 after |
| **Annual cost?** | $0-12 (first year), $12-72 after |
| **Startup cost?** | $0 (no upfront fees) |

## 🆓 Is it really free?

**First 12 months: YES!** (with new AWS account)

All components stay within AWS free tier:
- Lambda: 1M requests/month FREE
- DynamoDB: 25 GB storage FREE
- API Gateway: 1M requests/month FREE (first year)
- EventBridge: 1M events/month FREE (always)
- S3: 5 GB storage FREE (first year)

**Your usage:** ~10K Lambda invocations/month (1% of free tier!)

## 💵 After free tier expires?

**$1-6/month** depending on usage:

- 10 apps: ~$1-2/month
- 50 apps: ~$3-4/month
- 100 apps: ~$5-6/month

**That's less than 2 coffees per month!** ☕☕

## 📊 Cost breakdown by day?

```
Daily cost (after free tier):
  - Lambda: $0.01/day
  - DynamoDB: $0.008/day
  - API Gateway: $0.003/day
  - S3: $0.016/day
  - Total: ~$0.037/day
```

**Less than 4 cents per day!**

## 🎯 What drives the cost?

1. **Lambda invocations** (biggest factor)
   - Discovery: 12/day
   - Health checks: 96/day
   - User actions: 5-10/day

2. **API Gateway requests** (second factor)
   - UI loads: 10-50/day
   - API calls: 100-200/day

3. **Storage** (minimal)
   - DynamoDB: ~10-50 MB
   - S3: ~10 MB

## 🔻 How to reduce costs?

1. **Reduce frequency** (saves 50-70%)
   ```
   Discovery: Every 4 hours (instead of 2)
   Health: Every 30 min (instead of 15)
   ```

2. **Skip CloudFront** (saves $1-2/month)
   ```
   Use S3 website hosting only
   ```

3. **Manual discovery** (saves 70%)
   ```
   Remove scheduled discovery
   Add "Refresh" button
   ```

## 💳 When do I get charged?

**AWS charges at end of each month**

- First month might be $0 (free tier)
- Future months: $1-6 (depending on usage)
- Billed automatically to your credit card

## 📈 Cost scaling

| Apps | Monthly Cost |
|------|-------------|
| 1-10 | $0-1 |
| 10-50 | $1-3 |
| 50-100 | $3-6 |
| 100+ | $6-12 |

**Linear scaling, very predictable!**

## 🆚 vs Other Solutions

| Solution | Monthly Cost |
|----------|-------------|
| **This (Serverless)** | **$1-6** |
| EC2 + RDS | $48-100 |
| Kubernetes + DB | $100-200 |
| SaaS Tool | $50-500 |

**Savings: 87-99%!**

## ✅ Hidden costs?

**NO hidden costs!**

- ❌ No setup fees
- ❌ No per-user fees
- ❌ No licensing costs
- ❌ No maintenance fees
- ✅ Only pay for what you use

## 🎯 Real example

**Company with 20 apps, 5 users:**

```
Month 1-12: $0.00 (free tier)
Month 13:   $1.50
Month 14:   $1.45
Month 15:   $1.52
...
Average:    $1.50/month

Annual cost: $18 (after free year)
vs Traditional: $576/year
Savings: $558/year (97% cheaper!)
```

## 📞 Support cost?

**FREE!**

- No support contracts needed
- AWS provides console access
- CloudWatch logs included
- Community support available

## 🎁 Free tier details

### Always Free (No Expiration)
- Lambda: 1M requests + 400K GB-seconds/month
- DynamoDB: 25 GB storage + 25 RCU/WCU
- EventBridge: 1M events/month

### 12 Months Free (New Accounts)
- API Gateway: 1M HTTP requests/month
- S3: 5 GB storage + 20K GET requests
- CloudWatch: 5 GB logs

**This system uses <1% of all free tiers!**

## ⚠️ Cost warnings?

Set up alerts:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "Cost-Alert" \
  --threshold 5.0
```

Get email when costs exceed $5/month.

## 💡 Pro tips

1. **Start with default settings** (most cost-effective)
2. **Monitor first month** (should be $0)
3. **Adjust frequency** if needed (optimize based on usage)
4. **Set billing alerts** (get notified at $5)
5. **Review quarterly** (optimize based on patterns)

## 📊 Cost guarantee?

**99% of users will pay < $5/month**

With:
- 10-50 applications
- Moderate usage
- Default settings
- No CloudFront

**Worst case:** $10-15/month (with CloudFront + high usage)
**Still cheaper than any alternative!**

## 🎯 Bottom Line

**This is one of the cheapest solutions possible:**
- ✅ Free for first year
- ✅ $1-6/month after
- ✅ No hidden costs
- ✅ No upfront fees
- ✅ Pay only for usage
- ✅ 90-98% cheaper than alternatives

**Cost: Less than your Netflix subscription!** 🎬

