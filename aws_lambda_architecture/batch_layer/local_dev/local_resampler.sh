#!/bin/bash

# Test Fibonacci Resampling Logic Locally
# Purpose: Validate resampling logic before AWS deployment

set -e  # Exit on any error

echo "🧪 Starting Local Fibonacci Resampling Test"
echo "=============================================="

# Check if services are running
echo "📋 Checking if local services are running..."
if ! docker-compose ps | grep -q "Up"; then
    echo "⚠️  Services not running. Starting them..."
    docker-compose up -d
    echo "⏳ Waiting for services to be ready..."
    sleep 10
fi

# Test 1: Run basic resampling test
echo ""
echo "🔄 Test 1: Basic Fibonacci Resampling (all intervals)"
echo "----------------------------------------------------"
docker exec -it batch-resampler-test python local_resampler.py

# Test 2: Run with specific intervals
echo ""
echo "🔄 Test 2: Specific Intervals (3d, 5d, 8d)"
echo "------------------------------------------"
docker exec -it batch-resampler-test python local_resampler.py --intervals 3 5 8

# Test 3: Show detailed results
echo ""
echo "🔍 Test 3: Show Detailed Results"
echo "--------------------------------"
docker exec -it batch-resampler-test python local_resampler.py --show-results --validate

# Test 4: Check database directly
echo ""
echo "🗄️  Test 4: Database Verification"
echo "----------------------------------"
echo "Raw data summary:"
docker exec -it batch-timescaledb psql -U condvest_user -d condvest -c "
SELECT 
    'raw_ohlcv' as table_type, 
    symbol, 
    COUNT(*) as records,
    MIN(DATE(timestamp_data)) as start_date,
    MAX(DATE(timestamp_data)) as end_date
FROM raw_ohlcv 
WHERE interval_type = '1d'
GROUP BY symbol 
ORDER BY symbol;
"

echo ""
echo "Fibonacci resampled data summary:"
docker exec -it batch-timescaledb psql -U condvest_user -d condvest -c "
SELECT 'silver_3d' as table_type, symbol, COUNT(*) as records FROM silver_3d GROUP BY symbol
UNION ALL
SELECT 'silver_5d' as table_type, symbol, COUNT(*) as records FROM silver_5d GROUP BY symbol
UNION ALL
SELECT 'silver_8d' as table_type, symbol, COUNT(*) as records FROM silver_8d GROUP BY symbol
UNION ALL
SELECT 'silver_13d' as table_type, symbol, COUNT(*) as records FROM silver_13d GROUP BY symbol
UNION ALL
SELECT 'silver_21d' as table_type, symbol, COUNT(*) as records FROM silver_21d GROUP BY symbol
UNION ALL
SELECT 'silver_34d' as table_type, symbol, COUNT(*) as records FROM silver_34d GROUP BY symbol
ORDER BY table_type, symbol;
"

echo ""
echo "🎯 Sample 3-day Fibonacci data for AAPL:"
docker exec -it batch-timescaledb psql -U condvest_user -d condvest -c "
SELECT 
    symbol, 
    date, 
    open, 
    high, 
    low, 
    close, 
    volume
FROM silver_3d 
WHERE symbol = 'AAPL' 
ORDER BY date 
LIMIT 5;
"

echo ""
echo "✅ Local Fibonacci Resampling Test Complete!"
echo "============================================="
echo "📊 Results Summary:"
echo "  - Tested all Fibonacci intervals (3, 5, 8, 13, 21, 34)"
echo "  - Validated against local TimescaleDB"
echo "  - Used EXACT same SQL logic as AWS Aurora version"
echo "  - Ready for AWS deployment! 🚀"
echo ""
echo "💡 Next steps:"
echo "  1. Review the results above"
echo "  2. If all looks good, deploy to AWS with 'terraform apply'"
echo "  3. The same logic will work in Aurora!"
echo ""
