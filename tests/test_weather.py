import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from api.main import app
from models.weather import WeatherResponse
import json
import gzip

client = TestClient(app)

@pytest.fixture
def mock_redis():
    with patch("api.routes.weather.redis_client") as mock:
        yield mock

@pytest.fixture
def mock_requests():
    with patch("api.routes.weather.requests.get") as mock:
        yield mock

@pytest.fixture
def sample_weather_data():
    return {
        "properties": {
            "temperature": {"value": 22.5},
            "textDescription": "Sunny",
            "timestamp": "2024-01-01T12:00:00Z"
        }
    }

@pytest.fixture
def cached_weather_data():
    return {
        "city": "london",
        "temperature": 18.5,
        "description": "Partly cloudy"
    }

@pytest.mark.asyncio
async def test_get_weather_with_cache(mock_redis, cached_weather_data):
    mock_redis.get.return_value = json.dumps(cached_weather_data).encode('utf-8')

    response = client.get("/api/v1/weather/london")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == cached_weather_data
    mock_redis.get.assert_called_once_with("weather:london")

@pytest.mark.asyncio
async def test_get_weather_with_compressed_cache(mock_redis, cached_weather_data):
    compressed = gzip.compress(json.dumps(cached_weather_data).encode('utf-8'))
    mock_redis.get.side_effect = [None, compressed]

    response = client.get("/api/v1/weather/london")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == cached_weather_data
    assert mock_redis.get.call_count == 2

@pytest.mark.asyncio
async def test_get_weather_without_cache(mock_redis, mock_requests, sample_weather_data):
    mock_redis.get.return_value = None
    mock_requests.return_value.json.return_value = sample_weather_data
    mock_requests.return_value.status_code = 200

    response = client.get("/api/v1/weather/newyork")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "city": "newyork",
        "temperature": 22.5,
        "description": "Sunny"
    }
    mock_redis.setex.assert_called_once()

@pytest.mark.asyncio
async def test_get_weather_api_failure(mock_redis, mock_requests):
    mock_redis.get.return_value = None
    mock_requests.return_value.status_code = 500

    response = client.get("/api/v1/weather/paris")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "detail" in response.json()

@pytest.mark.asyncio
async def test_circuit_breaker_trip(mock_redis, mock_requests):
    mock_redis.get.return_value = None
    mock_requests.return_value.status_code = 500

    for _ in range(3):
        response = client.get("/api/v1/weather/berlin")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    response = client.get("/api/v1/weather/berlin")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "Circuit is OPEN" in response.json()["detail"]

@pytest.mark.asyncio
async def test_validation_error():
    response = client.get("/api/v1/weather/invalid%20city%20name")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

@pytest.mark.asyncio
async def test_extended_weather_forecast(mock_redis):
    mock_redis.get.return_value = None
    response = client.get("/api/v1/weather/london?extended=true")
    assert response.status_code == status.HTTP_200_OK
    assert "forecast" in response.json()

@pytest.mark.asyncio
async def test_units_parameter(mock_redis):
    mock_redis.get.return_value = None
    response = client.get("/api/v1/weather/london?units=imperial")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["units"] == "imperial"
