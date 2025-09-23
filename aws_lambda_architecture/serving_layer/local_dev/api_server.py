"""
Local FastAPI server simulating API Gateway + Lambda for serving layer
Purpose: Test API endpoints locally without AWS deployment
"""

import os
import sys
import json
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, date

# Add shared modules to path
sys.path.append('/app')
sys.path.append('/app/shared')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Condvest Serving Layer API",
    description="Local development server for serving layer endpoints",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import Lambda function (simulate Lambda handler)
try:
    sys.path.append('/app/lambda_functions')
    from api_live_prices import lambda_handler as live_prices_handler
except ImportError as e:
    logger.error(f"Error importing Lambda functions: {e}")
    live_prices_handler = None

@app.get("/")
async def root():
    return {
        "message": "Condvest Serving Layer API - Local Development",
        "version": "1.0.0",
        "environment": "local",
        "endpoints": {
            "live_prices": "/api/v1/prices/live/{symbol}",
            "fibonacci_data": "/api/v1/fibonacci/{symbol}/{interval}",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": "local",
        "database": "connected"  # TODO: Add actual DB health check
    }

@app.get("/api/v1/prices/live/{symbol}")
async def get_live_prices(symbol: str):
    """
    Get live prices for a symbol
    Simulates API Gateway -> Lambda -> Aurora
    """
    try:
        if not live_prices_handler:
            raise HTTPException(status_code=500, detail="Lambda handler not available")
        
        # Create Lambda event
        event = {
            "pathParameters": {"symbol": symbol.upper()},
            "httpMethod": "GET",
            "headers": {},
            "queryStringParameters": None
        }
        
        # Mock Lambda context
        class MockContext:
            def __init__(self):
                self.function_name = "api_live_prices"
                self.memory_limit_in_mb = 512
                self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:api_live_prices"
                
        context = MockContext()
        
        # Call Lambda handler
        response = live_prices_handler(event, context)
        
        # Parse Lambda response
        if response['statusCode'] == 200:
            return json.loads(response['body'])
        else:
            raise HTTPException(
                status_code=response['statusCode'],
                detail=json.loads(response['body']).get('error', 'Unknown error')
            )
            
    except Exception as e:
        logger.error(f"Error getting live prices for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/fibonacci/{symbol}/{interval}")
async def get_fibonacci_data(
    symbol: str,
    interval: str,
    limit: Optional[int] = Query(100, description="Number of records to return"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)")
):
    """
    Get Fibonacci resampled data for a symbol and interval
    Direct database access (no Lambda for this endpoint)
    """
    try:
        from shared.clients.local_postgres_client import LocalPostgresClient
        
        # Connect to database
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise HTTPException(status_code=500, detail="Database URL not configured")
        
        client = LocalPostgresClient(db_url)
        
        # Validate interval
        valid_intervals = ['3d', '5d', '8d', '13d', '21d', '34d']
        if interval not in valid_intervals:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid interval. Must be one of: {valid_intervals}"
            )
        
        # Build query
        table_name = f"silver_{interval}"
        query = f"""
        SELECT symbol, date, open, high, low, close, volume, created_at
        FROM {table_name}
        WHERE symbol = %s
        """
        
        params = [symbol.upper()]
        
        if start_date:
            query += " AND date >= %s"
            params.append(start_date)
        
        query += " ORDER BY date DESC LIMIT %s"
        params.append(limit)
        
        # Execute query
        result = client.execute_query(query, params)
        
        if not result:
            return {
                "symbol": symbol.upper(),
                "interval": interval,
                "data": [],
                "count": 0
            }
        
        # Format response
        data = []
        for row in result:
            data.append({
                "symbol": row[0],
                "date": row[1].isoformat() if hasattr(row[1], 'isoformat') else str(row[1]),
                "open": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "close": float(row[5]),
                "volume": int(row[6]),
                "created_at": row[7].isoformat() if hasattr(row[7], 'isoformat') else str(row[7])
            })
        
        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "data": data,
            "count": len(data),
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error getting Fibonacci data for {symbol}/{interval}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/symbols")
async def get_active_symbols():
    """
    Get all active symbols
    """
    try:
        from shared.clients.local_postgres_client import LocalPostgresClient
        
        db_url = os.environ.get('DATABASE_URL')
        client = LocalPostgresClient(db_url)
        
        query = """
        SELECT symbol, company_name, sector, industry, market_cap
        FROM symbol_metadata 
        WHERE is_active = true AND symbol != '_SAMPLE_DATA_LOADED_'
        ORDER BY symbol
        """
        
        result = client.execute_query(query)
        
        symbols = []
        for row in result:
            symbols.append({
                "symbol": row[0],
                "company_name": row[1],
                "sector": row[2],
                "industry": row[3],
                "market_cap": int(row[4]) if row[4] else None
            })
        
        return {
            "symbols": symbols,
            "count": len(symbols)
        }
        
    except Exception as e:
        logger.error(f"Error getting active symbols: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/fibonacci/intervals")
async def get_fibonacci_intervals():
    """
    Get available Fibonacci intervals
    """
    return {
        "intervals": [
            {"interval": "3d", "description": "3-day Fibonacci interval"},
            {"interval": "5d", "description": "5-day Fibonacci interval"},
            {"interval": "8d", "description": "8-day Fibonacci interval"},
            {"interval": "13d", "description": "13-day Fibonacci interval"},
            {"interval": "21d", "description": "21-day Fibonacci interval"},
            {"interval": "34d", "description": "34-day Fibonacci interval"}
        ]
    }

if __name__ == "__main__":
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "8000"))
    
    logger.info(f"Starting Condvest Serving Layer API on {host}:{port}")
    logger.info("Available endpoints:")
    logger.info("  GET /                              - API info")
    logger.info("  GET /health                        - Health check")
    logger.info("  GET /api/v1/prices/live/{symbol}   - Live prices")
    logger.info("  GET /api/v1/fibonacci/{symbol}/{interval} - Fibonacci data")
    logger.info("  GET /api/v1/symbols                - Active symbols")
    logger.info("  GET /api/v1/fibonacci/intervals    - Available intervals")
    
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
