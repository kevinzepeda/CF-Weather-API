import json
import gzip
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Union
import aioredis
from core.config import redis_client, logger, CacheKeys
from models.weather import WeatherResponse, WeatherFullResponse
import random
from utils.circuit_breaker import CircuitBreakerError

cache_circuit_breaker = CircuitBreaker(
    name="redis_cache",
    failure_threshold=3,
    recovery_timeout=30,
    expected_exceptions=(ConnectionError, TimeoutError)
)

class CacheMiss(Exception):
    """Custom exception for cache misses"""

class CacheStrategy:
    @staticmethod
    async def get_cached_weather(
        location: str,
        extended: bool = False
    ) -> Union[WeatherResponse, WeatherFullResponse, None]:
        """
        Unified method to get cached weather data with fallback strategies
        """
        try:
            async with cache_circuit_breaker:
                # Try compressed cache first
                compressed_data = await redis_client.get(
                    CacheKeys.weather_key(location) + ":compressed"
                )
                if compressed_data:
                    return WeatherResponse.parse_raw(
                        gzip.decompress(compressed_data).decode('utf-8')
                    )

                # Fallback to uncompressed cache
                uncompressed_data = await redis_client.get(
                    CacheKeys.weather_key(location)
                )
                if uncompressed_data:
                    return WeatherResponse.parse_raw(uncompressed_data.decode('utf-8'))

                raise CacheMiss(f"No cached data for {location}")
        except CircuitBreakerError as e:
            logger.warning(f"Cache circuit open: {e}")
            raise CacheMiss("Cache service unavailable")
        except Exception as e:
            logger.error(f"Cache read error: {str(e)}")
            raise CacheMiss("Cache read failed")

    @staticmethod
    async def set_cached_weather(
        location: str,
        data: Union[Dict, WeatherResponse],
        ttl: int = 3600,
        compress: bool = True
    ) -> bool:
        """
        Store weather data with adaptive caching strategy
        """
        try:
            async with cache_circuit_breaker:
                serialized_data = data.json() if isinstance(data, (WeatherResponse, WeatherFullResponse)) \
                    else json.dumps(data)

                # Adaptive TTL based on data freshness
                effective_ttl = ttl
                if isinstance(data, dict) and data.get('current', {}).get('timestamp'):
                    data_age = (datetime.utcnow() - datetime.fromisoformat(
                        data['current']['timestamp'])).total_seconds()
                    effective_ttl = max(300, ttl - int(data_age))  # Minimum 5 minutes

                if compress:
                    await redis_client.setex(
                        CacheKeys.weather_key(location) + ":compressed",
                        effective_ttl,
                        gzip.compress(serialized_data.encode('utf-8'))
                else:
                    await redis_client.setex(
                        CacheKeys.weather_key(location),
                        effective_ttl,
                        serialized_data.encode('utf-8'))

                # Set secondary keys for location-based queries
                await redis_client.setex(
                    CacheKeys.location_key(location.lower()),
                    effective_ttl * 2,  # Longer TTL for location mapping
                    json.dumps({
                        'primary_cache_key': CacheKeys.weather_key(location),
                        'last_updated': datetime.utcnow().isoformat()
                    })
                )
                return True
        except Exception as e:
            logger.error(f"Cache write error: {str(e)}")
            return False

    @staticmethod
    async def warm_cache_for_popular_locations(
        primary_location: str,
        radius_km: int = 50
    ) -> None:
        """
        Proactively cache weather for nearby popular locations
        """
        try:
            nearby_locations = await LocationService.get_nearby_locations(
                primary_location,
                radius_km
            )

            for location in nearby_locations[:3]:  # Limit to top 3 nearby
                if random.random() < 0.7:  # 70% chance to pre-warm
                    asyncio.create_task(
                        CacheStrategy._async_warm_location(location['name'])
                    )
        except Exception as e:
            logger.warning(f"Cache warming failed: {str(e)}")

    @staticmethod
    async def _async_warm_location(location: str) -> None:
        """Background task to warm cache for a location"""
        try:
            # Simulate API call - in practice this would call your weather service
            weather_data = {"location": location, "temp": 20.5}
            await CacheStrategy.set_cached_weather(location, weather_data)
            logger.debug(f"Successfully warmed cache for {location}")
        except Exception as e:
            logger.debug(f"Failed to warm cache for {location}: {str(e)}")

    @staticmethod
    async def sliding_window_cache(
        key: str,
        operation: Callable,
        window_size: int = 60,
        max_operations: int = 100
    ) -> Any:
        """
        Implement sliding window rate limiting pattern
        """
        now = datetime.utcnow().timestamp()
        window_start = now - window_size

        async with redis_client.pipeline() as pipe:
            try:
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                pipe.zadd(key, {str(now): now})
                pipe.expire(key, window_size)
                _, count, _, _ = await pipe.execute()

                if count > max_operations:
                    raise CircuitBreakerError("Rate limit exceeded")

                return await operation()
            except Exception as e:
                logger.warning(f"Sliding window error: {str(e)}")
                raise

class LocationService:
    """Mock location service for demonstration"""
    @staticmethod
    async def get_nearby_locations(location: str, radius_km: int) -> List[Dict]:
        # In a real implementation, this would query a geospatial database
        return [
            {"name": "Nearby City 1", "distance": 30},
            {"name": "Nearby Town 2", "distance": 45},
        ]

# Pre-configured strategies
get_cached_weather = CacheStrategy.get_cached_weather
set_cached_weather = CacheStrategy.set_cached_weather
warm_cache_for_popular_locations = CacheStrategy.warm_cache_for_popular_locations
sliding_window_cache = CacheStrategy.sliding_window_cache
