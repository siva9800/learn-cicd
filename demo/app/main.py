"""
A tiny Flask web application used for the CI/CD demo.

It is deliberately small so the focus stays on the pipeline, not the app.
Two endpoints:
  GET /         -> a friendly HTML greeting (what a user sees)
  GET /health   -> a JSON health check (what Kubernetes and smoke tests use)
"""

import os
from flask import Flask, jsonify

app = Flask(__name__)

# The version is read from an environment variable so we can prove that a new
# deployment actually shipped. The pipeline sets APP_VERSION to the commit SHA.
APP_VERSION = os.getenv("APP_VERSION", "dev")


@app.route("/")
def home():
    return f"""
    <html>
      <head><title>CI/CD Demo</title></head>
      <body style="font-family: sans-serif; text-align: center; margin-top: 80px;">
        <h1>Hello from the CI/CD demo!</h1>
        <p>This page was built, tested, containerised, and deployed automatically.</p>
        <p>Running version: <strong>{APP_VERSION}</strong></p>
      </body>
    </html>
    """


@app.route("/health")
def health():
    # A readiness/liveness endpoint. Kubernetes probes and the pipeline smoke
    # test both call this. Returning HTTP 200 means "I am alive and ready".
    return jsonify(status="ok", version=APP_VERSION)


if __name__ == "__main__":
    # 0.0.0.0 so the app is reachable from outside the container, not just localhost.
    app.run(host="0.0.0.0", port=5000)
