# User Access Guide

## 🌐 How Users Access the Dashboard

### Access Method 1: S3 Static Website (Simplest)

**URL Format:**
```
http://<bucket-name>.s3-website-<region>.amazonaws.com
```

**Example:**
```
http://eks-app-controller-ui.s3-website-us-east-1.amazonaws.com
```

**Steps for Users:**
1. Open web browser
2. Navigate to the S3 website URL
3. Dashboard loads automatically
4. No login required (unless you add authentication)

**Pros:**
- ✅ Simple to set up
- ✅ No additional cost
- ✅ Fast regional access

**Cons:**
- ⚠️ HTTP only (no HTTPS)
- ⚠️ No custom domain
- ⚠️ Public access (anyone with URL can access)

### Access Method 2: CloudFront (Recommended for Production)

**URL Format:**
```
https://<distribution-id>.cloudfront.net
```

**Example:**
```
https://d1234abcd5678.cloudfront.net
```

**Or with custom domain:**
```
https://app-controller.yourcompany.com
```

**Steps for Users:**
1. Open web browser
2. Navigate to CloudFront URL or custom domain
3. Dashboard loads (cached globally)
4. HTTPS automatically enabled

**Pros:**
- ✅ HTTPS enabled (secure)
- ✅ Global CDN (fast worldwide)
- ✅ Custom domain support
- ✅ Better caching

**Cons:**
- ⚠️ Additional cost (~$1-2/month)
- ⚠️ Slightly more complex setup

### Access Method 3: VPN Only (Most Secure)

**Setup:**
1. Deploy S3 website or CloudFront as above
2. Add IP whitelist or VPN requirement
3. Users must be on corporate network/VPN

**Steps for Users:**
1. Connect to corporate VPN
2. Navigate to dashboard URL
3. Access granted (VPN validates)

**Pros:**
- ✅ Maximum security
- ✅ Network-level access control
- ✅ Audit trail via VPN logs

**Cons:**
- ⚠️ Requires VPN infrastructure
- ⚠️ Less convenient for users

## 🔐 User Permissions Required

### For Dashboard Access (End Users)

**No AWS permissions needed!** 

Users only need:
- ✅ Network access to the dashboard URL
- ✅ Web browser (Chrome, Firefox, Safari, Edge)
- ✅ Internet connection

**Users do NOT need:**
- ❌ AWS Console access
- ❌ AWS credentials
- ❌ IAM users or roles
- ❌ Any AWS permissions

**Why?** The dashboard is a static website. The Lambda functions use their own IAM roles to perform actions.

### For Deployment (DevOps/Admins)

**AWS IAM Permissions Required:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:*",
        "dynamodb:*",
        "apigateway:*",
        "events:*",
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:PutRolePolicy",
        "iam:PassRole",
        "s3:*",
        "cloudfront:*",
        "eks:DescribeCluster",
        "eks:DescribeNodegroup",
        "eks:UpdateNodegroupConfig",
        "ec2:DescribeInstances",
        "ec2:StartInstances",
        "ec2:StopInstances"
      ],
      "Resource": "*"
    }
  ]
}
```

See [docs/PREREQUISITES.md](PREREQUISITES.md) for detailed IAM requirements.

## 🔒 Security & Access Control

### Current State (Default)

**Dashboard Access:** Public (anyone with URL)
**API Access:** Public (no authentication)
**Lambda Functions:** Protected by IAM roles

⚠️ **Not recommended for production with sensitive data!**

### Production Security Options

#### Option 1: AWS Cognito (Recommended)

**Setup:**
1. Create Cognito User Pool
2. Add Cognito authentication to API Gateway
3. Users must log in to access dashboard

**User Experience:**
```
1. User visits dashboard URL
2. Redirected to login page
3. Enters username/password
4. Authenticated → Dashboard loads
```

**Cost:** ~$0-5/month (first 50K MAU free)

**Implementation:**
```bash
# Add to API Gateway configuration
aws apigatewayv2 update-api \
  --api-id <api-id> \
  --authorizer-credentials-arn <cognito-pool-arn>
