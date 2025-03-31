import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from core.config import settings, logger, redis_client
from utils.circuit_breaker import weather_circuit_breaker
from utils.cache_strategies import warm_cache_for_popular_locations
from api.routes import weather, alerts, forecast
import prometheus_client
from prometheus_client import make_asgi_app
import uvloop

uvloop.install()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management with async context"""

    logger.info("Starting CF Weather API service")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Redis connected: {await redis_client.ping()}")


    await warm_cache_for_popular_locations("new york")
    await warm_cache_for_popular_locations("london")
    await warm_cache_for_popular_locations("tokyo")

    yield


    logger.info("Shutting down CF Weather API service")
    await redis_client.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Hyper-scalable Weather API with multi-source integration",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)


metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    weather.router,
    prefix="/api/v1/weather",
    tags=["Weather Data"]
)
app.include_router(
    alerts.router,
    prefix="/api/v1/alerts",
    tags=["Weather Alerts"]
)
app.include_router(
    forecast.router,
    prefix="/api/v1/forecast",
    tags=["Weather Forecasts"]
)

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Endpoint for health checks and service status"""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "redis": "connected" if await redis_client.ping() else "disconnected",
        "circuit_breaker": weather_circuit_breaker.get_state().name
    }

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Custom validation error handler"""
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.on_event("startup")
async def startup_event():
    """Additional startup configurations"""
    logger.info("Application startup complete")
    logger.info(f"Available providers: {[p['name'] for p in settings.active_providers]}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None,  # Use our custom logging
        server_header=False
    )
