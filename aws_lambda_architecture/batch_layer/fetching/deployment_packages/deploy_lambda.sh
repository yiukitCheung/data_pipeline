#!/bin/bash
# Build and deploy Lambda functions to AWS

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FETCHING_DIR="$(dirname "$SCRIPT_DIR")"
BATCH_LAYER_DIR="$(dirname "$FETCHING_DIR")"
SHARED_DIR="$BATCH_LAYER_DIR/shared"

# AWS Configuration
AWS_REGION="${AWS_REGION:-ca-west-1}"
FUNCTION_PREFIX="${FUNCTION_PREFIX:-dev-batch-}"  # Customize this prefix

echo "🚀 Building and deploying Lambda functions..."
echo "Region: $AWS_REGION"

# Function to build and deploy a Lambda package
build_and_deploy_lambda() {
    local function_name=$1
    local file_name=$(echo "$function_name" | tr '-' '_')  # Convert dashes to underscores for file name
    local package_dir="$SCRIPT_DIR/package/$function_name"
    
    echo ""
    echo "=" "=" "=" "=" "=" "=" "=" "=" "=" "="
    echo "📦 Building $function_name..."
    echo "=" "=" "=" "=" "=" "=" "=" "=" "=" "="
    
    # Create package directory
    mkdir -p "$package_dir"
    
    # Install dependencies (for Linux x86_64 - Lambda runtime)
    echo "📥 Installing dependencies for Linux x86_64..."
    pip install -r "$FETCHING_DIR/requirements.txt" -t "$package_dir" \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --python-version 3.11 \
        --implementation cp \
        --no-cache-dir \
        --quiet 2>/dev/null || \
    pip install -r "$FETCHING_DIR/requirements.txt" -t "$package_dir" \
        --no-cache-dir \
        --quiet
    
    # Copy Lambda function
    echo "📄 Copying Lambda function code..."
    cp "$FETCHING_DIR/lambda_functions/${file_name}.py" "$package_dir/${file_name}.py"
    
    # Copy shared modules (only what Lambda needs)
    echo "📁 Copying shared modules..."
    mkdir -p "$package_dir/shared/clients"
    mkdir -p "$package_dir/shared/models"
    mkdir -p "$package_dir/shared/utils"
    
    # Copy only required clients (not redis, kinesis, aurora)
    cp "$SHARED_DIR/clients/polygon_client.py" "$package_dir/shared/clients/"
    cp "$SHARED_DIR/clients/rds_timescale_client.py" "$package_dir/shared/clients/"
    cp "$SHARED_DIR/clients/fmp_client.py" "$package_dir/shared/clients/"
    
    # Create minimal __init__.py for Lambda (only what we need)
    cat > "$package_dir/shared/clients/__init__.py" << 'EOF'
"""Client modules for Lambda functions"""
from .polygon_client import PolygonClient
from .rds_timescale_client import RDSTimescaleClient
from .fmp_client import FMPClient

__all__ = ['PolygonClient', 'RDSTimescaleClient', 'FMPClient']
EOF
    
    # Copy models and utils
    cp -r "$SHARED_DIR/models/"* "$package_dir/shared/models/" 2>/dev/null || true
    if [ -n "$(ls -A "$SHARED_DIR/utils/" 2>/dev/null)" ]; then
        cp -r "$SHARED_DIR/utils/"* "$package_dir/shared/utils/"
    fi
    cp "$SHARED_DIR/__init__.py" "$package_dir/shared/"
    
    # Remove cache files
    echo "🧹 Cleaning cache files..."
    find "$package_dir" -name "*.pyc" -delete
    find "$package_dir" -name "*.pyo" -delete
    find "$package_dir" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # Create ZIP file
    echo "📦 Creating deployment package..."
    cd "$package_dir"
    zip -r9 "$SCRIPT_DIR/$function_name.zip" . -x "*.pyc" "*/__pycache__/*"
    cd "$SCRIPT_DIR"
    
    # Check package size
    local size=$(du -h "$SCRIPT_DIR/$function_name.zip" | cut -f1)
    echo "✅ Created $function_name.zip ($size)"
    
    # Deploy to AWS
    echo "🚀 Deploying to AWS Lambda..."
    
    # Try with prefix first, then without
    local aws_function_name="${FUNCTION_PREFIX}${function_name}"
    
    if aws lambda get-function --function-name "$aws_function_name" --region "$AWS_REGION" &>/dev/null; then
        echo "📝 Updating function: $aws_function_name"
        result=$(aws lambda update-function-code \
            --function-name "$aws_function_name" \
            --zip-file "fileb://$SCRIPT_DIR/$function_name.zip" \
            --region "$AWS_REGION" \
            --output json)
        
        echo "✅ Updated successfully!"
        echo "   Last Modified: $(echo $result | jq -r '.LastModified')"
        echo "   Code Size: $(echo $result | jq -r '.CodeSize') bytes"
    elif aws lambda get-function --function-name "$function_name" --region "$AWS_REGION" &>/dev/null; then
        echo "📝 Updating function: $function_name"
        result=$(aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file "fileb://$SCRIPT_DIR/$function_name.zip" \
            --region "$AWS_REGION" \
            --output json)
        
        echo "✅ Updated successfully!"
        echo "   Last Modified: $(echo $result | jq -r '.LastModified')"
        echo "   Code Size: $(echo $result | jq -r '.CodeSize') bytes"
    else
        echo "❌ Function not found in AWS (tried: $aws_function_name and $function_name)"
        echo "💡 Create it first via AWS Console, then run this script again."
    fi
}

# Clean up previous builds
echo "🧹 Cleaning previous builds..."
rm -rf "$SCRIPT_DIR"/package/
mkdir -p "$SCRIPT_DIR"/package

# Build and deploy Lambda functions
build_and_deploy_lambda "daily-ohlcv-fetcher"
build_and_deploy_lambda "daily-meta-fetcher"

# Clean up package directory
rm -rf "$SCRIPT_DIR"/package/

echo ""
echo "=" "=" "=" "=" "=" "=" "=" "=" "=" "="
echo "🎉 Deployment complete!"
echo "=" "=" "=" "=" "=" "=" "=" "=" "=" "="
echo ""
echo "📊 Deployed packages:"
for zip_file in "$SCRIPT_DIR"/*.zip; do
    if [ -f "$zip_file" ]; then
        size=$(du -h "$zip_file" | cut -f1)
        echo "  $(basename "$zip_file"): $size"
    fi
done

echo ""
echo "💡 Tips:"
echo "  - View logs: aws logs tail /aws/lambda/daily_ohlcv_fetcher --follow"
echo "  - Test function: aws lambda invoke --function-name daily_ohlcv_fetcher response.json"

