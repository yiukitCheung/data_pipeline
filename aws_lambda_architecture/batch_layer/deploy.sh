#!/bin/bash
# Industrial Terraform Deployment Script for Batch Layer
# Supports both modular and component-based deployment

set -e

ENVIRONMENT=${1:-dev}
COMPONENT=${2:-all}

echo "🚀 Deploying Batch Layer - Environment: $ENVIRONMENT, Component: $COMPONENT"

# Function to deploy a specific component
deploy_component() {
    local component=$1
    echo "📦 Deploying $component component..."
    
    if [ -d "$component/terraform" ]; then
        cd "$component/terraform"
        terraform init
        terraform plan -var="environment=$ENVIRONMENT"
        terraform apply -var="environment=$ENVIRONMENT" -auto-approve
        cd ../..
    else
        echo "❌ Component $component terraform not found"
        exit 1
    fi
}

# Function to deploy all via main infrastructure
deploy_all() {
    echo "🏗️ Deploying entire batch layer..."
    cd infrastructure
    terraform init
    terraform plan -var="environment=$ENVIRONMENT"
    terraform apply -var="environment=$ENVIRONMENT" -auto-approve
    cd ..
}

# Function to build deployment artifacts first
build_artifacts() {
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
    
    # Build container images
    if [ -f "processing/container_images/build_container.sh" ]; then
        echo "🐳 Building container images..."
        cd processing/container_images
        ./build_container.sh
        cd ../..
    fi
}

# Function to validate prerequisites
validate_prerequisites() {
    echo "🔍 Validating prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo "❌ AWS CLI not found. Please install AWS CLI."
        exit 1
    fi
    
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
        cd infrastructure
        echo ""
        echo "📊 Infrastructure Outputs:"
        terraform output
        cd ..
    fi
}

# Main deployment logic
case $COMPONENT in
    "all")
        validate_prerequisites
        build_artifacts
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
        read -p "Are you sure you want to destroy $ENVIRONMENT environment? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            cd infrastructure
            terraform destroy -var="environment=$ENVIRONMENT" -auto-approve
            cd ..
        else
            echo "Aborted."
        fi
        ;;
    *)
        echo "❌ Invalid component: $COMPONENT"
        echo ""
        echo "Usage: $0 [environment] [component]"
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
        echo "  $0 dev all                    # Deploy everything to dev"
        echo "  $0 prod fetching             # Deploy only fetching to prod"
        echo "  $0 dev build                 # Build artifacts only"
        exit 1
        ;;
esac

echo "✅ Deployment completed successfully!"
