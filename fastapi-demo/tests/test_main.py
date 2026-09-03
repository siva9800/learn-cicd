"""
Tests the CI pipeline runs on every push. Break one of these and CI goes red,
blocking the change before it can ship - that is the whole point of Day 2.

FastAPI ships a TestClient (built on httpx) that calls the app in-process,
so no server needs to be running.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_returns_200():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"].startswith("Hello")


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_route_returns_404():
    assert client.get("/does-not-exist").status_code == 404