```

#### Option 2: API Keys

**Setup:**
1. Generate API keys in API Gateway
2. Distribute keys to authorized users
3. Users include key in requests

**User Experience:**
```
1. User configured with API key
2. Dashboard includes key automatically
3. Access granted if key is valid
```

**Cost:** Free
**Security:** Basic (keys can be shared/leaked)

#### Option 3: IP Whitelist

**Setup:**
1. Configure CloudFront or API Gateway
2. Add allowed IP ranges
3. Only whitelisted IPs can access

**User Experience:**
```
1. User on corporate network
2. IP automatically whitelisted
3. Access granted
```

**Cost:** Free
**Security:** Network-level protection

#### Option 4: VPN + Private Endpoints

**Setup:**
1. Deploy API Gateway as private
2. Users connect via VPN
3. Access only from private network

**User Experience:**
```
1. User connects to VPN
2. Access internal URL
3. Maximum security
```

**Cost:** VPN infrastructure cost
**Security:** Maximum

### Recommended Security by Environment

| Environment | Recommended Security | Cost |
|-------------|---------------------|------|
| **Development** | No auth (open access) | Free |
| **Internal Tool** | IP whitelist or VPN | Free |
| **Production** | Cognito + HTTPS | ~$5/month |
| **External** | Cognito + MFA + HTTPS | ~$10/month |

## 💰 Daily and Monthly Costs

### Cost Breakdown (Typical Usage)

#### Daily Costs

**With 20 applications, moderate usage:**

```
Lambda Invocations:
  - Discovery: 12/day × $0.0000002 = $0.0000024
  - Health checks: 96/day × $0.0000002 = $0.0000192
  - API calls: 10/day × $0.0000002 = $0.000002
  - Controller: 2/day × $0.0000002 = $0.0000004
  Total Lambda: $0.0000240/day

DynamoDB:
  - Storage: 50 MB × $0.00 = $0 (free tier)
  - Requests: 500/day × $0.00 = $0 (free tier)
  Total DynamoDB: $0.00/day

API Gateway:
  - 20 requests/day × $0.000001 = $0.00002/day
  Total API Gateway: $0.00002/day

S3:
  - Storage: 10 MB × $0.00 = $0 (free tier)
  - Requests: 50/day × $0.00 = $0 (free tier)
  Total S3: $0.00/day

────────────────────────────
TOTAL DAILY COST: ~$0.00004/day
────────────────────────────
```

**That's less than 1/10th of a penny per day!** 

#### Monthly Costs (First Year with Free Tier)

```
Month 1-12 (With AWS Free Tier):
────────────────────────────
Lambda:        $0.00  (1M requests/month free)
DynamoDB:      $0.00  (25 GB + 25 RCU/WCU free)
API Gateway:   $0.00  (1M requests/month free)
EventBridge:   $0.00  (1M events/month free)
S3:            $0.00  (5 GB storage free)
CloudWatch:    $0.00  (5 GB logs free)
────────────────────────────
TOTAL:         $0.00/month ☕ FREE!
────────────────────────────
```

#### Monthly Costs (After Free Tier - Month 13+)

```
Month 13+ (Free Tier Expired):
────────────────────────────────────
Lambda:
  - ~10,000 invocations/month
  - Compute: ~1,000 GB-seconds
  - Cost: $0.20 × 1 = $0.20

DynamoDB:
  - Storage: 50 MB
  - Reads: 10,000/month
  - Writes: 1,000/month
  - Cost: $0.25 (still mostly in free tier)

API Gateway (HTTP):
  - ~5,000 requests/month
  - Cost: $1.00 per million = $0.005
  - Rounded: $0.01

S3:
  - Storage: 10 MB
  - Requests: 1,500/month
  - Cost: $0.50

EventBridge:
  - ~10,000 events/month
  - Cost: $0.00 (always free up to 1M)

CloudWatch Logs:
  - ~500 MB/month
  - Cost: $0.50

Data Transfer:
  - Same region: $0.00
