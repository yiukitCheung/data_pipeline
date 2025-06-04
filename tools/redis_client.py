from redis import Redis
from typing import Optional, Any, Union, List
import os
from dotenv import load_dotenv

class RedisClient:
    def __init__(self, redis_url: Optional[str] = None, prefix: str = "cache"):
        """
        Initialize Redis client with optional URL from environment variable.
        
        Args:
            redis_url: Optional Redis URL. If not provided, will try to get from REDIS_URL env var
            prefix: Prefix for all keys stored in Redis
        """
        load_dotenv()  # Load environment variables from .env file
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        
        if not self.redis_url:
            raise ValueError("Redis URL must be provided either directly or through REDIS_URL environment variable")
        
        try:
            self.redis = Redis.from_url(self.redis_url)
            # Test connection immediately
            self.redis.ping()
            print("Successfully connected to Redis!")
        except Exception as e:
            print(f"Failed to connect to Redis: {str(e)}")
            raise
        
        self.prefix = prefix

    def _get_key(self, key: str) -> str:
        """Add prefix to key if not already present"""
        if not key.startswith(f"{self.prefix}:"):
            return f"{self.prefix}:{key}"
        return key

    def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        return self.redis.get(self._get_key(key))
    
    def set(self, key: str, value: str, expire: Optional[int] = None) -> None:
        """
        Set value in Redis with optional expiration
        
        Args:
            key: Key to set
            value: Value to store
            expire: Optional expiration time in seconds
        """
        self.redis.set(self._get_key(key), value, ex=expire)
    
    def delete(self, key: str) -> None:
        """Delete a key from Redis"""
        self.redis.delete(self._get_key(key))
    
    def exists(self, key: str) -> bool:
        """Check if a key exists in Redis"""
        return bool(self.redis.exists(self._get_key(key)))
    
    def setex(self, key: str, seconds: int, value: str) -> None:
        """Set value with expiration time"""
        self.redis.setex(self._get_key(key), seconds, value)
    
    def ttl(self, key: str) -> int:
        """Get time to live for a key"""
        return self.redis.ttl(self._get_key(key))
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get all keys matching pattern"""
        return [k.decode() for k in self.redis.keys(self._get_key(pattern))]
    
    def flush_all(self) -> None:
        """Delete all keys in the current database"""
        self.redis.flushdb()
    
    def ping(self) -> bool:
        """Test Redis connection"""
        return self.redis.ping()

if __name__ == "__main__":
    # Try with explicit localhost URL first
    redis_client = RedisClient()
    print(redis_client.ping())
    print(redis_client.get("test"))
    redis_client.set("test", "test")
    print(redis_client.get("test"))
    redis_client.delete("test")
    print(redis_client.get("test"))