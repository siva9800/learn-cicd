"""
A tiny FastAPI service for the CI/CD class demo.

Deliberately small so the focus stays on the PIPELINE, not the app.
  GET /         -> JSON greeting (what a user hits)
  GET /health   -> JSON health check (what Kubernetes probes and smoke tests hit)
"""
import os

from fastapi import FastAPI

app = FastAPI(title="CI/CD Demo")

# The version is read from an environment variable so a deployment can PROVE that a
# new version actually shipped. The CD pipeline sets APP_VERSION to the commit SHA.
APP_VERSION = os.getenv("APP_VERSION", "dev")


@app.get("/")
def home():
    return {"message": "Hello from the CI/CD demo!", "version": APP_VERSION}


@app.get("/health")
def health():
    # A readiness/liveness endpoint. Returning 200 means "I am alive and ready".
    return {"status": "ok", "version": APP_VERSION}
