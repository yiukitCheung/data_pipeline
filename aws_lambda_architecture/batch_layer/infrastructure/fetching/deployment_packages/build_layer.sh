#!/bin/bash
# Build Lambda Layer for heavy dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAYER_NAME="condvest-batch-dependencies"
AWS_REGION=${AWS_REGION:-ca-west-1}

echo "🔧 Building Lambda Layer: $LAYER_NAME"

# Clean up previous builds
rm -rf "$SCRIPT_DIR"/layer/
rm -rf "$SCRIPT_DIR"/*-layer.zip

# Create layer directory structure
mkdir -p "$SCRIPT_DIR"/layer/python

# Install dependencies for the layer
echo "📥 Installing layer dependencies..."
pip install -r "$SCRIPT_DIR/layer_requirements.txt" -t "$SCRIPT_DIR/layer/python" \
    --no-cache-dir

# Remove unnecessary files to reduce size
echo "🧹 Optimizing layer size..."
find "$SCRIPT_DIR/layer/python" -name "*.pyc" -delete
find "$SCRIPT_DIR/layer/python" -name "*.pyo" -delete
find "$SCRIPT_DIR/layer/python" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR/layer/python" -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR/layer/python" -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR/layer/python" -name "test" -type d -exec rm -rf {} + 2>/dev/null || true

# Remove large unnecessary files
find "$SCRIPT_DIR/layer/python" -name "*.so" -exec strip {} + 2>/dev/null || true
find "$SCRIPT_DIR/layer/python" -name "*.txt" -path "*/site-packages/*" -delete 2>/dev/null || true

# Create layer ZIP
echo "📦 Creating layer package..."
cd "$SCRIPT_DIR/layer"
zip -r9 "../${LAYER_NAME}.zip" . -x "*.pyc" "*/__pycache__/*" "*/tests/*" "*/test/*"
cd "$SCRIPT_DIR"

# Check layer size
layer_size=$(du -h "$SCRIPT_DIR/${LAYER_NAME}.zip" | cut -f1)
layer_size_bytes=$(stat -f%z "$SCRIPT_DIR/${LAYER_NAME}.zip" 2>/dev/null || stat -c%s "$SCRIPT_DIR/${LAYER_NAME}.zip")

echo "✅ Created ${LAYER_NAME}.zip ($layer_size)"

# Check if layer is within AWS limits (250MB unzipped, ~50MB zipped typically)
if [ "$layer_size_bytes" -gt 52428800 ]; then  # 50MB warning
    echo "⚠️  Warning: Layer size is ${layer_size}, may be approaching AWS limits"
fi

# Option to publish layer
if [ "$1" = "--publish" ]; then
    echo "🚀 Publishing Lambda Layer to AWS..."
    
    layer_version=$(aws lambda publish-layer-version \
        --layer-name "$LAYER_NAME" \
        --description "CondVest batch layer dependencies (pandas, yfinance, polygon)" \
        --zip-file "fileb://${SCRIPT_DIR}/${LAYER_NAME}.zip" \
        --compatible-runtimes python3.11 python3.10 python3.9 \
        --region "$AWS_REGION" \
        --query 'Version' \
        --output text)
    
    layer_arn="arn:aws:lambda:${AWS_REGION}:$(aws sts get-caller-identity --query Account --output text):layer:${LAYER_NAME}:${layer_version}"
    
    echo "✅ Published layer version: $layer_version"
    echo "📍 Layer ARN: $layer_arn"
    echo ""
    echo "🔧 Add this to your Terraform:"
    echo "layers = [\"$layer_arn\"]"
else
    echo ""
    echo "💡 To publish the layer, run:"
    echo "   $0 --publish"
    echo ""
    echo "🔧 Or publish manually with:"
    echo "   aws lambda publish-layer-version \\"
    echo "     --layer-name $LAYER_NAME \\"
    echo "     --zip-file fileb://$SCRIPT_DIR/${LAYER_NAME}.zip \\"
    echo "     --compatible-runtimes python3.11"
fi

# Clean up
rm -rf "$SCRIPT_DIR"/layer/

echo "🎉 Lambda layer build completed!"