────────────────────────────────────
TOTAL:         $1.46/month
────────────────────────────────────
```

**Rounded up: ~$2/month to be safe**

### Cost by Usage Level

#### Low Usage (1-10 apps, few users)
```
Daily:    $0.00001/day  (< 1/100th penny)
Monthly:  $0.00-0.50/month
Annual:   $0-6/year
```

#### Medium Usage (10-50 apps, moderate users)
```
Daily:    $0.00010/day  (1/100th penny)
Monthly:  $1-3/month
Annual:   $12-36/year
```

#### High Usage (50+ apps, many users)
```
Daily:    $0.00020/day  (1/50th penny)
Monthly:  $3-6/month
Annual:   $36-72/year
```

### Cost Comparison

#### This Solution vs Traditional

```
Traditional EC2-Based:
  - EC2 t3.small (24/7):  $15/month × 30 = $0.50/day
  - RDS PostgreSQL:       $15/month × 30 = $0.50/day
  - ALB:                  $18/month × 30 = $0.60/day
  ──────────────────────────────────────────────
  TOTAL:                  $48/month = $1.60/day

This Serverless Solution:
  - All services:         $1-6/month = $0.03-0.20/day
  ──────────────────────────────────────────────
  
SAVINGS: $42-47/month (87-98% cheaper!)
```

### Cost Optimization Tips

**To reduce costs further:**

1. **Reduce polling frequency:**
   ```hcl
   # Change from every 2 hours to every 4 hours
   schedule_expression = "rate(4 hours)"
   ```
   **Saves:** 50% on Lambda costs

2. **Skip CloudFront:**
   - Use S3 website hosting only
   **Saves:** $1-2/month

3. **Manual discovery:**
   - Remove scheduled discovery
   - Add "Refresh" button in UI
   **Saves:** 70% on Lambda costs

4. **Use smaller Lambda memory:**
   - Already optimized at 256 MB
   - Can't reduce further without performance impact

### Cost Monitoring

**Set up billing alerts:**

```bash
# Alert when costs exceed $5/month
aws cloudwatch put-metric-alarm \
  --alarm-name "EKS-Controller-Cost-Alert" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 21600 \
  --threshold 5.0 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:123456789:billing-alerts
```

**View current costs:**

```bash
# Check month-to-date costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -d "month start" +%Y-%m-01),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=SERVICE
```

## 📊 Cost Summary Table

| Metric | First Year | After Free Tier |
|--------|-----------|-----------------|
| **Per Day** | $0.00 | $0.03-0.06 |
| **Per Week** | $0.00 | $0.21-0.42 |
| **Per Month** | $0-1 | $1-6 |
| **Per Year** | $0-12 | $12-72 |

## ✅ Access Summary

### For End Users (Dashboard Access)

**Required:**
- ✅ Web browser
- ✅ Dashboard URL
- ✅ Internet connection

**NOT Required:**
- ❌ AWS account
- ❌ AWS credentials
- ❌ Any AWS permissions

**Access URL Options:**
1. S3: `http://<bucket>.s3-website-<region>.amazonaws.com` (Free, HTTP)
2. CloudFront: `https://<id>.cloudfront.net` (+ ~$1/month, HTTPS)
3. Custom domain: `https://app-controller.company.com` (+ SSL cert)

### For Admins (Deployment)

**Required:**
- ✅ AWS account with admin permissions
- ✅ OpenTofu/Terragrunt installed
- ✅ AWS CLI configured
- ✅ IAM permissions (see [docs/PREREQUISITES.md](PREREQUISITES.md))

### Security Recommendations

| Environment | Access Control | Cost Impact |
|-------------|----------------|-------------|
| Development | Open (no auth) | $0 |
| Internal | IP whitelist | $0 |
| Production | Cognito + HTTPS | + $5/month |
| External | Cognito + MFA + WAF | + $15/month |

## 🎯 Key Takeaways

1. **Access is simple**: Just share a URL, no AWS setup needed for users
2. **Security is flexible**: Add authentication as needed for your use case
3. **Cost is minimal**: ~$0/day first year, $0.03-0.06/day after
4. **Monthly cost**: $0-1 first year, $1-6 after (less than a coffee!)

**This is one of the most cost-effective solutions possible while maintaining full functionality!**


