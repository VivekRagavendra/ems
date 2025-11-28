#!/bin/bash
# View logs for all Lambda functions

REGION="us-east-1"

echo "📋 EKS Application Controller - Lambda Logs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Select Lambda function:"
echo "  1. Controller (Start/Stop operations)"
echo "  2. Discovery (Application discovery)"
echo "  3. Health Monitor (Health checks)"
echo "  4. API Handler (API requests)"
echo ""
read -p "Select (1-4): " choice

case $choice in
  1) LOG_GROUP="/aws/lambda/eks-app-controller-controller" ;;
  2) LOG_GROUP="/aws/lambda/eks-app-controller-discovery" ;;
  3) LOG_GROUP="/aws/lambda/eks-app-controller-health-monitor" ;;
  4) LOG_GROUP="/aws/lambda/eks-app-controller-api-handler" ;;
  *)
    echo "Invalid option"
    exit 1
    ;;
esac

echo ""
echo "Viewing logs for: $LOG_GROUP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
aws logs tail "$LOG_GROUP" --since 30m --region "$REGION" --no-cli-pager | tail -100

