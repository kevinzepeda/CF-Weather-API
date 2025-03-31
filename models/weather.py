from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from enum import Enum

class UnitsSystem(str, Enum):
    METRIC = "metric"
    IMPERIAL = "imperial"

class Coordinates(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")

class LocationData(BaseModel):
    name: str = Field(..., description="Location name")
    coordinates: Coordinates
    timezone: str = Field(..., description="IANA timezone identifier")
    elevation: Optional[float] = Field(None, description="Elevation in meters")

class TemperatureData(BaseModel):
    value: float = Field(..., description="Temperature value")
    unit: str = Field("°C", description="Temperature unit")
    feels_like: float = Field(..., description="Apparent temperature")

class WindData(BaseModel):
    speed: float = Field(..., ge=0, description="Wind speed")
    direction: int = Field(..., ge=0, le=360, description="Wind direction in degrees")
    gust: Optional[float] = Field(None, ge=0, description="Wind gust speed")

class PrecipitationData(BaseModel):
    probability: float = Field(..., ge=0, le=1, description="Probability of precipitation")
    amount: Optional[float] = Field(None, ge=0, description="Expected precipitation amount in mm")
    type: Optional[str] = Field(None, description="Type of precipitation (rain, snow, etc.)")

class WeatherCondition(BaseModel):
    main: str = Field(..., description="Primary weather condition")
    description: str = Field(..., description="Detailed weather description")
    icon: Optional[str] = Field(None, description="Weather icon code")

class AirQualityData(BaseModel):
    aqi: int = Field(..., ge=0, le=500, description="Air Quality Index")
    pm25: Optional[float] = Field(None, ge=0, description="PM2.5 concentration")
    pm10: Optional[float] = Field(None, ge=0, description="PM10 concentration")
    o3: Optional[float] = Field(None, ge=0, description="Ozone concentration")

class UVIndex(BaseModel):
    value: float = Field(..., ge=0, description="UV Index value")
    risk_level: str = Field(..., description="Risk level category")

class AstronomyData(BaseModel):
    sunrise: datetime = Field(..., description="Sunrise time")
    sunset: datetime = Field(..., description="Sunset time")
    moon_phase: Optional[float] = Field(None, ge=0, le=1, description="Moon phase (0-1)")

class ForecastPeriod(BaseModel):
    timestamp: datetime = Field(..., description="Forecast valid time")
    temperature: TemperatureData
    conditions: List[WeatherCondition]
    precipitation: PrecipitationData
    humidity: float = Field(..., ge=0, le=100, description="Relative humidity percentage")
    pressure: float = Field(..., ge=0, description="Atmospheric pressure in hPa")
    wind: WindData
    visibility: Optional[float] = Field(None, ge=0, description="Visibility in meters")
    uv_index: Optional[UVIndex] = Field(None, description="UV Index data")

class WeatherAlert(BaseModel):
    title: str = Field(..., description="Alert headline")
    severity: str = Field(..., description="Alert severity level")
    time: datetime = Field(..., description="Time alert was issued")
    expires: datetime = Field(..., description="Time alert expires")
    description: str = Field(..., description="Detailed alert description")
    regions: List[str] = Field(..., description="Affected regions")

class CurrentWeather(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Observation time")
    temperature: TemperatureData
    conditions: List[WeatherCondition]
    wind: WindData
    precipitation: PrecipitationData
    humidity: float = Field(..., ge=0, le=100, description="Relative humidity percentage")
    pressure: float = Field(..., ge=0, description="Atmospheric pressure in hPa")
    visibility: float = Field(..., ge=0, description="Visibility in meters")
    uv_index: Optional[UVIndex]
    air_quality: Optional[AirQualityData]
    feels_like: float = Field(..., description="Apparent temperature")
    dew_point: float = Field(..., description="Dew point temperature")
    cloud_cover: int = Field(..., ge=0, le=100, description="Cloud cover percentage")

class Forecast(BaseModel):
    hourly: List[ForecastPeriod] = Field(..., description="Hourly forecast data")
    daily: List[ForecastPeriod] = Field(..., description="Daily forecast data")
    minutely: Optional[List[ForecastPeriod]] = Field(None, description="Minutely precipitation forecast")

class WeatherResponse(BaseModel):
    location: LocationData
    current: CurrentWeather
    last_updated: datetime = Field(..., description="When data was last refreshed")
    units: UnitsSystem = Field(UnitsSystem.METRIC, description="Measurement units system")

class WeatherFullResponse(WeatherResponse):
    forecast: Forecast
    alerts: List[WeatherAlert]
    astronomy: AstronomyData
    historical: Optional[Dict[str, CurrentWeather]] = Field(
        None,
        description="Historical weather data for previous days"
    )

    @validator('historical')
    def validate_historical_days(cls, v):
        if v and len(v) > 14:
            raise ValueError("Historical data limited to 14 days")
        return v

class WeatherCacheMetadata(BaseModel):
    cached_at: datetime
    expires_at: datetime
    source: str = Field(..., description="Which API provided this data")
    is_aggregated: bool = Field(False, description="Whether data is merged from multiple sources")
