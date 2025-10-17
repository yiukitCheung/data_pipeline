"""
Client modules for AWS Lambda Architecture
"""

from .polygon_client import PolygonClient
from .fmp_client import FMPClient
from .aurora_client import AuroraClient  # Deprecated: use RDSTimescaleClient
from .rds_timescale_client import RDSPostgresClient  # Primary production client
from .kinesis_client import KinesisClient
from .redis_client import RedisClient

__all__ = [
    'PolygonClient',
    'FMPClient',
    'RDSPostgresClient',  # Primary client for production
    'AuroraClient',        # Kept for backward compatibility
    'KinesisClient',
    'RedisClient'
]
