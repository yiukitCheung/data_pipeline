"""
Local FastAPI server that simulates API Gateway + Lambda for development
"""

import os
import sys
import json
import uvicorn
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional
import logging

# Add shared modules to path
sys.path.append('/app')
sys.path.append('/app/shared')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import Lambda functions
try:
    from serving_layer.lambda_functions.api_live_prices import lambda_handler as live_prices_handler
    from batch_layer.lambda_functions.daily_ohlcv_fetcher import lambda_handler as batch_handler
    from speed_layer.lambda_functions.websocket_handler import lambda_handler as websocket_handler
except ImportError as e:
    logger.error(f"Error importing Lambda functions: {e}")
    # Create mock handlers for development
    def live_prices_handler(event, context):
        return {"statusCode": 200, "body": json.dumps({"message": "Mock live prices handler"})}
    
    def batch_handler(event, context):
        return {"statusCode": 200, "body": json.dumps({"message": "Mock batch handler"})}
    
    def websocket_handler(event, context):
        return {"statusCode": 200, "body": json.dumps({"message": "Mock websocket handler"})}

# Create FastAPI app
app = FastAPI(
    title="Condvest Lambda Architecture API",
    description="Local development server for AWS Lambda Architecture",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock Lambda context
class MockContext:
    def __init__(self):
        self.function_name = "local-dev"
        self.function_version = "1.0.0"
        self.invoked_function_arn = "arn:aws:lambda:local:123456789012:function:local-dev"
        self.memory_limit_in_mb = "1024"
        self.remaining_time_in_millis = lambda: 300000

    def get_remaining_time_in_millis(self):
        return 300000


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Condvest Lambda Architecture Local Development Server",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "services": {
            "api": "running",
            "timescaledb": "connected" if check_timescale_connection() else "disconnected",
            "redis": "connected" if check_redis_connection() else "disconnected",
            "kafka": "connected" if check_kafka_connection() else "disconnected"
        }
    }


# ===============================================
# Live Prices API (Serving Layer)
# ===============================================

@app.get("/live/{symbol}")
async def get_live_price(symbol: str = Path(..., description="Stock symbol")):
    """Get live price for a single symbol"""
    
    event = {
        "httpMethod": "GET",
        "pathParameters": {"symbol": symbol},
        "queryStringParameters": None
    }
    
    try:
        response = live_prices_handler(event, MockContext())
        
        if response["statusCode"] == 200:
            body = json.loads(response["body"])
            return body
        else:
            body = json.loads(response["body"])
            raise HTTPException(status_code=response["statusCode"], detail=body.get("error", "Unknown error"))
            
    except Exception as e:
        logger.error(f"Error in live price endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/live")
async def get_multiple_live_prices(symbols: str = Query(..., description="Comma-separated list of symbols")):
    """Get live prices for multiple symbols"""
    
    event = {
        "httpMethod": "GET",
        "pathParameters": None,
        "queryStringParameters": {"symbols": symbols}
    }
    
    try:
        response = live_prices_handler(event, MockContext())
        
        if response["statusCode"] == 200:
            body = json.loads(response["body"])
            return body
        else:
            body = json.loads(response["body"])
            raise HTTPException(status_code=response["statusCode"], detail=body.get("error", "Unknown error"))
            
    except Exception as e:
        logger.error(f"Error in multiple live prices endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===============================================
# Batch Processing API (Batch Layer)
# ===============================================

@app.post("/batch/daily-ohlcv")
async def trigger_daily_ohlcv(
    symbols: Optional[List[str]] = None,
    date: Optional[str] = None,
    force: bool = False
):
    """Trigger daily OHLCV batch processing"""
    
    event = {
        "symbols": symbols,
        "date": date,
        "force": force
    }
    
    try:
        response = batch_handler(event, MockContext())
        
        if response["statusCode"] == 200:
            body = json.loads(response["body"])
            return body
        else:
            body = json.loads(response["body"])
            raise HTTPException(status_code=response["statusCode"], detail=body.get("error", "Unknown error"))
            
    except Exception as e:
        logger.error(f"Error in batch processing endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===============================================
# WebSocket API (Speed Layer)
# ===============================================

@app.post("/websocket/start")
async def start_websocket_client(symbols: Optional[List[str]] = None):
    """Start WebSocket client for real-time data"""
    
    event = {
        "symbols": symbols or ["AAPL", "MSFT", "GOOGL"]
    }
    
    try:
        response = websocket_handler(event, MockContext())
        
        if response["statusCode"] == 200:
            body = json.loads(response["body"])
            return body
        else:
            body = json.loads(response["body"])
            raise HTTPException(status_code=response["statusCode"], detail=body.get("error", "Unknown error"))
            
    except Exception as e:
        logger.error(f"Error in websocket endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===============================================
# Development Utilities
# ===============================================

@app.get("/dev/test-connection")
async def test_connections():
    """Test all service connections"""
    connections = {
        "timescaledb": check_timescale_connection(),
        "redis": check_redis_connection(),
        "kafka": check_kafka_connection(),
        "dynamodb": check_dynamodb_connection()
    }
    
    return {
        "connections": connections,
        "all_healthy": all(connections.values())
    }

@app.get("/dev/environment")
async def get_environment():
    """Get environment variables (for debugging)"""
    env_vars = {
        "POSTGRES_URL": os.environ.get("POSTGRES_URL", "Not set"),
        "REDIS_URL": os.environ.get("REDIS_URL", "Not set"),
        "KAFKA_BOOTSTRAP_SERVERS": os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "Not set"),
        "POLYGON_API_KEY": "***" if os.environ.get("POLYGON_API_KEY") else "Not set",
        "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "Not set")
    }
    
    return {"environment": env_vars}

# ===============================================
# Health Check Functions
# ===============================================

def check_timescale_connection() -> bool:
    """Check TimescaleDB connection"""
    try:
        import psycopg2
        postgres_url = os.environ.get("POSTGRES_URL")
        if not postgres_url:
            return False
        
        conn = psycopg2.connect(postgres_url)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return True
    except Exception:
        return False

def check_redis_connection() -> bool:
    """Check Redis connection"""
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            return False
        
        r = redis.from_url(redis_url)
        r.ping()
        return True
    except Exception:
        return False

def check_kafka_connection() -> bool:
    """Check Kafka connection"""
    try:
        from kafka import KafkaProducer
        bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
        if not bootstrap_servers:
            return False
        
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers.split(","),
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        producer.close()
        return True
    except Exception:
        return False

def check_dynamodb_connection() -> bool:
    """Check DynamoDB connection"""
    try:
        import boto3
        dynamodb_endpoint = os.environ.get("DYNAMODB_ENDPOINT")
        
        if dynamodb_endpoint:
            dynamodb = boto3.client('dynamodb', endpoint_url=dynamodb_endpoint)
        else:
            dynamodb = boto3.client('dynamodb')
        
        dynamodb.list_tables()
        return True
    except Exception:
        return False


# ===============================================
# Exception Handlers
# ===============================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "status_code": 500
        }
    )


if __name__ == "__main__":
    uvicorn.run(
        "local_api_server:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )
