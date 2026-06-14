# 02-ci/app/Dockerfile

# ─── Stage 1: Build ───────────────────────────────────────────────
# Use an official Node.js image as the base
FROM node:20-alpine AS builder

# Set working directory inside the container
WORKDIR /app

# Copy package files first (for Docker layer caching)
# Docker caches layers — if package.json hasn't changed,
# it reuses the cached npm install layer
COPY package*.json ./

# Install ONLY production dependencies
RUN npm ci --only=production

# Copy the rest of the application code
COPY src/ ./src/

# ─── Stage 2: Production Image ────────────────────────────────────
# Use a minimal image for the final stage (smaller and more secure)
FROM node:20-alpine AS production

WORKDIR /app

# Copy only what we need from the builder stage
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/src ./src
COPY package.json .

# Create a non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

# Expose the port the app runs on
EXPOSE 3000

# Health check — Docker will use this to know if the container is healthy
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:3000/health || exit 1

# Start the application
CMD ["node", "src/index.js"]
