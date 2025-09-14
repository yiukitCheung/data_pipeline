# API Documentation

This document describes the API endpoints available in both the **Prefect Medallion Architecture** and **AWS Lambda Architecture** implementations.

## 🚀 API Overview

### Architecture Comparison
| Feature | Medallion Architecture | AWS Lambda Architecture |
|---------|----------------------|-------------------------|
| **Base URL** | `http://localhost:8080` | `https://api.condvest.com` |
| **Authentication** | API Key (optional) | AWS API Gateway + API Key |
| **Rate Limiting** | Custom implementation | AWS API Gateway built-in |
| **Caching** | Redis (optional) | ElastiCache + CloudFront |
| **Real-time** | WebSocket (custom) | API Gateway WebSocket |

## 📊 Serving Layer APIs

### Live Price Data

#### Get Single Symbol Price
```http
GET /live/{symbol}
```

**Parameters:**
- `symbol` (path): Stock symbol (e.g., "AAPL")

**Example Request:**
```bash
curl -X GET "https://api.condvest.com/live/AAPL" \
  -H "X-API-Key: your-api-key"
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "price": 234.07,
    "open": 229.22,
    "high": 234.51,
    "low": 229.02,
    "close": 234.07,
    "volume": 55824216,
    "change": 4.85,
    "change_percent": 2.12,
    "timestamp": "2025-09-12T22:00:00Z",
    "interval": "1d",
    "source": "CACHE"
  },
  "timestamp": "2025-09-13T10:30:00Z"
}
```

#### Get Multiple Symbol Prices
```http
GET /live?symbols={symbol1,symbol2,symbol3}
```

**Parameters:**
- `symbols` (query): Comma-separated list of symbols

**Example Request:**
```bash
curl -X GET "https://api.condvest.com/live?symbols=AAPL,MSFT,GOOGL" \
  -H "X-API-Key: your-api-key"
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "prices": {
      "AAPL": {
        "symbol": "AAPL",
        "price": 234.07,
        "change": 4.85,
        "change_percent": 2.12,
        "volume": 55824216,
        "timestamp": "2025-09-12T22:00:00Z",
        "source": "CACHE"
      },
      "MSFT": {
        "symbol": "MSFT",
        "price": 509.90,
        "change": 3.25,
        "change_percent": 0.64,
        "volume": 23624884,
        "timestamp": "2025-09-12T22:00:00Z",
        "source": "CACHE"
      },
      "GOOGL": {
        "symbol": "GOOGL",
        "price": 240.80,
        "change": 0.43,
        "change_percent": 0.18,
        "volume": 26771610,
        "timestamp": "2025-09-12T22:00:00Z",
        "source": "DATABASE"
      }
    },
    "cache_hit_rate": 0.67,
    "total_symbols": 3,
    "successful_symbols": 3,
    "timestamp": "2025-09-13T10:30:00Z"
  }
}
```

### Historical Data

#### Get Historical OHLCV Data
```http
GET /historical/{symbol}?start_date={date}&end_date={date}&interval={interval}
```

**Parameters:**
- `symbol` (path): Stock symbol
- `start_date` (query): Start date (YYYY-MM-DD)
- `end_date` (query): End date (YYYY-MM-DD)
- `interval` (query): Time interval (1d, 1h, 5m, etc.)

**Example Request:**
```bash
curl -X GET "https://api.condvest.com/historical/AAPL?start_date=2025-09-01&end_date=2025-09-12&interval=1d" \
  -H "X-API-Key: your-api-key"
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "interval": "1d",
    "data": [
      {
        "timestamp": "2025-09-01T00:00:00Z",
        "open": 225.50,
        "high": 230.75,
        "low": 224.10,
        "close": 229.87,
        "volume": 45123456,
        "interval": "1d"
      },
      {
        "timestamp": "2025-09-02T00:00:00Z",
        "open": 229.87,
        "high": 232.45,
        "low": 227.90,
        "close": 231.22,
        "volume": 38567890,
        "interval": "1d"
      }
    ],
    "count": 2,
    "timestamp": "2025-09-13T10:30:00Z"
  }
}
```

### Trading Signals

