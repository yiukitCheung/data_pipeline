#!/bin/bash
# Build and push Docker container for processing component

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROCESSING_DIR="$(dirname "$SCRIPT_DIR")"
BATCH_DIR="$(dirname "$PROCESSING_DIR")"
SHARED_DIR="$BATCH_DIR/shared"  # Fixed: shared is now in batch_layer/shared

# Default values
AWS_REGION=${AWS_REGION:-ca-west-1}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}
ECR_REPOSITORY=${ECR_REPOSITORY:-dev-batch-fibonacci-resampler}
IMAGE_TAG=${IMAGE_TAG:-latest}

echo "🔧 Building Docker container for processing component..."
echo "📍 Region: $AWS_REGION"
echo "🏗️ Repository: $ECR_REPOSITORY"
echo "🏷️ Tag: $IMAGE_TAG"

# Get ECR login token
echo "🔐 Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# Copy shared files to processing directory for Docker build
echo "📁 Copying shared modules..."
rm -rf "$PROCESSING_DIR/shared"
cp -r "$SHARED_DIR" "$PROCESSING_DIR/"

# Build Docker image
echo "🐳 Building Docker image..."
cd "$BATCH_DIR"
docker build \
    -f "$PROCESSING_DIR/container_images/Dockerfile" \
    -t "$ECR_REPOSITORY:$IMAGE_TAG" \
    --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
    .

# Tag for ECR
echo "🏷️ Tagging image for ECR..."
docker tag "$ECR_REPOSITORY:$IMAGE_TAG" "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"

# Push to ECR
echo "⬆️ Pushing to ECR..."
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"

# Clean up copied shared files
echo "🧹 Cleaning up..."
rm -rf "$PROCESSING_DIR/shared"

echo "✅ Docker container built and pushed successfully!"
echo "📍 Image URI: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"

# Show image details
echo "📊 Image details:"
docker images "$ECR_REPOSITORY:$IMAGE_TAG" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"