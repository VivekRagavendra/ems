#!/bin/bash
# Script to build and deploy UI to S3/CloudFront
# Reads configuration from config/config.yaml

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$PROJECT_ROOT/ui"
CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load config from config.yaml
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Error: config/config.yaml not found${NC}"
    echo "Please create config/config.yaml from config/config.example.yaml"
    exit 1
fi

# Extract values from config.yaml using Python
S3_BUCKET=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['s3']['ui_bucket_name'])")
API_URL="${API_URL:-$(python3 -c "import yaml; cfg=yaml.safe_load(open('$CONFIG_FILE')); print(cfg.get('ui', {}).get('api_url', ''))")}"

# Allow override via environment variables
S3_BUCKET="${S3_BUCKET_OVERRIDE:-$S3_BUCKET}"

if [ -z "$S3_BUCKET" ]; then
    echo -e "${RED}Error: S3 bucket name not found in config/config.yaml${NC}"
    echo "Please set s3.ui_bucket_name in config/config.yaml"
    exit 1
fi

if [ -z "$API_URL" ]; then
    echo -e "${YELLOW}Warning: API URL not set in config/config.yaml${NC}"
    echo "Please set ui.api_url in config/config.yaml or provide API_URL environment variable"
    echo "You can get the API URL from API Gateway after deployment"
    read -p "Enter API Gateway URL (or press Enter to skip): " API_URL
    if [ -z "$API_URL" ]; then
        echo -e "${YELLOW}Continuing without API URL - you can set it later${NC}"
    fi
fi

echo -e "${GREEN}Building UI...${NC}"
echo -e "  S3 Bucket: ${S3_BUCKET}"
echo -e "  API URL: ${API_URL:-'(not set)'}"

cd "$UI_DIR"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing npm dependencies..."
    npm install
fi

# Create .env file with API URL
if [ -n "$API_URL" ]; then
    echo "VITE_API_URL=$API_URL" > .env.production
else
    echo "# API URL not set - update config/config.yaml" > .env.production
fi

# Generate config.json for UI (if API URL is available)
if [ -n "$API_URL" ]; then
    echo "{\"apiUrl\": \"$API_URL\"}" > "$UI_DIR/public/config.json"
fi

# Build the UI
echo "Building React app..."
npm run build

# Deploy to S3
echo -e "${GREEN}Deploying to S3 bucket: $S3_BUCKET${NC}"
aws s3 sync dist/ s3://$S3_BUCKET/ --delete

echo -e "${GREEN}✓ UI deployed successfully${NC}"
echo -e "${YELLOW}Note: If using CloudFront, invalidate the cache:${NC}"
echo "aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths '/*'"


