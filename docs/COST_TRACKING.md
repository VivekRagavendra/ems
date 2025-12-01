# Cost Tracking Documentation

## Overview

The Cost Tracking feature provides daily cost calculations for each application in the EKS cluster. Costs are calculated based on:

- **NodeGroup EC2 instances**: Hourly instance costs × 24 hours
- **Database EC2 instances**: Hourly instance costs × hours running
- **EBS volumes**: Storage costs per GB per month (converted to daily)
- **Network costs**: Data transfer costs based on CloudWatch metrics

## Architecture

### Components

1. **Cost Tracker Lambda** (`lambdas/cost-tracker/lambda_function.py`)
   - Runs daily at 00:30 UTC via EventBridge
   - Calculates costs for all applications
   - Stores results in DynamoDB `app_costs` table

2. **DynamoDB Table: `app_costs`**
   - PK: `app_name`
   - SK: `date` (YYYY-MM-DD format)
   - Stores: `daily_cost`, `projected_monthly_cost`, `savings_month_to_date`, `cost_breakdown`

3. **API Endpoint**: `GET /apps/{app}/cost`
   - Returns latest cost data for an application
   - Returns empty breakdown if no data available

4. **UI Component**: Cost breakdown modal
   - Displays daily, monthly, and savings
   - Shows cost breakdown by component

## Cost Calculation Details

### Instance Pricing

The cost tracker uses a **static pricing map** for common instance types:

- `t3.small`: $0.0208/hour
- `t3.medium`: $0.0416/hour
- `t3.large`: $0.0832/hour
- `m5.large`: $0.096/hour
- `m5.xlarge`: $0.192/hour
- `c5.large`: $0.085/hour
- `r5.large`: $0.126/hour
- ... (see `INSTANCE_PRICE_MAP` in `lambda_function.py`)

**Fallback**: For unknown instance types, estimates $0.015 per vCPU per hour.

### EBS Pricing

- **GP3**: $0.08/GB/month
- **GP2**: $0.10/GB/month
- **IO1/IO2**: $0.125/GB/month

Daily EBS cost = (size_gb × price_per_gb_month) / 30

### Network Pricing

- Default: $0.09 per GB (configurable in `config/config.yaml`)
- Calculated from CloudWatch `NetworkIn` and `NetworkOut` metrics
- Queries last 24 hours of data

### Limitations & Assumptions

1. **Static Pricing**: Uses hardcoded prices for common instance types. For accurate pricing, integrate AWS Pricing API (future enhancement).

2. **Simplified Calculations**:
   - Assumes instances run 24 hours if currently running
   - Does not account for partial hours or state changes
   - Network costs are estimates based on CloudWatch metrics

3. **Savings Calculation**: Currently returns 0. Future enhancement: calculate based on operation logs showing hours app was stopped.

4. **Regional Pricing**: Defaults to `us-east-1`. Update `config/config.yaml` for other regions.

## Configuration

### config/config.yaml

```yaml
cost:
  region: "us-east-1"  # AWS region for price lookup
  aws_price_per_gb: 0.09  # Network cost per GB (USD)
```

## API Usage

### Get Cost Data

```bash
GET /apps/{app_name}/cost

Response:
{
  "app": "mi.dev.mareana.com",
  "daily_cost": 12.50,
  "projected_monthly_cost": 375.00,
  "savings_month_to_date": 0.00,
  "breakdown": {
    "nodegroups": 10.00,
    "databases": 2.00,
    "ebs": 0.30,
    "network": 0.20
  },
  "date": "2024-01-15",
  "timestamp": "2024-01-15T00:30:00Z"
}
```

## Future Enhancements

1. **AWS Pricing API Integration**: Replace static pricing map with real-time pricing API calls
2. **Savings Calculation**: Track hours apps were stopped and calculate actual savings
3. **Cost Trends**: Show cost trends over time (weekly, monthly)
4. **Cost Alerts**: Alert when costs exceed thresholds
5. **Reserved Instance Discounts**: Account for RI discounts in calculations
6. **Spot Instance Pricing**: Support for spot instance cost calculations

## Troubleshooting

### No Cost Data Available

- Check if Cost Tracker Lambda is running (EventBridge rule: `cost-tracker-schedule`)
- Verify Lambda has permissions to read registry and write to `app_costs` table
- Check CloudWatch logs for errors

### Incorrect Costs

- Verify instance types in pricing map match your actual instances
- Check EBS volume types and sizes
- Verify network metrics are available in CloudWatch

### Missing Breakdown Components

- Ensure NodeGroups are properly configured in registry
- Verify database EC2 instance IDs are stored in registry
- Check CloudWatch metrics permissions for network data


