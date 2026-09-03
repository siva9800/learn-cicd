# Multi-stage build: stage 1 installs deps, stage 2 is a slim runtime that ships
# only what we need. Ties back to the Docker module.

# ---- Stage 1: install dependencies ----
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
# Install into a separate prefix so we can copy just the packages to the runtime.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.12-slim
WORKDIR /app

# Copy the installed packages from the builder stage (no pip cache, no build tools).
COPY --from=builder /install /usr/local
# Copy only the application code.
COPY app/ ./app/

# Run as a non-root user for security.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# uvicorn is the ASGI server for FastAPI. "app.main:app" = module app/main.py, variable "app".
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
