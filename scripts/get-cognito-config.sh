#!/bin/bash
# Script to get Cognito configuration values and update config file

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_NAME="${CONFIG_NAME:-config.demo.yaml}"
CONFIG_FILE="$PROJECT_ROOT/config/$CONFIG_NAME"

echo "🔍 Getting Cognito configuration values..."

# Get User Pool ID
POOL_ID=$(aws cognito-idp list-user-pools --max-results 20 --region us-east-1 --query 'UserPools[?contains(Name, `eks-app-controller`)].Id' --output text 2>&1 | head -1)

if [ -z "$POOL_ID" ] || [[ "$POOL_ID" == *"error"* ]]; then
    echo "❌ Error: Could not find Cognito User Pool"
    echo "Make sure Cognito is deployed and AWS credentials are valid"
    exit 1
fi

echo "✅ Found User Pool ID: $POOL_ID"

# Get Client ID
CLIENT_ID=$(aws cognito-idp list-user-pool-clients --user-pool-id "$POOL_ID" --region us-east-1 --query 'UserPoolClients[?contains(ClientName, `web`)].ClientId' --output text 2>&1 | head -1)

if [ -z "$CLIENT_ID" ] || [[ "$CLIENT_ID" == *"error"* ]]; then
    echo "❌ Error: Could not find Cognito Client"
    exit 1
fi

echo "✅ Found Client ID: $CLIENT_ID"

# Get Domain
DOMAIN=$(aws cognito-idp describe-user-pool-domain --domain "${POOL_ID:0:20}" --region us-east-1 --query 'DomainDescription.Domain' --output text 2>&1 2>/dev/null || \
         aws cognito-idp list-user-pool-domains --user-pool-id "$POOL_ID" --region us-east-1 --query 'Domains[0].Domain' --output text 2>&1 | head -1)

if [ -z "$DOMAIN" ] || [[ "$DOMAIN" == *"error"* ]] || [[ "$DOMAIN" == "None" ]]; then
    # Try to get from user pool name
    POOL_NAME=$(aws cognito-idp describe-user-pool --user-pool-id "$POOL_ID" --region us-east-1 --query 'UserPool.Name' --output text 2>&1)
    DOMAIN="${POOL_NAME}-auth-$(aws sts get-caller-identity --query Account --output text | tail -c 5)"
    echo "⚠️  Could not find domain, using pattern: $DOMAIN"
else
    echo "✅ Found Domain: $DOMAIN"
fi

# Update config file
echo ""
echo "📝 Updating $CONFIG_FILE..."

python3 << PYTHON_SCRIPT
import yaml
import sys

config_file = "$CONFIG_FILE"

try:
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f) or {}
    
    if 'cognito' not in config:
        config['cognito'] = {}
    
    config['cognito']['user_pool_id'] = "$POOL_ID"
    config['cognito']['client_id'] = "$CLIENT_ID"
    config['cognito']['domain'] = "$DOMAIN"
    
    with open(config_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print("✅ Config file updated successfully!")
    print(f"   User Pool ID: $POOL_ID")
    print(f"   Client ID: $CLIENT_ID")
    print(f"   Domain: $DOMAIN")
    
except Exception as e:
    print(f"❌ Error updating config: {e}")
    sys.exit(1)
PYTHON_SCRIPT

echo ""
echo "✅ Cognito configuration updated!"
echo ""
echo "Next steps:"
echo "  1. Update Cognito callback URLs with your S3 bucket URL"
echo "  2. Run: bash scripts/deploy-ui.sh"
echo "  3. Create a test user in Cognito"
