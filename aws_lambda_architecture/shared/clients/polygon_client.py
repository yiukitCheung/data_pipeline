"""
Polygon.io client for AWS Lambda Architecture
Adapted from the existing Prefect Medallion implementation
"""

import requests
import logging
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from polygon import RESTClient
from decimal import Decimal

from ..models.data_models import OHLCVData

logger = logging.getLogger(__name__)


class PolygonClient:
    """
    Polygon.io API client optimized for AWS Lambda usage
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = RESTClient(api_key=self.api_key)
        self.base_url = "https://api.polygon.io"
    
    def get_active_symbols(self, limit: int = 100) -> List[str]:
        """
        Get active stock symbols for data fetching
        Returns a limited list suitable for AWS Lambda batch processing
        
        Args:
            limit: Maximum number of symbols to return
            
        Returns:
            List of stock symbols
        """
        try:
            tickers_response = self.client.list_tickers(
                market="stocks",
                active=True,
                limit=limit
            )
            # Filter for common stocks on major exchanges
            symbols = [
                ticker.ticker for ticker in tickers_response 
                if ticker.type in ['CS', 'ADRC'] 
                and ticker.primary_exchange in ['XNYS', 'XNAS', 'XAMS']
            ]
            
            if symbols:
                logger.info(f"Retrieved {len(symbols)} active symbols from API")
                return symbols[:limit]  # Ensure we don't exceed the limit
            else:
                logger.warning("No symbols returned from API, using fallback")
                # Fallback to default symbols (weekend-safe)
                fallback_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM", "V", "JNJ"]
                return fallback_symbols[:limit]
            
        except Exception as e:
            logger.error(f"Error fetching active symbols: {e}")
            # Fallback to default symbols (weekend-safe)
            fallback_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM", "V", "JNJ"]
            return fallback_symbols[:limit]
    
    def fetch_meta(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch metadata for a given symbol
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            
        Returns:
            Dictionary containing symbol metadata or None if not found
        """
        try:
            params = {
                'ticker': symbol,
                'apiKey': self.api_key,
            }

            url = "https://api.polygon.io/v3/reference/tickers/"
            response = requests.get(url, params=params)

            if response.status_code != 200:
                logger.error(f"API request failed with status code {response.status_code}")
                return None

            response_json = response.json()
            return response_json['results'][0] if response_json.get('results') else None
            
        except Exception as e:
            logger.error(f"Error fetching metadata for {symbol}: {e}")
            return None
    
    def fetch_ohlcv_data(
        self, 
        symbol: str, 
        target_date: date,
        timespan: str = "day",
        multiplier: int = 1
    ) -> Optional[OHLCVData]:
        """
        Fetch OHLCV data for a specific symbol and date
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            target_date: Date to fetch data for
            timespan: "minute", "hour", "day", "week", "month", "quarter", "year"
            multiplier: Size of timespan multiplier
            
        Returns:
            OHLCVData object or None if no data found
        """
        try:
            # Convert date to string format for API
            date_str = target_date.strftime('%Y-%m-%d')
            
            # Use the aggregates endpoint for OHLCV data
            aggs = self.client.get_aggs(
                ticker=symbol,
                multiplier=multiplier,
                timespan=timespan,
                from_=date_str,
                to=date_str
            )
            
            if not aggs or len(aggs) == 0:
                logger.warning(f"No OHLCV data found for {symbol} on {date_str}")
                return None
            
            # Take the first (and usually only) result
            bar = aggs[0]
            
            # Convert to our data model
            ohlcv_data = OHLCVData(
                symbol=symbol,
                timestamp=datetime.fromtimestamp(bar.timestamp / 1000),  # Convert from milliseconds
                open=Decimal(str(bar.open)),
                high=Decimal(str(bar.high)),
                low=Decimal(str(bar.low)),
                close=Decimal(str(bar.close)),
                volume=int(bar.volume),
                interval=f"{multiplier}{timespan[0]}"
            )
            
            logger.info(f"Fetched OHLCV data for {symbol} on {date_str}")
            return ohlcv_data
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV data for {symbol} on {target_date}: {e}")
            return None
    
    def fetch_ticker_ohlcv(self, symbol: str, start_date: str, end_date: str) -> Optional[List[Dict]]:
        """
        Fetch OHLCV data for a date range (compatible with existing code)
        
        Args:
            symbol: Stock symbol
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of OHLCV data dictionaries or None if error
        """
        try:
            params = {
                'multiplier': 1,
                'timespan': 'day',
                'adjusted': False,
                'sort': 'asc',
                'apiKey': self.api_key
            }
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
            response = requests.get(url, params=params)
            response_json = response.json()
            
            return response_json.get('results', [])
        
        except Exception as e:
            logger.error(f"Error fetching OHLCV data for {symbol}: {e}")
            return None
    
    def fetch_batch_ohlcv_data(
        self, 
        symbols: List[str], 
        target_date: date
    ) -> List[OHLCVData]:
        """
        Fetch OHLCV data for multiple symbols for a specific date
        
        Args:
            symbols: List of stock symbols
            target_date: Date to fetch data for
            
        Returns:
            List of OHLCVData objects
        """
        results = []
        
        for symbol in symbols:
            try:
                ohlcv_data = self.fetch_ohlcv_data(symbol, target_date)
                if ohlcv_data:
                    results.append(ohlcv_data)
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                continue
        
        logger.info(f"Successfully fetched OHLCV data for {len(results)}/{len(symbols)} symbols")
        return results
    
    def get_market_status(self) -> Dict[str, Any]:
        """
        Get current market status
        Returns a dictionary containing market status information
        """
        try:
            result = self.client.get_market_status()
            
            # Parse the response into a dictionary
            market_status = {
                'after_hours': result.after_hours,
                'currencies': {
                    'crypto': result.currencies.crypto,
                    'fx': result.currencies.fx
                },
                'early_hours': result.early_hours,
                'exchanges': {
                    'nasdaq': result.exchanges.nasdaq,
                    'nyse': result.exchanges.nyse,
                    'otc': result.exchanges.otc
                },
                'market': result.market,
                'server_time': result.server_time
            }
            
            return market_status
            
        except Exception as e:
            logger.error(f"Error getting market status: {e}")
            return {}
    
    def get_previous_trading_day(self, from_date: Optional[date] = None) -> date:
        """
        Get the previous trading day from a given date
        Simple implementation - in production, use a proper market calendar
        
        Args:
            from_date: Date to start from (defaults to today)
            
        Returns:
            Previous trading day (excludes weekends)
        """
        if from_date is None:
            from_date = date.today()
        
        # Simple approach: subtract days until we find a weekday
        current_date = from_date - timedelta(days=1)
        print(f"   Current date: {current_date}")
        while current_date.weekday() >= 5:  # Saturday=5, Sunday=6
            current_date -= timedelta(days=1)
        
        return current_date
