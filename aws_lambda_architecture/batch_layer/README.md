# Batch Layer - Modular Architecture

## 🏗️ **Architecture Overview**

The batch layer is now structured using a **hybrid modular approach** for industrial-grade deployment and testing:

```
batch_layer/
├── infrastructure/              # 🎯 Main Terraform (Production)
│   ├── main.tf                 # Orchestrates all modules
│   ├── variables.tf
│   ├── terraform.tfvars
│   └── modules/                # Terraform modules
│       ├── fetching/
│       ├── processing/
│       ├── database/
│       └── shared/
├── fetching/                   # 📥 Data Fetching Component
│   ├── lambda_functions/
│   ├── deployment_packages/
│   ├── terraform/              # For testing only
│   └── requirements.txt
├── processing/                 # ⚙️ Data Processing Component
│   ├── batch_jobs/
│   ├── container_images/
│   ├── terraform/              # For testing only
│   └── requirements.txt
├── database/                   # 🗄️ Database Component
│   ├── schemas/
│   ├── terraform/              # For testing only
│   └── migrations/
├── shared/                     # 🔄 Shared Resources
│   ├── clients/
│   ├── models/
│   └── utils/
└── deploy.sh                   # 🚀 Main deployment script
```

## 🚀 **Quick Start**

### **⚡ Lambda Layers (Required First Step)**
```bash
# Build and publish Lambda Layer with heavy dependencies (pandas, yfinance)
./deploy.sh dev layer
```

### **Production Deployment (Single Command)**
```bash
# Deploy entire batch layer
./deploy.sh dev all

# Deploy to production
./deploy.sh prod all
```

### **Component Development & Testing**
```bash
# Test only the fetching component
./deploy.sh dev fetching

# Test only the processing component  
./deploy.sh dev processing

# Build artifacts without deploying
./deploy.sh dev build
```

## 📋 **Deployment Commands**

### **Main Commands**
```bash
./deploy.sh [environment] [component]
```

| Command | Description |
|---------|-------------|
| `./deploy.sh dev layer` | **Build and publish Lambda Layer (required first)** |
| `./deploy.sh dev all` | Deploy entire batch layer to dev |
| `./deploy.sh prod all` | Deploy entire batch layer to production |
| `./deploy.sh dev fetching` | Deploy only fetching component |
| `./deploy.sh dev processing` | Deploy only processing component |
| `./deploy.sh dev build` | Build all deployment artifacts |
| `./deploy.sh dev init` | Initialize Terraform |
| `./deploy.sh dev plan` | Plan infrastructure changes |
| `./deploy.sh dev destroy` | Destroy infrastructure |

### **Manual Component Building**
```bash
# Build Lambda Layer (heavy dependencies)
cd fetching/deployment_packages
./build_layer.sh --publish

# Build Lambda packages (lightweight)
./build_packages.sh

# Build Docker container
cd processing/container_images
./build_container.sh
```

## 📦 **Lambda Layers Solution**

### **🎯 Problem Solved**
AWS Lambda has a **70MB package size limit**, but our dependencies (pandas, yfinance, polygon-api-client) exceed this limit. 

### **✅ Solution: Lambda Layers**
- **Layer**: Heavy dependencies (pandas, yfinance, polygon-api-client) → ~40-50MB
- **Function**: Lightweight code only (requests, pydantic, psycopg2) → ~5-10MB
- **Total**: Under 70MB limit ✅

### **🏗️ Layer Architecture**
```
Lambda Layer (40-50MB):
├── pandas/
├── numpy/
├── yfinance/
├── polygon-api-client/
└── pandas-market-calendars/

Lambda Function (5-10MB):
├── daily_ohlcv_fetcher.py
├── daily_meta_fetcher.py
├── shared/clients/
├── shared/models/
└── lightweight dependencies
```

### **🔄 Layer Management**
```bash
# Build and publish layer
./deploy.sh dev layer

# The layer ARN will be automatically used by Terraform
# Add to terraform.tfvars:
lambda_layer_arns = ["arn:aws:lambda:region:account:layer:condvest-batch-dependencies:1"]
```

## 🏭 **Industrial Benefits**

### ✅ **Production Advantages**
- **Single Command Deployment**: `./deploy.sh prod all`
- **Consistent Infrastructure**: All modules deployed together
- **Dependency Management**: Terraform handles module dependencies
- **State Management**: Single state file for production

### ✅ **Development Advantages**
- **Component Isolation**: Test individual components
- **Fast Iteration**: Deploy only what changed
- **Independent Testing**: Each component has its own Terraform
- **Parallel Development**: Teams can work on different components

### ✅ **Enterprise Features**
- **Terraform Modules**: Reusable across environments
- **Version Control**: Each component can be versioned
- **CI/CD Ready**: Scripts work in automation pipelines
- **Cost Optimization**: Deploy only what you need for testing

## 📊 **Component Details**

### **Fetching Component**
- **Purpose**: Fetch daily OHLCV and metadata from external APIs
- **Technology**: AWS Lambda (Python)
- **Scheduling**: EventBridge cron expressions
- **Output**: Data stored in PostgreSQL

### **Processing Component**
- **Purpose**: Resample data using Fibonacci intervals (3-34 days)
- **Technology**: AWS Batch + Fargate Spot (70% cost savings)
- **Trigger**: Automated after data fetching
- **Output**: Resampled data for backtesting

### **Database Component**
- **Purpose**: PostgreSQL optimized for time-series data
- **Technology**: RDS PostgreSQL with custom parameter group
- **Features**: Automated backups, monitoring, security groups

### **Shared Component**
- **Purpose**: Common IAM roles, security groups, utilities
- **Technology**: Terraform modules
- **Benefits**: DRY principle, centralized security

## 🔄 **Terraform State Management**

### **Production State**
```hcl
# Single state file for production
backend "s3" {
  bucket = "condvest-terraform-state"
  key    = "batch-layer/terraform.tfstate"
  region = "ca-west-1"
}
```

### **Component Testing States**
```hcl
# Separate state files for testing
backend "s3" {
  bucket = "condvest-terraform-state"
  key    = "batch-layer/components/fetching/terraform.tfstate"
  region = "ca-west-1"
}
```

## 🛠️ **Development Workflow**

### **1. Component Development**
```bash
# Work on fetching component
cd fetching/
# Make changes to lambda_functions/
./deployment_packages/build_packages.sh
./terraform/
terraform apply
```

### **2. Integration Testing**
```bash
# Test all components together
./deploy.sh dev all
```

### **3. Production Deployment**
```bash
# Deploy to production
./deploy.sh prod all
```

## 📈 **Monitoring & Costs**

### **Cost Optimization**
- **Fargate Spot**: 70% savings on batch processing
- **Component-based testing**: Deploy only what's needed
- **Scheduled scaling**: Resources scale to zero when not needed

### **Monitoring**
- **CloudWatch Logs**: Centralized logging for all components
- **Terraform Outputs**: Key ARNs and endpoints
- **Cost Tags**: All resources tagged for cost tracking

## 🔧 **Prerequisites**

- AWS CLI configured
- Terraform >= 1.5.0
- Docker (for processing component)
- Python 3.11+ (for Lambda functions)

## 🎯 **Next Steps**

This modular structure provides the foundation for:
1. **Speed Layer**: Real-time processing components
2. **Serving Layer**: API and query interfaces  
3. **Multi-Environment**: Dev/Staging/Prod separation
4. **Team Scaling**: Multiple teams working on different components

The architecture follows industrial best practices used by Netflix, Airbnb, and other tech giants! 🚀