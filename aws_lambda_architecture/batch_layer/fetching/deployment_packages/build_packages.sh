#!/bin/bash
# Build Lambda deployment packages for fetching component

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FETCHING_DIR="$(dirname "$SCRIPT_DIR")"
SHARED_DIR="$(dirname "$(dirname "$FETCHING_DIR")")/shared"

echo "🔧 Building Lambda deployment packages for fetching component..."

# Clean up previous builds
rm -rf "$SCRIPT_DIR"/*.zip
rm -rf "$SCRIPT_DIR"/package/

# Create package directory
mkdir -p "$SCRIPT_DIR"/package

# Function to build a Lambda package
build_lambda_package() {
    local function_name=$1
    local package_dir="$SCRIPT_DIR/package/$function_name"
    
    echo "📦 Building $function_name package..."
    
    # Create package directory
    mkdir -p "$package_dir"
    
    # Install dependencies
    pip install -r "$FETCHING_DIR/requirements.txt" -t "$package_dir"
    
    # Copy Lambda function
    cp "$FETCHING_DIR/lambda_functions/$function_name.py" "$package_dir/"
    
    # Copy shared modules
    cp -r "$SHARED_DIR"/* "$package_dir/"
    
    # Create ZIP file
    cd "$package_dir"
    zip -r "../../../$function_name.zip" .
    cd "$SCRIPT_DIR"
    
    echo "✅ Created $function_name.zip"
}

# Build Lambda packages
build_lambda_package "daily_ohlcv_fetcher"
build_lambda_package "daily_meta_fetcher"

# Clean up package directory
rm -rf "$SCRIPT_DIR"/package/

echo "🎉 All Lambda packages built successfully!"
echo "📁 Packages available in: $SCRIPT_DIR"

# Show package sizes
echo "📊 Package sizes:"
for zip_file in "$SCRIPT_DIR"/*.zip; do
    if [ -f "$zip_file" ]; then
        size=$(du -h "$zip_file" | cut -f1)
        echo "  $(basename "$zip_file"): $size"
    fi
done
