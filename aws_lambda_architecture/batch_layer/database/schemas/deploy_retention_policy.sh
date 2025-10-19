#!/bin/bash

# ================================================================================
# DEPLOY RETENTION POLICY TO RDS
# ================================================================================
# Purpose: Deploy data retention policy (archive + deletion) to PostgreSQL RDS
# Usage:
#   1. Local testing: ./deploy_retention_policy.sh local
#   2. AWS RDS: ./deploy_retention_policy.sh rds
# ================================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RETENTION_POLICY_SQL="${SCRIPT_DIR}/retention_policy.sql"

# Function to print colored messages
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if psql is installed
check_psql() {
    if ! command -v psql &> /dev/null; then
        log_error "psql command not found. Please install PostgreSQL client."
        exit 1
    fi
    log_success "psql command found"
}

# Function to deploy to local TimescaleDB
deploy_local() {
    log_info "Deploying retention policy to LOCAL TimescaleDB..."
    
    DB_HOST="${DB_HOST:-localhost}"
    DB_PORT="${DB_PORT:-5432}"
    DB_NAME="${DB_NAME:-condvest}"
    DB_USER="${DB_USER:-postgres}"
    
    log_info "Connection details:"
    echo "  Host: ${DB_HOST}"
    echo "  Port: ${DB_PORT}"
    echo "  Database: ${DB_NAME}"
    echo "  User: ${DB_USER}"
    echo ""
    
    # Execute SQL
    PGPASSWORD="${DB_PASSWORD}" psql \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        -f "${RETENTION_POLICY_SQL}" \
        -v ON_ERROR_STOP=1
    
    if [ $? -eq 0 ]; then
        log_success "Retention policy deployed successfully to local database"
    else
        log_error "Failed to deploy retention policy"
        exit 1
    fi
}

# Function to deploy to AWS RDS
deploy_rds() {
    log_info "Deploying retention policy to AWS RDS..."
    
    # Check if AWS environment variables are set
    if [ -z "${RDS_ENDPOINT}" ] || [ -z "${RDS_USERNAME}" ] || [ -z "${RDS_PASSWORD}" ]; then
        log_error "AWS RDS credentials not set. Please set:"
        echo "  - RDS_ENDPOINT"
        echo "  - RDS_USERNAME"
        echo "  - RDS_PASSWORD"
        echo "  - RDS_DB_NAME (optional, defaults to 'condvest')"
        exit 1
    fi
    
    RDS_DB_NAME="${RDS_DB_NAME:-condvest}"
    
    log_info "Connection details:"
    echo "  Endpoint: ${RDS_ENDPOINT}"
    echo "  Database: ${RDS_DB_NAME}"
    echo "  User: ${RDS_USERNAME}"
    echo ""
    
    # Execute SQL
    PGPASSWORD="${RDS_PASSWORD}" psql \
        -h "${RDS_ENDPOINT}" \
        -p 5432 \
        -U "${RDS_USERNAME}" \
        -d "${RDS_DB_NAME}" \
        -f "${RETENTION_POLICY_SQL}" \
        -v ON_ERROR_STOP=1
    
    if [ $? -eq 0 ]; then
        log_success "Retention policy deployed successfully to RDS"
    else
        log_error "Failed to deploy retention policy to RDS"
        exit 1
    fi
}

# Function to dry-run (check what will be archived)
dry_run() {
    log_info "Running DRY RUN to check what will be archived..."
    
    if [ "$1" == "local" ]; then
        DB_HOST="${DB_HOST:-localhost}"
        DB_PORT="${DB_PORT:-5432}"
        DB_NAME="${DB_NAME:-condvest}"
        DB_USER="${DB_USER:-postgres}"
        
        PGPASSWORD="${DB_PASSWORD}" psql \
            -h "${DB_HOST}" \
            -p "${DB_PORT}" \
            -U "${DB_USER}" \
            -d "${DB_NAME}" \
            -c "
                SELECT 
                    COUNT(*) AS records_to_archive,
                    MIN(timestamp) AS oldest_record,
                    MAX(timestamp) AS newest_record_to_archive,
                    COUNT(DISTINCT symbol) AS unique_symbols
                FROM raw_ohlcv
                WHERE timestamp < CURRENT_DATE - INTERVAL '3 years 1 month';
            "
    else
        log_error "Dry run only supports 'local' for now"
        exit 1
    fi
}

# Main script logic
main() {
    echo "========================================"
    echo "  RETENTION POLICY DEPLOYMENT SCRIPT"
    echo "========================================"
    echo ""
    
    # Check if SQL file exists
    if [ ! -f "${RETENTION_POLICY_SQL}" ]; then
        log_error "retention_policy.sql not found at: ${RETENTION_POLICY_SQL}"
        exit 1
    fi
    
    log_success "Found retention_policy.sql"
    
    # Check psql
    check_psql
    
    # Parse command
    case "$1" in
        local)
            deploy_local
            ;;
        rds)
            deploy_rds
            ;;
        dry-run)
            dry_run "local"
            ;;
        test)
            log_info "Running test deployment to local database..."
            deploy_local
            log_info "Testing archival procedure..."
            DB_HOST="${DB_HOST:-localhost}"
            DB_PORT="${DB_PORT:-5432}"
            DB_NAME="${DB_NAME:-condvest}"
            DB_USER="${DB_USER:-postgres}"
            PGPASSWORD="${DB_PASSWORD}" psql \
                -h "${DB_HOST}" \
                -p "${DB_PORT}" \
                -U "${DB_USER}" \
                -d "${DB_NAME}" \
                -c "CALL archive_old_ohlcv_data();"
            ;;
        *)
            echo "Usage: $0 {local|rds|dry-run|test}"
            echo ""
            echo "Commands:"
            echo "  local    - Deploy to local TimescaleDB"
            echo "  rds      - Deploy to AWS RDS"
            echo "  dry-run  - Check what will be archived (local only)"
            echo "  test     - Deploy and run test archival (local only)"
            echo ""
            echo "Environment variables:"
            echo "  Local:"
            echo "    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD"
            echo ""
            echo "  RDS:"
            echo "    RDS_ENDPOINT, RDS_USERNAME, RDS_PASSWORD, RDS_DB_NAME"
            echo ""
            exit 1
            ;;
    esac
}

# Run main function
main "$@"

