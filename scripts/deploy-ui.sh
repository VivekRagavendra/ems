#!/bin/bash
# Script to build and deploy UI to S3/CloudFront

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$PROJECT_ROOT/ui"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if S3 bucket and API URL are provided
if [ -z "$S3_BUCKET" ]; then
    echo -e "${RED}Error: S3_BUCKET environment variable not set${NC}"
    echo "Usage: S3_BUCKET=your-bucket-name API_URL=your-api-url ./scripts/deploy-ui.sh"
    exit 1
fi

if [ -z "$API_URL" ]; then
    echo -e "${RED}Error: API_URL environment variable not set${NC}"
    echo "Usage: S3_BUCKET=your-bucket-name API_URL=your-api-url ./scripts/deploy-ui.sh"
    exit 1
fi

echo -e "${GREEN}Building UI...${NC}"

cd "$UI_DIR"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing npm dependencies..."
    npm install
fi

# Create .env file with API URL
echo "VITE_API_URL=$API_URL" > .env.production

# Build the UI
echo "Building React app..."
npm run build

# Deploy to S3
echo -e "${GREEN}Deploying to S3 bucket: $S3_BUCKET${NC}"
aws s3 sync dist/ s3://$S3_BUCKET/ --delete

echo -e "${GREEN}✓ UI deployed successfully${NC}"
echo -e "${YELLOW}Note: If using CloudFront, invalidate the cache:${NC}"
echo "aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths '/*'"


