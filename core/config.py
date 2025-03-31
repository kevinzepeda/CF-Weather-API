import redis

class Settings:
    REDIS_HOST = "redis"
    REDIS_PORT = 6379
    REDIS_DB = 0

settings = Settings()
redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB, decode_responses=True)
