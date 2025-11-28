#!/bin/bash
# Script to package and deploy Lambda functions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAMBDAS_DIR="$PROJECT_ROOT/lambdas"
BUILD_DIR="$PROJECT_ROOT/build"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Building Lambda deployment packages...${NC}"

# Create build directory
mkdir -p "$BUILD_DIR"

# Function to package a Lambda
package_lambda() {
    local lambda_name=$1
    local lambda_dir="$LAMBDAS_DIR/$lambda_name"
    local zip_file="$BUILD_DIR/${lambda_name}.zip"
    
    if [ ! -d "$lambda_dir" ]; then
        echo -e "${RED}Error: Lambda directory not found: $lambda_dir${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}Packaging $lambda_name...${NC}"
    
    # Create temporary directory
    local temp_dir=$(mktemp -d)
    
    # Copy Lambda function code
    cp "$lambda_dir/lambda_function.py" "$temp_dir/"
    
    # Copy config directory if it exists (for config loader)
    if [ -d "$lambda_dir/config" ]; then
        cp -r "$lambda_dir/config" "$temp_dir/"
    fi
    
    # Copy config.yaml to Lambda package root (for Lambda runtime)
    if [ -f "$PROJECT_ROOT/config/config.yaml" ]; then
        mkdir -p "$temp_dir/config"
        cp "$PROJECT_ROOT/config/config.yaml" "$temp_dir/config/"
    fi
    
    # Install dependencies if requirements.txt exists
    if [ -f "$lambda_dir/requirements.txt" ]; then
        echo "Installing dependencies for $lambda_name..."
        pip install -r "$lambda_dir/requirements.txt" -t "$temp_dir" --quiet
    fi
    
    # Create zip file
    cd "$temp_dir"
    zip -r "$zip_file" . -q
    cd - > /dev/null
    
    # Cleanup
    rm -rf "$temp_dir"
    
    echo -e "${GREEN}✓ Created $zip_file${NC}"
}

# Package all Lambda functions
for lambda_dir in "$LAMBDAS_DIR"/*; do
    if [ -d "$lambda_dir" ] && [ -f "$lambda_dir/lambda_function.py" ]; then
        lambda_name=$(basename "$lambda_dir")
        package_lambda "$lambda_name"
    fi
done

echo -e "${GREEN}All Lambda packages created in $BUILD_DIR${NC}"
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Update Terraform lambdas.tf to use these zip files"
echo "2. Run: terraform apply"


