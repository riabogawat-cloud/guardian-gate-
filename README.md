# GuardianGate: API Gateway & Caching Layer

FastAPI service for invoice CRUD with a Redis layer that does two jobs:
**rate limiting** (fixed window, per client) and **caching** (cache-aside with invalidation on writes).
MySQL is the source of truth (SQLAlchemy ORM). Everything runs with Docker Compose.

## Run
    cp .env.example .env        # edit the passwords
    docker compose up --build
    # API docs: http://localhost:8000/docs

## Test (no Docker needed; uses SQLite + fakeredis)
    pip install -r requirements-dev.txt
    pytest

## Endpoints
| Method | Path | Notes |
|---|---|---|
| POST | /invoices | 201, 409 on duplicate number, 422 on bad input |
| GET | /invoices?skip=&limit= | cached; header `X-Cache: HIT/MISS` |
| GET | /invoices/{id} | cached; 404 if missing |
| PATCH | /invoices/{id} | partial update; clears cache |
| DELETE | /invoices/{id} | 204; clears cache |
| GET | /health | not rate limited |

## Design
- **Rate limiter:** Redis key `rate:<api-key or IP>`, atomic MULTI/EXEC (SET NX EX, INCR, TTL). Over limit gives 429 + `Retry-After`. Fails open if Redis is down.
- **Cache:** key `invoice:<id>` and `invoices:list:<skip>:<limit>`, TTL 60s. Writes delete affected keys. Redis errors are treated as a cache miss.
- **Limitations:** fixed window allows boundary bursts; list invalidation drops all list pages; no auth; tables created with `create_all` (no migrations).

## Load test (measure your own numbers)
    pip install locust
    # 1) cache ON
    RATE_LIMIT_ENABLED=false CACHE_ENABLED=true  docker compose up -d --build
    locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 20 -r 5 -t 60s --csv=cache_on
    # 2) cache OFF
    RATE_LIMIT_ENABLED=false CACHE_ENABLED=false docker compose up -d --build
    locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 20 -r 5 -t 60s --csv=cache_off
    # compare median / p95 for /invoices/[id] in the *_stats.csv files
