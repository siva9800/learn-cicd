"""
Unit tests for the demo app.

These exist so the CI pipeline has something real to run. If a student breaks
the app, a test fails, and CI blocks the change before it can ever be deployed -
that is the whole point of the "test as a quality gate" lesson (Day 2).
"""

import sys
import os

# Make the app package importable when tests run from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import main  # noqa: E402


def client():
    main.app.config["TESTING"] = True
    return main.app.test_client()


def test_home_returns_200():
    response = client().get("/")
    assert response.status_code == 200
    assert b"Hello from the CI/CD demo" in response.data


def test_health_returns_ok():
    response = client().get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_unknown_route_returns_404():
    response = client().get("/does-not-exist")
    assert response.status_code == 404
