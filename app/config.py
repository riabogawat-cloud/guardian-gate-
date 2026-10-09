import os


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Rate limiting: at most RATE_LIMIT_REQUESTS per RATE_LIMIT_WINDOW seconds per client
    RATE_LIMIT_ENABLED = _flag("RATE_LIMIT_ENABLED")
    RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

    # Caching: entries expire after CACHE_TTL seconds (safety net if invalidation is missed)
    CACHE_ENABLED = _flag("CACHE_ENABLED")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))


settings = Settings()
