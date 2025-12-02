#!/bin/bash
# Script to build and deploy UI to S3/CloudFront
# Reads configuration from config/config.yaml

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$PROJECT_ROOT/ui"
CONFIG_NAME="${CONFIG_NAME:-config.yaml}"
CONFIG_FILE="$PROJECT_ROOT/config/$CONFIG_NAME"

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

# Extract values from config file using Python (respects CONFIG_NAME env var)
export CONFIG_NAME
S3_BUCKET=$(python3 -c "
import os
import sys
import json
import subprocess

config_name = os.environ.get('CONFIG_NAME', 'config.yaml')
script_dir = os.path.dirname(os.path.abspath('$SCRIPT_DIR/load-config.py'))
project_root = os.path.dirname(script_dir)
load_config_script = os.path.join(project_root, 'scripts', 'load-config.py')

try:
    result = subprocess.run(
        ['python3', load_config_script],
        capture_output=True,
        text=True,
        env={**os.environ, 'CONFIG_NAME': config_name}
    )
    if result.returncode != 0:
        print(f'Error loading config: {result.stderr}', file=sys.stderr)
        sys.exit(1)
    config = json.loads(result.stdout)
    print(config.get('s3', {}).get('ui_bucket_name', ''))
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
")

API_URL="${API_URL:-$(python3 -c "
import os
import sys
import json
import subprocess

config_name = os.environ.get('CONFIG_NAME', 'config.yaml')
script_dir = os.path.dirname(os.path.abspath('$SCRIPT_DIR/load-config.py'))
project_root = os.path.dirname(script_dir)
load_config_script = os.path.join(project_root, 'scripts', 'load-config.py')

try:
    result = subprocess.run(
        ['python3', load_config_script],
        capture_output=True,
        text=True,
        env={**os.environ, 'CONFIG_NAME': config_name}
    )
    if result.returncode != 0:
        print(f'Error loading config: {result.stderr}', file=sys.stderr)
        sys.exit(1)
    config = json.loads(result.stdout)
    print(config.get('ui', {}).get('api_url', ''))
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
")}"

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

# Extract Cognito values from config
COGNITO_USER_POOL_ID=$(python3 -c "
import os
import sys
import json
import subprocess

config_name = os.environ.get('CONFIG_NAME', 'config.yaml')
script_dir = os.path.dirname(os.path.abspath('$SCRIPT_DIR/load-config.py'))
project_root = os.path.dirname(script_dir)
load_config_script = os.path.join(project_root, 'scripts', 'load-config.py')

try:
    result = subprocess.run(
        ['python3', load_config_script],
        capture_output=True,
        text=True,
        env={**os.environ, 'CONFIG_NAME': config_name}
    )
    if result.returncode != 0:
        print('', file=sys.stderr)
        sys.exit(0)
    config = json.loads(result.stdout)
    print(config.get('cognito', {}).get('user_pool_id', ''))
except Exception:
    print('')
")

COGNITO_CLIENT_ID=$(python3 -c "
import os
import sys
import json
import subprocess

config_name = os.environ.get('CONFIG_NAME', 'config.yaml')
script_dir = os.path.dirname(os.path.abspath('$SCRIPT_DIR/load-config.py'))
project_root = os.path.dirname(script_dir)
load_config_script = os.path.join(project_root, 'scripts', 'load-config.py')

try:
    result = subprocess.run(
        ['python3', load_config_script],
        capture_output=True,
        text=True,
        env={**os.environ, 'CONFIG_NAME': config_name}
    )
    if result.returncode != 0:
        print('', file=sys.stderr)
        sys.exit(0)
    config = json.loads(result.stdout)
    print(config.get('cognito', {}).get('client_id', ''))
except Exception:
    print('')
")

# Create .env file with API URL and Cognito config
ENV_CONTENT=""
if [ -n "$API_URL" ]; then
    ENV_CONTENT="VITE_API_URL=$API_URL"
fi

if [ -n "$COGNITO_USER_POOL_ID" ] && [ -n "$COGNITO_CLIENT_ID" ]; then
    if [ -n "$ENV_CONTENT" ]; then
        ENV_CONTENT="$ENV_CONTENT"$'\n'
    fi
    ENV_CONTENT="${ENV_CONTENT}VITE_COGNITO_USER_POOL_ID=$COGNITO_USER_POOL_ID"$'\n'"VITE_COGNITO_CLIENT_ID=$COGNITO_CLIENT_ID"
    echo -e "${GREEN}Cognito authentication enabled${NC}"
    echo -e "  User Pool ID: ${COGNITO_USER_POOL_ID:0:20}..."
    echo -e "  Client ID: ${COGNITO_CLIENT_ID:0:20}..."
else
    echo -e "${YELLOW}Warning: Cognito not configured - authentication will be disabled${NC}"
    echo "Set cognito.user_pool_id and cognito.client_id in config/$CONFIG_NAME to enable"
fi

echo "$ENV_CONTENT" > .env.production

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


