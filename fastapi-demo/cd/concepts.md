# CD Concepts - GitHub Actions in Detail

> A complete reference for **every CD concept** in the demo, each explained AND shown **where it appears in our real [`cd.yml`](cd.yml)**. Read [README.md](README.md) to *run/enable* CD; read this to *understand* it. CD reuses the GitHub Actions basics from [../ci/concepts.md](../ci/concepts.md) (jobs, steps, contexts, permissions) - this page focuses on what is specific to shipping.

Contents:
1. [What CD is (and the CI handoff)](#1-what-cd-is-and-the-ci-handoff)
2. [Gating CD on CI with `workflow_run`](#2-gating-cd-on-ci-with-workflow_run)
3. [Building and pushing the image](#3-building-and-pushing-the-image)
4. [Container registries and image tagging](#4-container-registries-and-image-tagging)
5. [Secrets](#5-secrets)
6. [Permissions and keyless auth (OIDC)](#6-permissions-and-keyless-auth-oidc)
7. [Environments and approval gates](#7-environments-and-approval-gates)
8. [Deploying to Kubernetes](#8-deploying-to-kubernetes)
9. [Deployment strategies](#9-deployment-strategies)
10. [Smoke tests and verification](#10-smoke-tests-and-verification)
11. [Rollback](#11-rollback)
12. [Concurrency for deploys](#12-concurrency-for-deploys)
13. [Every concept, mapped to our cd.yml](#every-concept-mapped-to-our-cdyml)

---

## 1. What CD is (and the CI handoff)

**CI** ends at a tested, packaged **artifact**. **CD** takes that artifact and **ships it**: build+push the image, then deploy it. The artifact (a Docker image, tagged by commit SHA) is the handoff point.

```
CI: lint + test + build-check   ->   [image]   ->   CD: build+push + deploy
```

The golden rule CD must honour: **only a CI-verified commit is ever deployed.** Section 2 is how we enforce that.

---

## 2. Gating CD on CI with `workflow_run`

Our CI and CD are **separate workflows**. To make CD run only after CI passes, we trigger it with `workflow_run`:

```yaml
on:
  workflow_run:
    workflows: ["CI (fastapi-demo)"]   # the CI workflow's name
    types: [completed]
    branches: [main]

jobs:
  build-push:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}   # only if CI passed
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.workflow_run.head_sha }}   # the EXACT commit CI tested
```

- `workflow_run` fires when the named workflow **finishes** on `main`.
- The `if: ...conclusion == 'success'` check drops the run if CI **failed** (workflow_run fires on failure too).
- `github.event.workflow_run.head_sha` is the commit CI tested - we check that out so CD ships exactly what was verified.

> **Alternative:** a single workflow doing `test -> build -> deploy` with `needs:` also gates CD on CI (simpler, one file). Separate workflows + `workflow_run` is the pattern when CI and CD are owned/triggered independently.

---

## 3. Building and pushing the image

The image is the deployable artifact. The standard Docker actions:

```yaml
- uses: docker/setup-buildx-action@v3        # enable Buildx (better builds + caching)
- uses: docker/login-action@v3               # log in to the registry
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}     # built-in token, no setup
- uses: docker/build-push-action@v6
  with:
    context: fastapi-demo                     # folder with the Dockerfile
    push: true                                # actually publish (false = build only)
    tags: |
      ghcr.io/${{ github.repository }}/fastapi-demo:${{ github.event.workflow_run.head_sha }}
      ghcr.io/${{ github.repository }}/fastapi-demo:latest
```

- **Buildx** gives layer caching (`cache-from: type=gha`, `cache-to: type=gha,mode=max`) and multi-platform builds (`platforms: linux/amd64,linux/arm64`).
- `push: true` publishes; `push: false` just verifies the build (that is what CI does).

---

## 4. Container registries and image tagging

A **registry** stores images. Options: **GHCR** (`ghcr.io`, built into GitHub - what we use), Docker Hub, Amazon ECR, etc.

**Tagging strategy matters.** Never deploy `:latest` alone - you cannot tell which version is running or roll back precisely. Tag with the **immutable commit SHA**, and optionally a moving `:latest`:

```
ghcr.io/owner/repo/fastapi-demo:<full-sha>   # immutable, exact - deploy THIS
ghcr.io/owner/repo/fastapi-demo:latest        # convenience pointer
```

`docker/metadata-action@v5` can auto-generate tags (branch, `sha-` prefix, semver from git tags):

```yaml
- uses: docker/metadata-action@v5
  with:
    images: ghcr.io/${{ github.repository }}
    tags: |
      type=sha
      type=ref,event=branch
      type=semver,pattern={{version}}
```

> **In our `cd.yml`:** we push two tags - the exact `head_sha` and `latest` - to GHCR.

---

## 5. Secrets

Secrets are encrypted values (tokens, kubeconfigs, keys) you never put in the YAML. Read them with `${{ secrets.NAME }}`; GitHub **masks** them in logs.

- **Repository / organization / environment** secrets (environment secrets are scoped to a deploy environment - Section 7).
- **`GITHUB_TOKEN`** is provided automatically (no setup) and is enough to push to GHCR.
- **Never `echo` a secret** - even a slice may not be masked.

```yaml
env:
  KUBECONFIG_DATA: ${{ secrets.KUBECONFIG_DATA }}   # a base64 kubeconfig we add
```

> **In our `cd.yml`:** `GITHUB_TOKEN` (built in) pushes the image; `KUBECONFIG_DATA` (you add it) enables the k8s deploy. If it is unset, the deploy job skips cleanly instead of failing.

---

## 6. Permissions and keyless auth (OIDC)

CD needs more power than CI, so it widens the token - least privilege still applies:

```yaml
permissions:
  contents: read
  packages: write      # push to GHCR
  id-token: write      # only if using OIDC (below)
```

**OIDC (keyless auth)** is the modern way to reach a cloud (AWS/Azure/GCP) with **no long-lived secret**: the workflow presents a short-lived identity token the cloud trusts.

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::111122223333:role/gha-deployer
    aws-region: ap-south-1
# then: aws eks update-kubeconfig ...
```

> Our demo keeps CD **generic** (a `KUBECONFIG_DATA` secret, works on any cluster). For a real EKS setup you would swap that for OIDC + `aws eks update-kubeconfig` + an EKS access entry - no kubeconfig stored anywhere.

---

## 7. Environments and approval gates

An **environment** (`Settings -> Environments`) is a named deploy target (staging, production) with **protection rules**:

```yaml
jobs:
  deploy-prod:
    environment: production    # attaches the environment's rules + secrets
    steps: [...]
```

- **Required reviewers** - the job **pauses for a human to approve** before it runs (the approval gate).
- **Wait timer** - a delay before deploy.
- **Environment secrets/variables** - values scoped to just that environment (so prod creds are only available to the prod job).

This is how you make production deploys manual/gated while staging stays automatic.

---

## 8. Deploying to Kubernetes

The deploy step needs cluster credentials, then updates the running Deployment:

```yaml
- name: Configure kubectl
  run: |
    echo "$KUBECONFIG_DATA" | base64 -d > "$RUNNER_TEMP/kubeconfig"
    echo "KUBECONFIG=$RUNNER_TEMP/kubeconfig" >> "$GITHUB_ENV"   # point kubectl at it
- name: Deploy (rolling update)
  run: |
    kubectl set image deployment/fastapi-demo fastapi-demo="$IMAGE" -n "$NS"
    kubectl rollout status deployment/fastapi-demo -n "$NS"       # wait + fail if it stalls
```

- `kubectl` is pre-installed on Ubuntu runners.
- `kubectl set image` triggers a **rolling update** of the Deployment (Kubernetes replaces pods gradually - zero downtime).
- `kubectl rollout status` **waits** for the rollout and **fails the job** if it does not become healthy - so a bad deploy turns the pipeline red.

> **In our `cd.yml`:** the `deploy` job decodes `KUBECONFIG_DATA`, sets the new image (tagged by the tested SHA), and waits on the rollout. It **skips cleanly** if the secret is not set.

---

## 9. Deployment strategies

How new pods replace old ones:

| Strategy | How | Downtime | Rollback |
|----------|-----|----------|----------|
| **Recreate** | Stop all old, start all new | Yes | Redeploy old |
| **Rolling** (default) | Replace pods a few at a time | No | `rollout undo` |
| **Blue/Green** | Run new (green) beside old (blue), switch traffic | No | Flip traffic back |
| **Canary** | Send a small % of traffic to new, watch, then ramp | No | Route back to old |

Our demo uses **Rolling** (via `kubectl set image` on a 2-replica Deployment). Blue/green and canary are usually done with a Service mesh, an Ingress controller, or a tool like Argo Rollouts / Flagger.

---

## 10. Smoke tests and verification

After deploying, **prove the new version actually responds** before calling it done:

```yaml
- name: Smoke test
  run: curl -f https://<host>/health || exit 1   # -f makes curl fail on non-200
```

A smoke test is a tiny "is it alive?" check (hit `/health`, the critical path). If it fails, the job fails - pair it with a rollback step (Section 11). Kubernetes **readiness/liveness probes** (in `k8s/deployment.yaml`) do continuous health checking; the smoke test is the one-time post-deploy confirmation.

---

## 11. Rollback

When a deploy goes bad:

```bash
kubectl rollout undo deployment/fastapi-demo -n <ns>   # instant: back to the previous ReplicaSet
```

Other options: re-run CD pinned to the previous good commit SHA (the image tag), or `git revert` the bad commit and let the pipeline redeploy the corrected state. Because we tag images by **SHA**, every past version is still pullable - rollback is just "deploy the old tag."

---

## 12. Concurrency for deploys

Two deploys racing to the same environment is a real hazard. Guard it:

```yaml
concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false    # let an in-flight deploy FINISH (do not kill mid-rollout)
```

Note: for deploys use `cancel-in-progress: false` (unlike CI, where cancelling an old run is fine).

---

## Every concept, mapped to our cd.yml

| Concept | Where it is in [`cd.yml`](cd.yml) |
|---------|-----------------------------------|
| CI gates CD | `on: workflow_run` + `if: conclusion == 'success'` |
| Ship the tested commit | `checkout` with `ref: workflow_run.head_sha` |
| Build + push image | `docker/login-action` + `docker/build-push-action@v6`, `push: true` |
| Registry + tagging | GHCR, tags `:<sha>` and `:latest` |
| Permissions | `packages: write` for GHCR |
| Secrets | `secrets.GITHUB_TOKEN` (push), `secrets.KUBECONFIG_DATA` (deploy) |
| Deploy to k8s | decode kubeconfig, `kubectl set image` + `rollout status` |
| Graceful skip | deploy steps gated on `env.KUBECONFIG_DATA != ''` |

---

**See also:** [README.md](README.md) (enable CD) - [CI concepts](../ci/concepts.md) (the build/test side).
