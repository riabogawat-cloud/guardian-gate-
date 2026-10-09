import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import get_redis
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Base


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    fake = fakeredis.FakeRedis(decode_responses=True)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = lambda: fake
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    yield TestClient(app)
    app.dependency_overrides.clear()


NEW = {"invoice_number": "INV-001", "customer_name": "Acme", "amount": "1500.50"}


def test_create_and_get_uses_cache(client):
    created = client.post("/invoices", json=NEW)
    assert created.status_code == 201
    iid = created.json()["id"]

    first = client.get(f"/invoices/{iid}")
    second = client.get(f"/invoices/{iid}")
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert first.json() == second.json()


def test_update_invalidates_cache(client):
    iid = client.post("/invoices", json=NEW).json()["id"]
    client.get(f"/invoices/{iid}")  # warms cache
    client.patch(f"/invoices/{iid}", json={"status": "paid"})
    after = client.get(f"/invoices/{iid}")
    assert after.headers["X-Cache"] == "MISS"   # cache was cleared
    assert after.json()["status"] == "paid"      # and we see fresh data


def test_list_cache_invalidated_on_create(client):
    client.post("/invoices", json=NEW)
    assert client.get("/invoices").headers["X-Cache"] == "MISS"
    assert client.get("/invoices").headers["X-Cache"] == "HIT"
    client.post("/invoices", json={**NEW, "invoice_number": "INV-002"})
    fresh = client.get("/invoices")
    assert fresh.headers["X-Cache"] == "MISS"
    assert len(fresh.json()) == 2


def test_delete_then_404(client):
    iid = client.post("/invoices", json=NEW).json()["id"]
    client.get(f"/invoices/{iid}")
    assert client.delete(f"/invoices/{iid}").status_code == 204
    assert client.get(f"/invoices/{iid}").status_code == 404


def test_duplicate_invoice_number_conflict(client):
    client.post("/invoices", json=NEW)
    assert client.post("/invoices", json=NEW).status_code == 409


def test_validation_error(client):
    bad = {**NEW, "amount": "-5"}
    assert client.post("/invoices", json=bad).status_code == 422


def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS", 3)
    codes = [client.get("/invoices").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    blocked = client.get("/invoices")
    assert "Retry-After" in blocked.headers


def test_rate_limit_is_per_client(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS", 1)
    assert client.get("/invoices", headers={"x-api-key": "A"}).status_code == 200
    assert client.get("/invoices", headers={"x-api-key": "A"}).status_code == 429
    assert client.get("/invoices", headers={"x-api-key": "B"}).status_code == 200
