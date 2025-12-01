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
   - SK: `date` (YYYY-MM-DD format) or `latest` for summary
   - Daily records store: `daily_cost`, `yesterday_cost`, `cost_breakdown`, `timestamp`
   - Latest record stores: `daily_cost`, `yesterday_cost`, `projected_monthly_cost`, `mtd_cost`, `breakdown`, `month`, `updated_at`

3. **API Endpoint**: `GET /apps/{app}/cost`
   - Returns latest cost data for an application
   - Returns empty breakdown if no data available

4. **UI Component**: Cost breakdown modal
   - Displays: Yesterday's Cost, Projected Monthly Cost, Daily Cost Today
   - Shows cost breakdown by component (NodeGroups, PostgreSQL EC2/EBS, Neo4j EC2/EBS, Network)

## Cost Data Fields

### Yesterday's Cost
- **Field**: `yesterday_cost`
- **Description**: Total cost for the previous day (in UTC)
- **Calculation**: Retrieved from the previous day's daily record
- **UI Display**: "Yesterday's Cost: $X.XX"
- **Behavior**: If yesterday's cost is not available, shows $0.00

### Daily Cost (Today)
- **Field**: `daily_cost`
- **Description**: Total cost for the current day
- **Calculation**: Calculated fresh on each cost tracker run
- **UI Display**: "Daily Cost Today: $X.XX"

### Projected Monthly Cost
- **Field**: `projected_monthly_cost`
- **Description**: Estimated monthly cost based on today's daily cost
- **Calculation**: `daily_cost × days_in_current_month`
- **UI Display**: "Projected Monthly Cost: $X.XX"

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
  "yesterday_cost": 11.80,
  "projected_monthly_cost": 375.00,
  "mtd_cost": 187.50,
  "breakdown": {
    "nodegroups": 10.00,
    "postgres_ec2": 1.44,
    "postgres_ebs": 5.39,
    "neo4j_ec2": 1.44,
    "neo4j_ebs": 0.59,
    "databases": 2.88,
    "ebs": 5.98,
    "network": 0.20
  },
  "month": "2024-01",
  "updated_at": "2024-01-15T00:30:00Z"
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


