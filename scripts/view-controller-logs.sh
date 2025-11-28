#!/bin/bash
# View Controller Lambda logs

LOG_GROUP="/aws/lambda/eks-app-controller-controller"
REGION="us-east-1"

echo "📋 Controller Lambda Logs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Options:"
echo "  1. Follow logs in real-time (Ctrl+C to exit)"
echo "  2. View last 30 minutes"
echo "  3. View last hour"
echo "  4. Search for specific app"
echo ""
read -p "Select option (1-4): " option

case $option in
  1)
    echo "Following logs (Ctrl+C to exit)..."
    aws logs tail "$LOG_GROUP" --follow --region "$REGION"
    ;;
  2)
    echo "Last 30 minutes:"
    aws logs tail "$LOG_GROUP" --since 30m --region "$REGION" --no-cli-pager | tail -100
    ;;
  3)
    echo "Last hour:"
    aws logs tail "$LOG_GROUP" --since 1h --region "$REGION" --no-cli-pager | tail -200
    ;;
  4)
    read -p "Enter app name to search: " app_name
    echo "Searching for: $app_name"
    aws logs filter-log-events \
      --log-group-name "$LOG_GROUP" \
      --filter-pattern "$app_name" \
      --region "$REGION" \
      --no-cli-pager | jq -r '.events[] | "\(.timestamp | tonumber / 1000 | strftime("%Y-%m-%d %H:%M:%S")) | \(.message)"'
    ;;
  *)
    echo "Invalid option"
    exit 1
    ;;
esac

