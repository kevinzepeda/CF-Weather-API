from fastapi import APIRouter, HTTPException
import requests
import json
from models.weather import WeatherResponse
from core.config import redis_client

router = APIRouter()

def fetch_weather(city: str) -> dict:
    url = f"https://api.weather.gov/points/{city}"
    response = requests.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Error fetching data")
    return response.json()

@router.get("/weather/{city}", response_model=WeatherResponse)
def get_weather(city: str):
    cached_data = redis_client.get(city)
    if cached_data:
        return json.loads(cached_data)

    weather_data = fetch_weather(city)
    properties = weather_data.get("properties", {})
    temperature = properties.get("temperature", {}).get("value", 0.0)
    description = properties.get("textDescription", "No description available")

    result = {"city": city, "temperature": temperature, "description": description}
    redis_client.setex(city, 3600, json.dumps(result))
    return result
