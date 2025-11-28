#!/bin/bash
set -e

echo "Building Lambda packages with dependencies..."
echo ""

mkdir -p build

# Function to build a Lambda package
build_lambda() {
    local lambda_name=$1
    local lambda_dir="lambdas/$lambda_name"
    local build_dir="build/$lambda_name-package"
    local zip_file="build/$lambda_name.zip"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Building: $lambda_name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Clean previous build
    rm -rf "$build_dir" "$zip_file"
    mkdir -p "$build_dir"
    
    # Install dependencies
    if [ -f "$lambda_dir/requirements.txt" ]; then
        echo "Installing dependencies..."
        pip3 install -q -t "$build_dir" -r "$lambda_dir/requirements.txt"
    fi
    
    # Copy Lambda code
    echo "Copying Lambda code..."
    cp "$lambda_dir/lambda_function.py" "$build_dir/"
    
    # Copy config directory if it exists (for config loader)
    if [ -d "$lambda_dir/config" ]; then
        echo "Copying config module..."
        cp -r "$lambda_dir/config" "$build_dir/"
    fi
    
    # Copy config.yaml to Lambda package (for Lambda runtime)
    if [ -f "config/config.yaml" ]; then
        echo "Copying config.yaml..."
        mkdir -p "$build_dir/config"
        cp "config/config.yaml" "$build_dir/config/"
    fi
    
    # Create ZIP
    echo "Creating ZIP package..."
    cd "$build_dir"
    zip -q -r "../$lambda_name.zip" .
    cd - > /dev/null
    
    # Cleanup
    rm -rf "$build_dir"
    
    echo "✅ Built: $zip_file"
    echo ""
}

# Build all Lambda functions
build_lambda "discovery"
build_lambda "controller"
build_lambda "health-monitor"
build_lambda "api-handler"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ALL LAMBDA PACKAGES BUILT!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ls -lh build/*.zip


