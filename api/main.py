from fastapi import FastAPI
from api.routes.weather import router as weather_router

app = FastAPI(
    title="Weather API",
    description="Fetches and caches weather data",
    version="1.0.0"
)

app.include_router(weather_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
