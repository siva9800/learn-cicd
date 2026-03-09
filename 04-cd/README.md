# Module 4 — Continuous Deployment

## Table of Contents

1. [CD Overview](#1-cd-overview)
2. [Docker — Build and Push Images](#2-docker--build-and-push-images)
3. [Deploying to Cloud Platforms](#3-deploying-to-cloud-platforms)
4. [Versioning and Tagging](#4-versioning-and-tagging)
5. [Rollback Strategies](#5-rollback-strategies)
6. [Deployment Verification](#6-deployment-verification)
7. [Lab — End-to-End Deploy Pipeline](#lab--end-to-end-deploy-pipeline)

---

## 1. CD Overview

### What Happens After CI Passes?

CI verifies code quality. CD takes the verified code and gets it running somewhere. The full flow:

```
Code merged to main
        ↓
CI pipeline runs (tests, lint, security)
        ↓
All CI jobs pass
        ↓
CD pipeline starts
        ↓
┌─────────────────────────────────────────────┐
│              CD PIPELINE                    │
│                                             │
│  1. Build Docker image                      │
│  2. Push to container registry              │
│  3. Deploy to staging                       │
│  4. Run smoke tests on staging              │
│  5. [APPROVAL GATE]                         │
│  6. Deploy to production                    │
│  7. Verify deployment health                │
│  8. Notify team (Slack/email)               │
└─────────────────────────────────────────────┘
```

### Deployment Strategies Overview

| Strategy | Description | Downtime | Risk |
|---|---|---|---|
| **Recreate** | Stop old, start new | Yes | High |
| **Rolling** | Replace instances one by one | No | Medium |
| **Blue/Green** | Two identical environments, switch traffic | No | Low |
| **Canary** | Route small % of traffic to new version | No | Very Low |

Most beginners use Rolling or Blue/Green. The platform you deploy to usually handles the strategy.

---

## 2. Docker — Build and Push Images

### Why Docker in CI/CD?

Docker containers solve the "works on my machine" problem. A Docker image contains:
- Your application code
- The runtime (Node.js, Python, etc.) at the exact version you tested with
- All dependencies
- Configuration

The same image runs identically in CI, staging, and production.

### The Dockerfile

Before we can build in CI, we need a `Dockerfile`:

```dockerfile
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
```

### `.dockerignore`

Like `.gitignore` but for Docker — prevents unnecessary files from being sent to Docker daemon:

```
node_modules
.git
.github
coverage
*.md
.env
.env.*
tests/
*.test.js
```

### Building Docker Images in GitHub Actions

```yaml
# .github/workflows/docker.yml
name: Build and Push Docker Image

on:
  push:
    branches: [develop, main, 'release/**']  # GitFlow: build on all integration branches
    tags: ['v*.*.*']                         # also build on version tags

jobs:
  docker:
    name: Build & Push
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write    # needed to push to GitHub Container Registry

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      # ── Set up Docker Buildx ────────────────────────────────────
      # Buildx is an extended Docker build tool with better caching
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      # ── Login to GitHub Container Registry ──────────────────────
      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}   # built-in, no setup needed!

      # ── Generate image metadata and tags ────────────────────────
      - name: Extract metadata for Docker
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=sha,prefix=sha-
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}
          # This generates tags like:
          #   ghcr.io/org/repo:main
          #   ghcr.io/org/repo:sha-abc1234
          #   ghcr.io/org/repo:latest

      # ── Build and push the image ─────────────────────────────────
      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .               # build context (where Dockerfile is)
          push: true               # actually push (set false to just build)
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha    # use GitHub Actions cache for Docker layers
          cache-to: type=gha,mode=max
```

### Docker Registries

| Registry | URL | Best For |
|---|---|---|
| **GitHub Container Registry (GHCR)** | `ghcr.io` | GitHub projects (free with repos) |
| **Docker Hub** | `docker.io` | Public images |
| **Amazon ECR** | `{account}.dkr.ecr.{region}.amazonaws.com` | AWS deployments |
| **Google Artifact Registry** | `{region}-docker.pkg.dev` | GCP deployments |
| **Azure Container Registry** | `{name}.azurecr.io` | Azure deployments |

### Multi-Platform Images

Build for both AMD64 and ARM64 (for Apple Silicon Macs and AWS Graviton):

```yaml
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build multi-platform image
        uses: docker/build-push-action@v5
        with:
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ghcr.io/${{ github.repository }}:latest
```

---

## 3. Deploying to Cloud Platforms

### Deploy to AWS

#### Option A: Deploy to ECS (Elastic Container Service)

```yaml
  deploy-aws:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      # Authenticate via OIDC (no stored credentials)
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      # Login to ECR (AWS's container registry)
      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      # Build and push to ECR
      - name: Build and push to ECR
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: my-app
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG

      # Update ECS service to use new image
      - name: Deploy to ECS
        run: |
          aws ecs update-service \
            --cluster my-cluster \
            --service my-service \
            --force-new-deployment \
            --region us-east-1
```

#### Option B: Deploy to EC2 via SSH

```yaml
      - name: Deploy to EC2
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ubuntu
          key: ${{ secrets.EC2_PRIVATE_KEY }}
          script: |
            cd /opt/myapp
            docker pull ghcr.io/${{ github.repository }}:latest
            docker-compose up -d
            docker system prune -f
```

#### Option C: Deploy static site to S3 + CloudFront

```yaml
      - name: Build static site
        run: npm run build

      - name: Deploy to S3
        run: |
          aws s3 sync dist/ s3://${{ secrets.S3_BUCKET }}/ \
            --delete \
            --cache-control "public, max-age=31536000" \
            --exclude "*.html"
          aws s3 sync dist/ s3://${{ secrets.S3_BUCKET }}/ \
            --delete \
            --cache-control "no-cache" \
            --include "*.html"

      - name: Invalidate CloudFront cache
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} \
            --paths "/*"
```

---

### Deploy to Azure

#### Azure Web App (App Service)

```yaml
      - name: Login to Azure
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy to Azure Web App
        uses: azure/webapps-deploy@v3
        with:
          app-name: my-app-name
          images: ghcr.io/${{ github.repository }}:${{ github.sha }}
```

---

### Deploy to GCP (Cloud Run)

```yaml
      - name: Google Auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

      - name: Deploy to Cloud Run
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: my-service
          region: us-central1
          image: gcr.io/${{ secrets.GCP_PROJECT }}/my-app:${{ github.sha }}
```

---

### Deploy to Simpler Platforms (No Cloud Account Needed for Practice)

#### Render.com

Render auto-deploys from GitHub. Just connect your repo in the Render dashboard and every push to `main` triggers a deploy. You can also trigger via API:

```yaml
      - name: Trigger Render deploy
        run: |
          curl -X POST \
            -H "Authorization: Bearer ${{ secrets.RENDER_API_KEY }}" \
            "https://api.render.com/v1/services/${{ secrets.RENDER_SERVICE_ID }}/deploys" \
            -H "Content-Type: application/json" \
            -d '{}'
```

#### Railway

```yaml
      - name: Deploy to Railway
        run: npx @railway/cli up --service ${{ secrets.RAILWAY_SERVICE }}
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

#### Heroku

```yaml
      - name: Deploy to Heroku
        uses: akhileshns/heroku-deploy@v3.13.15
        with:
          heroku_api_key: ${{ secrets.HEROKU_API_KEY }}
          heroku_app_name: my-app-name
          heroku_email: my@email.com
```

---

## 4. Versioning and Tagging

### Semantic Versioning

**SemVer** format: `MAJOR.MINOR.PATCH` (e.g., `2.4.1`)

| Part | When to increment | Example |
|---|---|---|
| MAJOR | Breaking changes | API changed, not backwards compatible |
| MINOR | New features, backwards compatible | Added new endpoint |
| PATCH | Bug fixes, backwards compatible | Fixed login bug |

### Tagging Releases in CI

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*.*.*'     # trigger on tags like v1.0.0, v2.3.1

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write    # needed to create GitHub Release

    steps:
      - uses: actions/checkout@v4

      - name: Build
        run: npm run build

      - name: Create GitHub Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref_name }}
          release_name: Release ${{ github.ref_name }}
          body: |
            ## Changes in ${{ github.ref_name }}
            - See CHANGELOG.md for details
          draft: false
          prerelease: false
```

### Auto-Versioning with Conventional Commits

If your team uses conventional commits (`feat: add login`, `fix: resolve bug`), you can auto-generate version numbers and changelogs:

```yaml
      - name: Semantic Release
        uses: cycjimmy/semantic-release-action@v4
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

This automatically:
- Determines the next version based on commit messages
- Creates a git tag
- Generates a changelog
- Creates a GitHub Release

### Using Git SHA as Image Tag

For Docker images, the commit SHA is a reliable, unique, immutable tag:

```yaml
env:
  IMAGE_TAG: ${{ github.sha }}    # e.g., abc1234def5678...

# Short SHA (more readable):
  IMAGE_TAG: ${{ github.sha | head -c 7 }}
```

---

## 5. Rollback Strategies

### What is a Rollback?

A rollback undoes a bad deployment and returns to a known-good state. Having a fast rollback strategy is essential — even with good CI, things go wrong in production.

### Strategy 1 — Re-Deploy Previous Image

The simplest approach: keep the previous Docker image tag and redeploy it.

```yaml
# .github/workflows/rollback.yml
name: Rollback

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: 'Docker image tag to roll back to (e.g., sha-abc1234)'
        required: true
        type: string
      reason:
        description: 'Reason for rollback'
        required: true
        type: string

jobs:
  rollback:
    name: Rollback Production
    runs-on: ubuntu-latest
    environment: production    # requires approval

    steps:
      - uses: actions/checkout@v4

      - name: Log rollback initiation
        run: |
          echo "==================================="
          echo "  ROLLBACK INITIATED"
          echo "==================================="
          echo "Rolled back by: ${{ github.actor }}"
          echo "Target tag: ${{ inputs.image_tag }}"
          echo "Reason: ${{ inputs.reason }}"
          echo "Time: $(date -u)"
          echo "==================================="

      - name: Deploy previous version
        run: |
          # Update your deployment to use the previous image tag
          # Example for ECS:
          aws ecs update-service \
            --cluster my-cluster \
            --service my-service \
            --task-definition my-app:${{ inputs.image_tag }} \
            --force-new-deployment

      - name: Notify team
        run: |
          # Send Slack notification, etc.
          echo "Rollback complete!"
```

### Strategy 2 — Git Revert

Revert the bad commit and let the CD pipeline re-deploy:

```bash
# Locally:
git revert HEAD          # creates a new commit that undoes the last commit
git push origin main     # triggers CI/CD which deploys the reverted state
```

### Strategy 3 — Blue/Green Swap

If you use blue/green deployment:
```
Blue (old version running) → Green (new version just deployed)
                               ↑ something went wrong
           ← swap traffic back to Blue (instant rollback)
```

```yaml
      - name: Switch traffic back to blue
        run: |
          aws elbv2 modify-listener \
            --listener-arn ${{ secrets.ALB_LISTENER_ARN }} \
            --default-actions Type=forward,TargetGroupArn=${{ secrets.BLUE_TARGET_GROUP_ARN }}
```

### Strategy 4 — Feature Flags

Use feature flags to disable a bad feature without a deployment:

```javascript
// In your app code
if (featureFlags.isEnabled('new-checkout-flow')) {
  return newCheckout();
} else {
  return oldCheckout();
}
```

Flip the flag in your feature flag system (LaunchDarkly, Flagsmith, etc.) → users instantly get the old behavior. No deployment needed.

---

## 6. Deployment Verification

### Smoke Tests

After deploying, automatically verify the app is working:

```yaml
      - name: Wait for deployment to stabilize
        run: sleep 30   # give the app time to start

      - name: Run smoke tests
        run: |
          # Check health endpoint
          response=$(curl -s -o /dev/null -w "%{http_code}" https://myapp.com/health)
          if [ "$response" != "200" ]; then
            echo "Health check failed! Got $response"
            exit 1
          fi
          echo "Health check passed!"

          # Check critical API endpoint
          curl -f https://myapp.com/api/v1/status || exit 1

      - name: Rollback on failure
        if: failure()
        run: |
          echo "Smoke tests failed — rolling back!"
          # Trigger rollback workflow
          gh workflow run rollback.yml \
            -f image_tag=sha-${{ env.PREVIOUS_SHA }} \
            -f reason="Automated rollback: smoke tests failed"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Monitoring Integration

```yaml
      - name: Create deployment marker in Datadog
        run: |
          curl -X POST "https://api.datadoghq.com/api/v1/events" \
            -H "Content-Type: application/json" \
            -H "DD-API-KEY: ${{ secrets.DATADOG_API_KEY }}" \
            -d '{
              "title": "Deployment to production",
              "text": "Deployed ${{ github.sha }} by ${{ github.actor }}",
              "tags": ["deployment", "github-actions"]
            }'
```

---

## Lab — End-to-End Deploy Pipeline

### Objective

Build a complete CD pipeline that:
1. Builds a Docker image on every merge to `main`
2. Pushes to GitHub Container Registry
3. Deploys to staging automatically
4. Requires approval before production
5. Runs smoke tests after each deployment
6. Tags the release

### The Complete Pipeline

```yaml
# .github/workflows/cd.yml
name: CD — Deploy
# GitFlow CD mapping:
#   develop branch push  → build image → deploy to staging (automatic)
#   version tag (v*.*.*)  → build image → deploy to production (with approval)

on:
  push:
    branches: [develop]      # staging deploys from develop
    tags: ['v*.*.*']         # production deploys from version tags
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # ─── Job 1: Build and Push Docker Image ─────────────────────────
  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    outputs:
      image-tag: ${{ steps.meta.outputs.version }}    # pass tag to later jobs

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ─── Job 2: Deploy to Staging ────────────────────────────────────
  # GitFlow: runs on every push to 'develop'
  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: build
    if: startsWith(github.ref, 'refs/heads/')   # branch pushes only (not tags)
    environment:
      name: staging
      url: https://staging.myapp.com

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Deploy image to staging
        run: |
          echo "Deploying ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.build.outputs.image-tag }}"
          # SSH to server and pull new image:
          # ssh ${{ secrets.STAGING_HOST }} "docker pull ... && docker-compose up -d"

      - name: Smoke test staging
        run: |
          echo "Testing https://staging.myapp.com/health"
          # curl -f https://staging.myapp.com/health

  # ─── Job 3: Deploy to Production (gated) ────────────────────────
  # GitFlow: runs only on version tag pushes (v*.*.*)
  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: build
    if: startsWith(github.ref, 'refs/tags/')    # tag pushes only
    environment:
      name: production
      url: https://myapp.com

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Deploy image to production
        run: |
          echo "Deploying ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.build.outputs.image-tag }} to PRODUCTION"

      - name: Smoke test production
        run: |
          echo "Testing https://myapp.com/health"

      - name: Tag release
        run: |
          DATE=$(date +%Y%m%d-%H%M%S)
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git tag "release-${DATE}" -m "Production deployment by ${{ github.actor }}"
          git push origin --tags
```

---

## Summary

| Concept | Key Point |
|---|---|
| Docker | Same image = same behavior everywhere |
| Multi-stage builds | Keep production images small and secure |
| GHCR | Free Docker registry built into GitHub |
| SHA as image tag | Immutable, traceable, maps to exact commit |
| Rollback | Always plan for "how do I undo this?" |
| Smoke tests | Verify the app works after every deploy |
| Blue/green | Switch traffic instantly for zero-downtime |

---

Next: [Module 5 — Advanced GitHub Actions](../05-advanced/README.md)
