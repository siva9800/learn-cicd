# Multi-stage build (ties back to the Docker module, Day 8).
# Stage 1 installs dependencies; stage 2 is a slim runtime that ships only what we need.

# ---- Stage 1: build / install dependencies ----
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
# Install into a separate prefix so we can copy just the packages to the runtime stage.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.12-slim
WORKDIR /app

# Copy the installed packages from the builder stage (no pip cache, no build tools).
COPY --from=builder /install /usr/local
# Copy only the application code.
COPY app/ ./app/

# Run as a non-root user for security (Docker module, Day 7).
RUN useradd --create-home appuser
USER appuser

EXPOSE 5000

# gunicorn is a production-grade server; "app.main:app" means module app/main.py, variable "app".
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app.main:app"]
