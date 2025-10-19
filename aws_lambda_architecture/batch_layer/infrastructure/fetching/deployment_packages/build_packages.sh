#!/bin/bash
# Build Lambda deployment packages for fetching component

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Point to batch_layer/fetching (application code) not infrastructure/fetching
BATCH_LAYER_DIR="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
FETCHING_DIR="$BATCH_LAYER_DIR/fetching"
SHARED_DIR="$(dirname "$BATCH_LAYER_DIR")/shared"

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
    
    # Install dependencies with optimizations
    echo "📥 Installing dependencies..."
    pip install -r "$FETCHING_DIR/requirements.txt" -t "$package_dir" \
        --no-cache-dir \
        --compile \
        --no-deps \
        || pip install -r "$FETCHING_DIR/requirements.txt" -t "$package_dir" --no-cache-dir
    
    # Copy Lambda function
    cp "$FETCHING_DIR/lambda_functions/$function_name.py" "$package_dir/"
    
    # Copy only essential shared modules
    mkdir -p "$package_dir/shared"
    cp -r "$SHARED_DIR/clients" "$package_dir/shared/"
    cp -r "$SHARED_DIR/models" "$package_dir/shared/"
    cp -r "$SHARED_DIR/utils" "$package_dir/shared/"
    cp "$SHARED_DIR/__init__.py" "$package_dir/shared/"
    
    # Remove unnecessary files to reduce size
    echo "🧹 Optimizing package size..."
    find "$package_dir" -name "*.pyc" -delete
    find "$package_dir" -name "*.pyo" -delete
    find "$package_dir" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$package_dir" -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$package_dir" -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$package_dir" -name "test" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$package_dir" -name "*.so" -exec strip {} + 2>/dev/null || true
    
    # Create ZIP file with compression
    cd "$package_dir"
    zip -r9 "$SCRIPT_DIR/$function_name.zip" . -x "*.pyc" "*/__pycache__/*" "*/tests/*" "*/test/*"
    cd "$SCRIPT_DIR"
    
    # Check package size
    local size=$(du -h "$SCRIPT_DIR/$function_name.zip" | cut -f1)
    echo "✅ Created $function_name.zip ($size)"
    
    # Warn if approaching limit
    local size_bytes=$(stat -f%z "$SCRIPT_DIR/$function_name.zip" 2>/dev/null || stat -c%s "$SCRIPT_DIR/$function_name.zip")
    if [ "$size_bytes" -gt 52428800 ]; then  # 50MB warning
        echo "⚠️  Warning: Package size is ${size}, approaching 70MB Lambda limit"
    fi
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