#### Get Trading Signals
```http
GET /signals/{symbol}?strategy={strategy}&timeframe={timeframe}
```

**Parameters:**
- `symbol` (path): Stock symbol
- `strategy` (query): Strategy name (vegas_channel, rsi, macd)
- `timeframe` (query): Timeframe (1m, 5m, 1h, 1d)

**Example Request:**
```bash
curl -X GET "https://api.condvest.com/signals/AAPL?strategy=vegas_channel&timeframe=1h" \
  -H "X-API-Key: your-api-key"
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "signals": [
      {
        "signal_id": "vegas_aapl_1h_20250913_103000",
        "symbol": "AAPL",
        "signal_type": "BUY",
        "strategy": "vegas_channel",
        "confidence": 0.85,
        "price": 234.07,
        "timestamp": "2025-09-13T10:30:00Z",
        "metadata": {
          "ema_12": 232.45,
          "ema_144": 228.90,
          "ema_169": 228.10,
          "channel_position": "above",
          "trend_strength": "strong"
        }
      }
    ],
    "count": 1,
    "timestamp": "2025-09-13T10:30:00Z"
  }
}
```

## 🔧 Batch Layer APIs

### Batch Processing

#### Trigger Daily OHLCV Fetch
```http
POST /batch/daily-ohlcv
```

**Request Body:**
```json
{
  "symbols": ["AAPL", "MSFT", "GOOGL"],
  "date": "2025-09-12",
  "force": false
}
```

**Example Request:**
```bash
curl -X POST "https://api.condvest.com/batch/daily-ohlcv" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["AAPL", "MSFT"],
    "date": "2025-09-12",
    "force": false
  }'
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "job_id": "daily-ohlcv-2025-09-12-1726234567",
    "status": "RUNNING",
    "message": "Daily OHLCV fetch initiated",
    "symbols_count": 2,
    "target_date": "2025-09-12",
    "estimated_completion": "2025-09-13T10:35:00Z"
  },
  "timestamp": "2025-09-13T10:30:00Z"
}
```

#### Get Batch Job Status
```http
GET /batch/job/{job_id}
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "job_id": "daily-ohlcv-2025-09-12-1726234567",
    "job_type": "DAILY_OHLCV",
    "status": "COMPLETED",
    "start_time": "2025-09-13T10:30:00Z",
    "end_time": "2025-09-13T10:33:45Z",
    "symbols_processed": ["AAPL", "MSFT"],
    "records_processed": 2,
    "error_message": null
  }
}
```

## ⚡ Speed Layer APIs (Real-time)

### WebSocket Connection

#### Connect to Real-time Data Stream
```javascript
// WebSocket endpoint
const ws = new WebSocket('wss://api.condvest.com/ws');

// Subscribe to symbols
ws.send(JSON.stringify({
  action: 'subscribe',
  symbols: ['AAPL', 'MSFT', 'GOOGL']
}));

// Receive real-time data
ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('Real-time data:', data);
};
```

**Real-time Message Format:**
```json
{
  "type": "tick",
  "symbol": "AAPL",
  "price": 234.15,
  "volume": 1000,
  "timestamp": "2025-09-13T10:30:15.123Z",
  "exchange": "XNAS",
  "conditions": [12, 37]
}
```

### Market Status

#### Get Market Status
```http
GET /market/status
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "market": "open",
    "session": "regular",
    "next_open": "2025-09-16T14:30:00Z",
    "next_close": "2025-09-13T21:00:00Z",
    "timezone": "America/New_York",
    "trading_day": "2025-09-13"
  }
}
```

## 🛠️ Development & Utility APIs

### Health Check

#### System Health Check
```http
GET /health
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "services": {
      "api": "running",
      "timescaledb": "connected",
      "redis": "connected",
      "kafka": "connected"
    },
    "version": "1.0.0",
    "uptime": "2d 14h 32m",
    "timestamp": "2025-09-13T10:30:00Z"
  }
}
```

### Development Endpoints

#### Test Database Connection
```http
GET /dev/test-connection
```

#### Get Environment Info
```http
GET /dev/environment
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "environment": {
      "POSTGRES_URL": "Connected",
      "REDIS_URL": "Connected",
      "KAFKA_BOOTSTRAP_SERVERS": "Not set",
      "POLYGON_API_KEY": "***",
      "AWS_DEFAULT_REGION": "us-east-1"
    }
  }
}
```

