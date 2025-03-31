import os
from functools import lru_cache
from typing import Dict, List, Optional
from pydantic import BaseSettings, RedisDsn, AnyUrl, validator
import aioredis
from logging.config import dictConfig
import logging
from dotenv import load_dotenv

load_dotenv()

class LoggingConfig(BaseSettings):
    LOG_LEVEL: str = "INFO"
    JSON_LOGS: bool = False

    class Config:
        env_prefix = "LOG_"

class RedisConfig(BaseSettings):
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"
    REDIS_CLUSTER_ENABLED: bool = False
    REDIS_CACHE_TTL: int = 3600  # 1 hour default
    REDIS_COMPRESSION_ENABLED: bool = True

    class Config:
        env_prefix = "REDIS_"

class WeatherProviderConfig(BaseSettings):
    NAME: str
    URL_TEMPLATE: str
    API_KEY: Optional[str] = None
    PRIORITY: int = 1
    RATE_LIMIT: Optional[int] = None
    ENABLED: bool = True

    class Config:
        env_prefix = "PROVIDER_"

class Settings(BaseSettings):
    PROJECT_NAME: str = "CF-Weather-API"
    ENVIRONMENT: str = "dev"
    DEBUG: bool = False

    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["*"]

    redis: RedisConfig = RedisConfig()

    logging: LoggingConfig = LoggingConfig()

    PROVIDERS: List[WeatherProviderConfig] = []

    REQUEST_TIMEOUT: int = 10
    CIRCUIT_BREAKER_THRESHOLD: int = 3

    API_KEYS: Dict[str, str] = {}  # API keys for external services

    class Config:
        env_file = ".env"
        case_sensitive = True

    @validator('PROVIDERS', pre=True)
    def parse_providers(cls, v):
        if isinstance(v, str):
            return [WeatherProviderConfig.parse_raw(v)]
        return v

@lru_cache()
def get_settings() -> Settings:
    return Settings()

def configure_logging():
    settings = get_settings()

    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json" if settings.logging.JSON_LOGS else "console": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter" if settings.logging.JSON_LOGS
                      else "logging.Formatter",
                "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s"
            }
        },
        "handlers": {
            "default": {
                "formatter": "json" if settings.logging.JSON_LOGS else "console",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            }
        },
        "loggers": {
            "": {
                "handlers": ["default"],
                "level": settings.logging.LOG_LEVEL
            }
        }
    })

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)

if settings.redis.REDIS_CLUSTER_ENABLED:
    redis_client = aioredis.RedisCluster.from_url(
        settings.redis.REDIS_URL,
        decode_responses=False
    )
else:
    redis_client = aioredis.from_url(
        settings.redis.REDIS_URL,
        decode_responses=False
    )

weather_api_providers = [
    {
        "name": "National Weather Service",
        "url_template": "https://api.weather.gov/points/{location}",
        "priority": 1
    },
    {
        "name": "OpenWeatherMap",
        "url_template": "https://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}",
        "api_key": os.getenv("OWM_API_KEY"),
        "priority": 2
    },
    {
        "name": "WeatherAPI",
        "url_template": "http://api.weatherapi.com/v1/current.json?key={api_key}&q={location}",
        "api_key": os.getenv("WEATHERAPI_KEY"),
        "priority": 3
    }
]

active_providers = [p for p in weather_api_providers if p.get("enabled", True)]
active_providers.sort(key=lambda x: x["priority"])

class CircuitBreakerConfig:
    FAILURE_THRESHOLD = settings.CIRCUIT_BREAKER_THRESHOLD
    RECOVERY_TIMEOUT = 60  # seconds
    MONITORING_WINDOW = 120  # seconds

class CacheKeys:
    WEATHER_PREFIX = "weather:"
    LOCATION_PREFIX = "location:"
    ALERTS_PREFIX = "alerts:"
    FORECAST_PREFIX = "forecast:"

    @classmethod
    def weather_key(cls, location: str) -> str:
        return f"{cls.WEATHER_PREFIX}{location.lower()}"

    @classmethod
    def forecast_key(cls, location: str) -> str:
        return f"{cls.FORECAST_PREFIX}{location.lower()}"
