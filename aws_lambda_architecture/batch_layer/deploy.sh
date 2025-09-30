#!/bin/bash
# Batch Layer Deployment Script
# Usage: ./deploy.sh [environment] [component]

set -e

# Default values
ENVIRONMENT=${1:-dev}
COMPONENT=${2:-all}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to deploy entire batch layer
deploy_all() {
    echo "🏗️ Deploying entire batch layer..."
    
    # First, deploy infrastructure (creates ECR repository)
    echo "🏗️ Deploying infrastructure..."
    cd infrastructure
    terraform init
    terraform plan -var="environment=$ENVIRONMENT"
    terraform apply -var="environment=$ENVIRONMENT" -auto-approve
    cd ..
    
    # Then, build and push container (now that ECR exists)
    echo "🐳 Building and pushing container..."
    if [ -f "processing/container_images/build_container.sh" ]; then
        cd processing/container_images
        ./build_container.sh
        cd ../..
    fi
}

# Function to build deployment artifacts first
build_artifacts() {
    local skip_ecr_push=${1:-false}
    
    echo "📦 Building deployment artifacts..."
    
    # Build Lambda Layer first (contains heavy dependencies)
    if [ -f "fetching/deployment_packages/build_layer.sh" ]; then
        echo "🔧 Building Lambda Layer..."
        cd fetching/deployment_packages
        ./build_layer.sh --publish
        cd ../..
    fi
    
    # Build Lambda packages (now lightweight without heavy deps)
    if [ -f "fetching/deployment_packages/build_packages.sh" ]; then
        echo "🔧 Building Lambda packages..."
        cd fetching/deployment_packages
        ./build_packages.sh
        cd ../..
    fi
    
    # Build container images (but only push to ECR if not skipping)
    if [ -f "processing/container_images/build_container.sh" ]; then
        echo "🐳 Building container images..."
        cd processing/container_images
        if [ "$skip_ecr_push" = "true" ]; then
            # Build only, don't push to ECR
            echo "🔧 Building container (skipping ECR push)..."
            docker build \
                -f "$(pwd)/Dockerfile" \
                -t "dev-batch-fibonacci-resampler:latest" \
                --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
                --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
                "$(dirname "$(pwd)")/.."
        else
            # Build and push to ECR
            ./build_container.sh
        fi
        cd ../..
    fi
}

# Function to deploy specific component
deploy_component() {
    local component=$1
    echo "🚀 Deploying $component component..."
    
    cd infrastructure
    terraform init
    terraform plan -var="environment=$ENVIRONMENT" -target="module.$component"
    terraform apply -var="environment=$ENVIRONMENT" -target="module.$component" -auto-approve
    cd ..
}

# Function to validate prerequisites
validate_prerequisites() {
    echo "🔍 Validating prerequisites..."
    
    # Check Terraform
    if ! command -v terraform &> /dev/null; then
        echo "❌ Terraform not found. Please install Terraform."
        exit 1
    fi
    
    # Check Docker (for container builds)
    if [ "$COMPONENT" = "processing" ] || [ "$COMPONENT" = "all" ]; then
        if ! command -v docker &> /dev/null; then
            echo "❌ Docker not found. Please install Docker."
            exit 1
        fi
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo "❌ AWS credentials not configured. Please run 'aws configure'."
        exit 1
    fi
    
    echo "✅ Prerequisites validated!"
}

# Function to show deployment summary
show_summary() {
    echo ""
    echo "🎉 Deployment Summary:"
    echo "===================="
    echo "Environment: $ENVIRONMENT"
    echo "Component: $COMPONENT"
    echo "Timestamp: $(date)"
    
    if [ "$COMPONENT" = "all" ]; then
        echo ""
        echo "📋 Deployed Components:"
        echo "  ✅ Infrastructure (RDS, ECR, Lambda, Batch, EventBridge)"
        echo "  ✅ Fetching (Lambda functions with layers)"
        echo "  ✅ Processing (Container image in ECR)"
        echo "  ✅ Database (PostgreSQL with schema)"
        echo ""
        echo "🔗 Next Steps:"
        echo "  1. Test Lambda functions in AWS Console"
        echo "  2. Check container in ECR repository"
        echo "  3. Verify database connection"
        echo "  4. Monitor EventBridge schedules"
    else
        echo ""
        echo "📋 Deployed Component: $COMPONENT"
        echo ""
        echo "🔗 Next Steps:"
        echo "  1. Check component in AWS Console"
        echo "  2. Test functionality"
        echo "  3. Monitor logs"
    fi
}

# Main execution
echo "🚀 Deploying Batch Layer - Environment: $ENVIRONMENT, Component: $COMPONENT"

case $COMPONENT in
    "all")
        validate_prerequisites
        build_artifacts true  # Skip ECR push during build
        deploy_all
        show_summary
        ;;
    "fetching"|"processing"|"database")
        validate_prerequisites
        if [ "$COMPONENT" = "fetching" ]; then
            # Build Lambda packages for fetching
            if [ -f "fetching/deployment_packages/build_packages.sh" ]; then
                cd fetching/deployment_packages
                ./build_packages.sh
                cd ../..
            fi
        elif [ "$COMPONENT" = "processing" ]; then
            # Build container for processing
            if [ -f "processing/container_images/build_container.sh" ]; then
                cd processing/container_images
                ./build_container.sh
                cd ../..
            fi
        fi
        deploy_component $COMPONENT
        show_summary
        ;;
    "build")
        validate_prerequisites
        build_artifacts
        ;;
    "layer")
        echo "🔧 Building and publishing Lambda Layer..."
        validate_prerequisites
        if [ -f "fetching/deployment_packages/build_layer.sh" ]; then
            cd fetching/deployment_packages
            ./build_layer.sh --publish
            cd ../..
        fi
        ;;
    "init")
        echo "🔧 Initializing infrastructure..."
        cd infrastructure
        terraform init
        cd ..
        ;;
    "plan")
        echo "📋 Planning infrastructure..."
        cd infrastructure
        terraform plan -var="environment=$ENVIRONMENT"
        cd ..
        ;;
    "destroy")
        echo "💥 Destroying infrastructure..."
        read -p "Are you sure you want to destroy all resources? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            cd infrastructure
            terraform destroy -var="environment=$ENVIRONMENT" -auto-approve
            cd ..
        else
            echo "❌ Destruction cancelled."
        fi
        ;;
    *)
        echo "❌ Invalid component: $COMPONENT"
        echo ""
        echo "Usage: ./deploy.sh [environment] [component]"
        echo ""
        echo "Environments: dev, staging, prod"
        echo "Components:"
        echo "  all        - Deploy entire batch layer (default)"
        echo "  fetching   - Deploy only fetching component"
        echo "  processing - Deploy only processing component"
        echo "  database   - Deploy only database component"
        echo "  build      - Build artifacts only"
        echo "  layer      - Build and publish Lambda Layer only"
        echo "  init       - Initialize Terraform"
        echo "  plan       - Plan infrastructure"
        echo "  destroy    - Destroy infrastructure"
        echo ""
        echo "Examples:"
        echo "  ./deploy.sh dev all                    # Deploy everything to dev"
        echo "  ./deploy.sh prod fetching             # Deploy only fetching to prod"
        echo "  ./deploy.sh dev build                 # Build artifacts only"
        exit 1
        ;;
esac

echo "✅ Deployment completed successfully!"