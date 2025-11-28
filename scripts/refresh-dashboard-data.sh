#!/bin/bash
# Manually refresh dashboard data by triggering Discovery and Health Monitor

echo "🔄 Refreshing dashboard data..."
echo ""

echo "1. Triggering Discovery Lambda..."
aws lambda invoke \
  --function-name eks-app-controller-discovery \
  --region us-east-1 \
  --payload '{}' \
  /tmp/discovery-response.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
  echo "   ✅ Discovery Lambda triggered"
else
  echo "   ⚠️  Discovery Lambda failed (check logs)"
fi

echo ""
echo "2. Waiting 10 seconds for discovery to complete..."
sleep 10

echo ""
echo "3. Triggering Health Monitor Lambda..."
aws lambda invoke \
  --function-name eks-app-controller-health-monitor \
  --region us-east-1 \
  --payload '{}' \
  /tmp/health-response.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
  echo "   ✅ Health Monitor Lambda triggered"
else
  echo "   ⚠️  Health Monitor Lambda failed (check logs)"
fi

echo ""
echo "4. Waiting 15 seconds for health checks to complete..."
sleep 15

echo ""
echo "✅ Data refresh complete!"
echo ""
echo "📊 Check dashboard: http://eks-app-controller-ui-420464349284.s3-website-us-east-1.amazonaws.com"
echo "   (Refresh your browser to see updated data)"
