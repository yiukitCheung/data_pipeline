"""
Client modules for AWS Lambda Architecture
"""

from .polygon_client import PolygonClient
from .aurora_client import AuroraClient  # Deprecated: use RDSTimescaleClient
from .rds_timescale_client import RDSTimescaleClient  # Primary production client
from .local_postgres_client import LocalPostgresClient
from .kinesis_client import KinesisClient
from .redis_client import RedisClient

__all__ = [
    'PolygonClient', 
    'RDSTimescaleClient',  # Primary client for production
    'AuroraClient',        # Kept for backward compatibility
    'LocalPostgresClient',
    'KinesisClient',
    'RedisClient'
]
