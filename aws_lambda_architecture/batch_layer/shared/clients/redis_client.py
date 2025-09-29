"""
Redis Client for Speed Layer Caching and Pub/Sub

Handles real-time price caching, signal storage, and frontend notifications.
Used for instant data access and Redis Pub/Sub for frontend updates.
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timedelta
from decimal import Decimal

import redis.asyncio as redis
from redis.exceptions import RedisError, ConnectionError

logger = logging.getLogger(__name__)

class RedisClient:
    """
    Redis client for Speed Layer operations
    
    Features:
    - Latest price caching with TTL
    - OHLCV aggregation storage
    - Signal caching with expiration
    - Pub/Sub for frontend notifications
    - Async operations for performance
    """
    
    def __init__(
        self, 
        host: str = 'localhost', 
        port: int = 6379, 
        db: int = 0,
        password: Optional[str] = None,
        ssl: bool = False,
        decode_responses: bool = True
    ):
        """
        Initialize Redis client
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if auth required)
            ssl: Use SSL connection
            decode_responses: Decode byte responses to strings
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.ssl = ssl
        
        # Connection parameters
        self.connection_params = {
            'host': host,
            'port': port,
            'db': db,
            'decode_responses': decode_responses
        }
        
        if password:
            self.connection_params['password'] = password
        
        if ssl:
            self.connection_params['ssl'] = ssl
        
        # Redis client (will be initialized on first use)
        self.redis_client = None
        self.pubsub_client = None
        
        logger.info(f"Redis client configured for {host}:{port}")
    
    async def _get_client(self):
        """Get or create Redis client connection"""
        if self.redis_client is None:
            try:
                self.redis_client = redis.Redis(**self.connection_params)
                # Test connection
                await self.redis_client.ping()
                logger.info("Redis connection established successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                raise
        
        return self.redis_client
    
    async def set_latest_price(
        self, 
        symbol: str, 
        price: Union[float, Decimal], 
        volume: Optional[int] = None,
        ttl_seconds: int = 300  # 5 minutes default TTL
    ) -> bool:
        """
        Set latest price for a symbol with TTL
        
        Args:
            symbol: Stock symbol
            price: Latest price
            volume: Latest volume (optional)
            ttl_seconds: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            client = await self._get_client()
            
            # Prepare price data
            price_data = {
                'symbol': symbol,
                'price': float(price),
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'websocket'
            }
            
            if volume is not None:
                price_data['volume'] = volume
            
            # Set with TTL
            key = f"latest_price:{symbol}"
            await client.setex(
                key, 
                ttl_seconds, 
                json.dumps(price_data, default=str)
            )
            
            logger.debug(f"Set latest price for {symbol}: ${price}")
            return True
            
        except RedisError as e:
            logger.error(f"Redis error setting latest price for {symbol}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error setting latest price for {symbol}: {str(e)}")
            return False
    
    async def get_latest_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest price for a symbol
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Price data dict or None if not found
        """
        try:
            client = await self._get_client()
            key = f"latest_price:{symbol}"
            
            price_data = await client.get(key)
            if price_data:
                return json.loads(price_data)
            
            return None
            
        except RedisError as e:
            logger.error(f"Redis error getting latest price for {symbol}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error getting latest price for {symbol}: {str(e)}")
            return None
    
    async def set_ohlcv_minute(
        self, 
        symbol: str, 
        ohlcv_data: Dict[str, Any],
        ttl_seconds: int = 3600  # 1 hour default TTL
    ) -> bool:
        """
        Set 1-minute OHLCV data with TTL
        
        Args:
            symbol: Stock symbol
            ohlcv_data: OHLCV data dict
            ttl_seconds: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            client = await self._get_client()
            
            # Use minute-aligned timestamp as key suffix
            timestamp = datetime.fromisoformat(ohlcv_data['timestamp'].replace('Z', '+00:00'))
            minute_key = timestamp.strftime('%Y%m%d_%H%M')
            
            key = f"ohlcv_1m:{symbol}:{minute_key}"
            await client.setex(
                key,
                ttl_seconds,
                json.dumps(ohlcv_data, default=str)
            )
            
            logger.debug(f"Set 1m OHLCV for {symbol} at {minute_key}")
            return True
            
        except RedisError as e:
            logger.error(f"Redis error setting OHLCV for {symbol}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error setting OHLCV for {symbol}: {str(e)}")
            return False
    
    async def get_ohlcv_minute(
        self, 
        symbol: str, 
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Get 1-minute OHLCV data for specific time
        
        Args:
            symbol: Stock symbol
            timestamp: Target timestamp
            
        Returns:
            OHLCV data dict or None if not found
        """
        try:
            client = await self._get_client()
            
            minute_key = timestamp.strftime('%Y%m%d_%H%M')
            key = f"ohlcv_1m:{symbol}:{minute_key}"
            
            ohlcv_data = await client.get(key)
            if ohlcv_data:
                return json.loads(ohlcv_data)
            
            return None
            
        except RedisError as e:
            logger.error(f"Redis error getting OHLCV for {symbol}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error getting OHLCV for {symbol}: {str(e)}")
            return None
    
    async def cache_signal(
        self, 
        symbol: str, 
        signal_type: str, 
        signal_data: Dict[str, Any],
        ttl_seconds: int = 1800  # 30 minutes default for signals
    ) -> bool:
        """
        Cache a trading signal with TTL
        
        Args:
            symbol: Stock symbol
            signal_type: Type of signal (breakout, momentum, etc.)
            signal_data: Signal data dict
            ttl_seconds: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            client = await self._get_client()
            
            # Add metadata
            cached_signal = {
                **signal_data,
                'cached_at': datetime.utcnow().isoformat(),
                'expires_at': (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
            }
            
            key = f"signal:{signal_type}:{symbol}"
            await client.setex(
                key,
                ttl_seconds,
                json.dumps(cached_signal, default=str)
            )
            
            logger.debug(f"Cached {signal_type} signal for {symbol}")
            return True
            
        except RedisError as e:
            logger.error(f"Redis error caching signal for {symbol}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error caching signal for {symbol}: {str(e)}")
            return False
    
    async def get_signal(
        self, 
        symbol: str, 
        signal_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached trading signal
        
        Args:
            symbol: Stock symbol
            signal_type: Type of signal
            
        Returns:
            Signal data dict or None if not found/expired
        """
        try:
            client = await self._get_client()
            key = f"signal:{signal_type}:{symbol}"
            
            signal_data = await client.get(key)
            if signal_data:
                return json.loads(signal_data)
            
            return None
            
        except RedisError as e:
            logger.error(f"Redis error getting signal for {symbol}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error getting signal for {symbol}: {str(e)}")
            return None
    
    async def publish_price_update(
        self, 
        symbol: str, 
        price_data: Dict[str, Any]
    ) -> int:
        """
        Publish real-time price update to subscribers
        
        Args:
            symbol: Stock symbol
            price_data: Price update data
            
        Returns:
            Number of subscribers that received the message
        """
        try:
            client = await self._get_client()
            
            # Publish to symbol-specific channel
            channel = f"price_updates:{symbol}"
            message = json.dumps(price_data, default=str)
            
            subscribers = await client.publish(channel, message)
            
            # Also publish to general price updates channel
            general_channel = "price_updates:all"
            general_message = json.dumps({
                'symbol': symbol,
                **price_data
            }, default=str)
            
            await client.publish(general_channel, general_message)
            
            logger.debug(f"Published price update for {symbol} to {subscribers} subscribers")
            return subscribers
            
        except RedisError as e:
            logger.error(f"Redis error publishing price update for {symbol}: {str(e)}")
            return 0
        except Exception as e:
            logger.error(f"Error publishing price update for {symbol}: {str(e)}")
            return 0
    
    async def publish_signal(
        self, 
        symbol: str, 
        signal_data: Dict[str, Any]
    ) -> int:
        """
        Publish trading signal to subscribers
        
        Args:
            symbol: Stock symbol
            signal_data: Signal data
            
        Returns:
            Number of subscribers that received the message
        """
        try:
            client = await self._get_client()
            
            # Publish to signal-specific channel
            channel = f"signals:{symbol}"
            message = json.dumps(signal_data, default=str)
            
            subscribers = await client.publish(channel, message)
            
            # Also publish to general signals channel
            general_channel = "signals:all"
            general_message = json.dumps({
                'symbol': symbol,
                **signal_data
            }, default=str)
            
            await client.publish(general_channel, general_message)
            
            logger.debug(f"Published signal for {symbol} to {subscribers} subscribers")
            return subscribers
            
        except RedisError as e:
            logger.error(f"Redis error publishing signal for {symbol}: {str(e)}")
            return 0
        except Exception as e:
            logger.error(f"Error publishing signal for {symbol}: {str(e)}")
            return 0
    
    async def get_symbols_with_latest_prices(self) -> List[str]:
        """
        Get list of symbols that have latest prices cached
        
        Returns:
            List of symbol names
        """
        try:
            client = await self._get_client()
            
            # Find all latest_price keys
            keys = await client.keys("latest_price:*")
            
            # Extract symbols from keys
            symbols = [key.split(":", 1)[1] for key in keys]
            
            return sorted(symbols)
            
        except RedisError as e:
            logger.error(f"Redis error getting symbols: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting symbols: {str(e)}")
            return []
    
    async def close(self):
        """
        Close Redis connections
        """
        try:
            if self.redis_client:
                await self.redis_client.close()
                logger.info("Redis client connection closed")
            
            if self.pubsub_client:
                await self.pubsub_client.close()
                logger.info("Redis pub/sub connection closed")
                
        except Exception as e:
            logger.error(f"Error closing Redis connections: {str(e)}")
    
    async def health_check(self) -> bool:
        """
        Check Redis connection health
        
        Returns:
            True if Redis is accessible
        """
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {str(e)}")
            return False
