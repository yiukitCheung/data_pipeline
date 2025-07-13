import polars as pl
from typing import List, Optional, Dict, Any
import json
from datetime import datetime
from tools.redis_client import RedisTools
from prefect import get_run_logger

class CacheManager:
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize the cache manager with Redis connection
        
        Args:
            redis_url: Optional Redis URL. If not provided, will use REDIS_URL from environment
        """
        self.redis = RedisTools(redis_url=redis_url, prefix="gold_cache")
        self.logger = get_run_logger()
        
    def cache_latest_picks(self, pl_df: pl.DataFrame) -> bool:
        """
        Cache the latest picks from gold data for a specific strategy
        
        Args:
            df: Polars DataFrame containing the gold data
            strategy_name: Name of the strategy (e.g., 'vegas_channel')
            
        Returns:
            bool: True if caching was successful, False otherwise
        """
        try:
            # Get all strategies from the gold data
            strategy_names = pl_df.columns
            
            # Get the last row of the gold data
            latest_data = pl_df.head(1)
            
            # Extract the picks for the strategy
            for strategy_name in strategy_names:
                symbol = latest_data.select([f"{strategy_name}"]).to_dicts()[0][f"{strategy_name}"]
                
                # Convert date object to string if it's a date
                if hasattr(symbol, 'strftime'):
                    symbol = symbol.strftime("%Y-%m-%d")
                elif symbol is not None:
                    symbol = str(symbol)
            
                # Clear existing list and add new symbol
                self.redis.delete(f"{strategy_name}")
                self.redis.rpush(f"{strategy_name}", symbol)
                
                self.logger.info(f"Cache Manager: Successfully cached {symbol} for {strategy_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Cache Manager: Error caching picks for {strategy_name}: {str(e)}")
            return False
            
    def get_cached_picks(self, strategy_name: str) -> Optional[List[str]]:
        """
        Retrieve cached picks for a specific strategy
        
        Args:
            strategy_name: Name of the strategy (e.g., 'vegas_channel')
            
        Returns:
            Optional[List[str]]: List of symbols, or None if not found
        """
        try:
            cached_data = self.redis.lrange(f"{strategy_name}", 0, -1)
            if cached_data:
                return cached_data
            return None
            
        except Exception as e:
            self.logger.error(f"Cache Manager: Error retrieving cached picks for {strategy_name}: {str(e)}")
            return None
            
    def clear_strategy_cache(self, strategy_name: str) -> bool:
        """
        Clear cached picks for a specific strategy
        
        Args:
            strategy_name: Name of the strategy to clear cache for
            
        Returns:
            bool: True if cache was cleared successfully, False otherwise
        """
        try:
            self.redis.delete(f"{strategy_name}")
            self.logger.info(f"Cache Manager: Cleared cache for {strategy_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Cache Manager: Error clearing cache for {strategy_name}: {str(e)}")
            return False
            
    def get_all_cached_strategies(self) -> List[str]:
        """
        Get list of all strategies that have cached picks
        
        Returns:
            List[str]: List of strategy names with cached data
        """
        try:
            keys = self.redis.keys("*")
            return [key.replace("gold_cache:", "") for key in keys]
            
        except Exception as e:
            self.logger.error(f"Cache Manager: Error getting cached strategies: {str(e)}")
            return []
            
    def is_cache_valid(self, strategy_name: str, max_age_hours: int = 24) -> bool:
        """
        Check if the cached picks for a strategy are still valid
        
        Args:
            strategy_name: Name of the strategy to check
            max_age_hours: Maximum age of cache in hours before considering it invalid
            
        Returns:    
            bool: True if cache is valid, False otherwise
        """
        try:
            cached_data = self.get_cached_picks(strategy_name)
            if not cached_data:
                return False
                
            cache_time = datetime.strptime(cached_data["timestamp"], "%Y-%m-%d %H:%M:%S")
            age_hours = (datetime.now() - cache_time).total_seconds() / 3600
            
            return age_hours <= max_age_hours
            
        except Exception as e:
            self.logger.error(f"Cache Manager: Error checking cache validity for {strategy_name}: {str(e)}")
            return False
