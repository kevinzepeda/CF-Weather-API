import json
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.background import BackgroundTasks
import requests
from models.weather import (
    WeatherResponse,
    WeatherFullResponse,
    LocationData,
    CurrentWeather,
    Forecast,
    WeatherAlert
)
from core.config import (
    redis_client,
    settings,
    weather_api_providers,
    logger
)
from datetime import datetime, timedelta
import asyncio
from aiohttp import ClientSession
import aioredis
import gzip
from utils.circuit_breaker import CircuitBreaker
from utils.cache_strategies import (
    get_cached_weather,
    set_cached_weather,
    warm_cache_for_popular_locations
)

router = APIRouter()

weather_circuit_breaker = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=60
)

async def fetch_from_provider(url: str, session: ClientSession) -> Optional[Dict]:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None
    except Exception as e:
        logger.error(f"Error fetching from {url}: {str(e)}")
        return None

async def aggregate_weather_data(city: str) -> Dict:
    async with ClientSession() as session:
        tasks = []
        for provider in weather_api_providers:
            url = provider["url_template"].format(location=city)
            tasks.append(fetch_from_provider(url, session))

        results = await asyncio.gather(*tasks)
        valid_results = [res for res in results if res is not None]

        if not valid_results:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="All weather providers failed"
            )
        return merge_weather_data(valid_results)

def merge_weather_data(sources: list) -> Dict:
    """
    Normalize and merge data from multiple weather sources
    with weighted averages based on source reliability
    """
    primary_source = sources[0]
    return primary_source

def enrich_weather_data(raw_data: Dict) -> Dict:
    """
    Add derived metrics and enhance the raw weather data
    """
    # Implement data enrichment logic
    return raw_data

@router.get("/weather/{city}", response_model=WeatherResponse)
async def get_weather(
    city: str,
    background_tasks: BackgroundTasks,
    extended: bool = Query(False, description="Include extended forecast data"),
    units: str = Query("metric", enum=["metric", "imperial"])
):
    compressed_key = f"{city}:compressed"
    cached_data = await get_cached_weather(compressed_key)

    if cached_data:
        return gzip.decompress(cached_data).decode('utf-8')

    try:
        with weather_circuit_breaker:
            raw_data = await aggregate_weather_data(city)
            enriched_data = enrich_weather_data(raw_data)

            background_tasks.add_task(
                set_cached_weather,
                key=compressed_key,
                value=gzip.compress(json.dumps(enriched_data).encode('utf-8')),
                ttl=3600
            )

            background_tasks.add_task(
                warm_cache_for_popular_locations,
                city
            )

            return enriched_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting weather for {city}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service temporarily unavailable"
        )

@router.get("/weather/full/{city}", response_model=WeatherFullResponse)
async def get_full_weather(
    city: str,
    background_tasks: BackgroundTasks
):
    """
    Endpoint with comprehensive weather data including:
    - Current conditions
    - Forecasts
    - Alerts
    - Historical data
    """
    pass

@router.get("/weather/alerts/{city}", response_model=list[WeatherAlert])
async def get_weather_alerts(city: str):
    """
    Specialized endpoint for severe weather alerts
    """
    pass

@router.get("/weather/historical/{city}")
async def get_historical_weather(
    city: str,
    days: int = Query(7, ge=1, le=365)
):
    """
    Endpoint for historical weather data
    """
    pass