## 🔐 Authentication & Security

### API Key Authentication
All production API endpoints require an API key:

```bash
# Include in header
curl -H "X-API-Key: your-api-key" https://api.condvest.com/live/AAPL

# Or in query parameter (not recommended for production)
curl "https://api.condvest.com/live/AAPL?api_key=your-api-key"
```

### Rate Limiting
- **Development**: No limits
- **Production**: 1000 requests/hour per API key
- **Premium**: 10,000 requests/hour per API key

**Rate Limit Headers:**
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1726237200
```

## 📈 Response Formats

### Success Response
```json
{
  "success": true,
  "data": {
    // Response data
  },
  "timestamp": "2025-09-13T10:30:00Z"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error message",
  "code": "ERROR_CODE",
  "timestamp": "2025-09-13T10:30:00Z"
}
```

### Common Error Codes
- `INVALID_SYMBOL`: Symbol not found or invalid format
- `INVALID_DATE`: Date format or range invalid
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `AUTHENTICATION_FAILED`: Invalid or missing API key
- `INTERNAL_ERROR`: Server-side error
- `DATA_NOT_AVAILABLE`: Requested data not available

## 🔧 Local Development

### Starting Local API Server
```bash
# Medallion Architecture
cd prefect_medallion/
python local_api_server.py
# Available at: http://localhost:8080

# AWS Lambda Architecture
cd aws_lambda_architecture/local_dev/
python local_api_server.py
# Available at: http://localhost:8080
```

### Testing APIs Locally
```bash
# Test health endpoint
curl http://localhost:8080/health

# Test live prices
curl http://localhost:8080/live/AAPL

# Test multiple symbols
curl "http://localhost:8080/live?symbols=AAPL,MSFT,GOOGL"
```

## 📚 SDK & Client Libraries

### Python SDK Example
```python
import requests

class CondvestAPI:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {'X-API-Key': api_key}
    
    def get_live_price(self, symbol):
        response = requests.get(
            f"{self.base_url}/live/{symbol}",
            headers=self.headers
        )
        return response.json()
    
    def get_historical_data(self, symbol, start_date, end_date, interval='1d'):
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'interval': interval
        }
        response = requests.get(
            f"{self.base_url}/historical/{symbol}",
            headers=self.headers,
            params=params
        )
        return response.json()

# Usage
api = CondvestAPI('https://api.condvest.com', 'your-api-key')
price_data = api.get_live_price('AAPL')
historical = api.get_historical_data('AAPL', '2025-09-01', '2025-09-12')
```

### JavaScript SDK Example
```javascript
class CondvestAPI {
  constructor(baseUrl, apiKey) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
  }

  async getLivePrice(symbol) {
    const response = await fetch(`${this.baseUrl}/live/${symbol}`, {
      headers: { 'X-API-Key': this.apiKey }
    });
    return response.json();
  }

  async getMultiplePrices(symbols) {
    const symbolsStr = symbols.join(',');
    const response = await fetch(`${this.baseUrl}/live?symbols=${symbolsStr}`, {
      headers: { 'X-API-Key': this.apiKey }
    });
    return response.json();
  }
}

// Usage
const api = new CondvestAPI('https://api.condvest.com', 'your-api-key');
const priceData = await api.getLivePrice('AAPL');
const multiplePrices = await api.getMultiplePrices(['AAPL', 'MSFT', 'GOOGL']);
```

## 🚀 Production Considerations

### Caching Strategy
- **Live Prices**: 1-5 second cache
- **Historical Data**: 1 hour cache
- **Signals**: 30 second cache
- **Market Status**: 5 minute cache

### Performance Optimization
- Use batch endpoints for multiple symbols
- Implement client-side caching
- Use WebSocket for real-time updates
- Leverage CDN for static content

### Error Handling
- Implement exponential backoff for retries
- Handle rate limiting gracefully
- Validate input parameters
- Log errors for debugging

This API documentation provides a comprehensive guide to integrating with both Condvest data pipeline implementations. Choose the endpoints and architecture that best fits your use case.
