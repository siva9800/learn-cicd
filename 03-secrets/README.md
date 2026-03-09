# Module 3 — Secrets, Environments & Security

## Table of Contents

1. [Why Secrets Matter](#1-why-secrets-matter)
2. [GitHub Secrets](#2-github-secrets)
3. [Environments](#3-environments)
4. [Approval Gates](#4-approval-gates)
5. [Environment-Specific Secrets](#5-environment-specific-secrets)
6. [OIDC — Keyless Authentication](#6-oidc--keyless-authentication)
7. [Permissions & Least Privilege](#7-permissions--least-privilege)
8. [Security Best Practices](#8-security-best-practices)
9. [Lab — Deploy with Secrets and Approval Gate](#lab--deploy-with-secrets-and-approval-gate)

---

## 1. Why Secrets Matter

A **secret** is any sensitive value that must not be exposed publicly:
- API keys (Stripe, SendGrid, OpenAI)
- Cloud credentials (AWS_ACCESS_KEY_ID, AZURE_CLIENT_SECRET)
- Database connection strings
- SSH private keys
- JWT signing keys
- Passwords

### The Wrong Way (Never Do This)

```yaml
# WRONG — hardcoded secret in workflow file
- run: aws s3 cp dist/ s3://my-bucket/ --region us-east-1
  env:
    AWS_ACCESS_KEY_ID: AKIAIOSFODNN7EXAMPLE    # ← PUBLIC! Anyone can see this!
    AWS_SECRET_ACCESS_KEY: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**Why is this terrible?**
- The `.github/workflows/*.yml` files are committed to git
- Git history is permanent — even if you delete the file, the secret is in history
- Public repos expose this to everyone on the internet
- GitHub will warn you and secret scanning tools will flag it

### The Right Way

```yaml
# CORRECT — secrets are stored in GitHub, referenced by name
- run: aws s3 cp dist/ s3://my-bucket/
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

---

## 2. GitHub Secrets

### Types of Secrets

GitHub has three scopes for secrets:

| Scope | Where Defined | Available To |
|---|---|---|
| **Repository secrets** | Repo → Settings → Secrets | All workflows in that repo |
| **Environment secrets** | Repo → Settings → Environments | Workflows using that environment |
| **Organization secrets** | Org → Settings → Secrets | All repos in the org (configurable) |

### Creating a Repository Secret

**Via GitHub UI:**
1. Go to your repo on GitHub
2. Click **Settings** (top menu)
3. Click **Secrets and variables** → **Actions** (left sidebar)
4. Click **New repository secret**
5. Enter a name (e.g., `DATABASE_URL`) and value
6. Click **Add secret**

**Via GitHub CLI:**
```bash
gh secret set DATABASE_URL --body "postgres://user:password@host:5432/db"

# From a file
gh secret set PRIVATE_KEY < private_key.pem

# List secrets (shows names only, not values)
gh secret list
```

### Using Secrets in Workflows

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy with secrets
        run: ./deploy.sh
        env:
          # Reference secrets with ${{ secrets.SECRET_NAME }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          API_KEY: ${{ secrets.STRIPE_API_KEY }}
          PRIVATE_KEY: ${{ secrets.SSH_PRIVATE_KEY }}

      # You can also pass secrets directly as CLI arguments
      - name: Authenticate with registry
        run: |
          echo "${{ secrets.DOCKER_PASSWORD }}" | docker login \
            --username ${{ secrets.DOCKER_USERNAME }} \
            --password-stdin
```

### How GitHub Protects Secrets

1. **Encrypted at rest** — secrets are encrypted using libsodium before storage
2. **Masked in logs** — GitHub automatically redacts secret values from log output. If a secret appears in a log, it shows as `***`
3. **Not passed to fork PRs** — workflows triggered by PRs from forks do NOT have access to secrets (security feature)
4. **Not available via API** — you can create/update secrets via API but never read them

### The Masking Behavior

```yaml
- run: |
    echo "My secret is: ${{ secrets.MY_SECRET }}"
    # Output in GitHub logs:
    # My secret is: ***
```

**Important limitation:** If your secret value appears inside a larger string and GitHub can't detect it, it might not be masked. Keep secrets as complete, opaque values.

### Built-In GITHUB_TOKEN Secret

GitHub automatically creates a **`GITHUB_TOKEN`** for every workflow run. This token has permissions to interact with the GitHub API (create issues, comment on PRs, push to the repo, etc.).

```yaml
- name: Comment on PR
  uses: actions/github-script@v7
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}   # always available
    script: |
      github.rest.issues.createComment({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        body: 'Deployment complete!'
      })
```

The `GITHUB_TOKEN` is scoped to the current repository and expires when the workflow run ends.

---

## 3. Environments

### What is an Environment?

A GitHub **Environment** is a named deployment target — like `staging`, `production`, `preview`. Environments let you:
- Require manual approval before deploying
- Define environment-specific secrets
- Specify which branches can deploy to the environment
- Track deployment history

### Creating an Environment

1. Repo → Settings → Environments
2. Click **New environment**
3. Name it (e.g., `production`)
4. Configure protection rules

### Using Environments in Workflows

```yaml
jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging    # ← uses the "staging" environment

    steps:
      - run: echo "Deploying to staging"
      - run: ./deploy.sh
        env:
          # Gets secrets from the "staging" environment
          DATABASE_URL: ${{ secrets.DATABASE_URL }}

  deploy-production:
    runs-on: ubuntu-latest
    environment: production    # ← uses the "production" environment
    needs: deploy-staging      # must run after staging

    steps:
      - run: echo "Deploying to production"
```

### Environment URL

You can set a URL for the environment, which GitHub displays on the Actions and Deployments pages:

```yaml
jobs:
  deploy:
    environment:
      name: staging
      url: https://staging.myapp.com   # shown as a link in GitHub UI
```

---

## 4. Approval Gates

### What is an Approval Gate?

An approval gate **pauses the workflow** and requires a designated reviewer to approve before it continues. This is how you add a human checkpoint before production deployments.

### Setting Up Required Reviewers

1. Go to Settings → Environments → Select your environment
2. Check **"Required reviewers"**
3. Add people or teams who can approve

### How It Looks in Practice

```yaml
jobs:
  deploy-staging:
    environment: staging     # no approval required
    steps:
      - run: ./deploy.sh staging

  # This job PAUSES and sends a notification to reviewers
  deploy-production:
    environment: production  # has approval gate configured
    needs: deploy-staging
    steps:
      - run: ./deploy.sh production
```

**What happens:**
1. `deploy-staging` runs and completes
2. `deploy-production` starts — but immediately pauses
3. GitHub sends email/notification to required reviewers
4. Reviewer sees the workflow, clicks "Review deployments", approves
5. The workflow resumes and runs the production deployment

**If rejected:**
- The workflow is cancelled
- The team is notified

### Wait Timer

You can also add a mandatory wait before deployment (e.g., give staging time to soak):

```yaml
# In Environment settings:
# Wait timer: 10 minutes
# This adds an automatic delay even after approval
```

### Deployment Branches

Restrict which branches can deploy to an environment:

```yaml
# In Environment settings:
# Deployment branches: Selected branches
# Pattern: main
# Only the 'main' branch can deploy to production
```

---

## 5. Environment-Specific Secrets

The same secret name can have different values per environment. For example, `DATABASE_URL` in staging points to the staging database, while in production it points to the production database.

```yaml
# No need to change your workflow — environment secrets override repo secrets
jobs:
  deploy-staging:
    environment: staging        # picks up staging DATABASE_URL
    steps:
      - run: ./deploy.sh
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}   # staging value

  deploy-production:
    environment: production     # picks up production DATABASE_URL
    steps:
      - run: ./deploy.sh
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}   # production value (different!)
```

**Priority order (highest to lowest):**
1. Environment secrets
2. Repository secrets
3. Organization secrets

---

## 6. OIDC — Keyless Authentication

### The Problem with Static Credentials

Traditional approach: create a cloud IAM user, generate long-lived access keys, store in GitHub Secrets.

**Problems:**
- Keys never expire (huge security risk if leaked)
- Keys have to be rotated manually
- Every rotation requires updating GitHub Secrets
- One compromised key = full access until discovered

### What is OIDC?

**OpenID Connect (OIDC)** allows GitHub Actions to authenticate with cloud providers (AWS, GCP, Azure) **without storing any long-lived credentials**. Instead:

1. GitHub generates a **short-lived JWT token** for each workflow run
2. The cloud provider validates the token directly with GitHub
3. The cloud provider grants temporary credentials that expire when the job ends

```
GitHub Actions → "I am run #1234 on repo org/myapp, branch main"
      ↓
AWS (verifies with GitHub's OIDC endpoint)
      ↓
AWS → "OK, I trust GitHub. Here are 1-hour credentials for role X"
      ↓
Workflow uses credentials, they expire when job ends
```

### AWS OIDC Setup

**Step 1: Configure AWS (one-time, done in AWS console or Terraform)**
1. Create an IAM Identity Provider in AWS (type: OpenID Connect)
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`
2. Create an IAM Role with the trust policy:
```json
{
  "Effect": "Allow",
  "Principal": {
    "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
    },
    "StringLike": {
      "token.actions.githubusercontent.com:sub": "repo:myorg/myrepo:*"
    }
  }
}
```

**Step 2: Use in workflow (NO secrets needed!)**
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write    # REQUIRED: allows GitHub to request OIDC token
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/github-actions-role
          aws-region: us-east-1
          # No access key or secret needed!

      - name: Deploy to S3
        run: aws s3 sync dist/ s3://my-bucket/
```

### Azure OIDC Setup

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - name: Azure login via OIDC
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}       # Not a secret, just an ID
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}       # Not a secret, just an ID
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          # No client secret! OIDC handles auth
```

### GCP OIDC Setup

```yaml
      - name: GCP auth via OIDC
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: 'projects/123/locations/global/workloadIdentityPools/my-pool/providers/my-provider'
          service_account: 'my-service-account@my-project.iam.gserviceaccount.com'
```

---

## 7. Permissions & Least Privilege

### Default Permissions

By default, `GITHUB_TOKEN` has read/write permissions on most things. You should restrict this:

**In workflow file:**
```yaml
# Restrict the whole workflow
permissions:
  contents: read          # can read repo files
  pull-requests: write    # can comment on PRs
  # Everything else: none

jobs:
  test:
    # Override for a specific job
    permissions:
      contents: read
    steps: [...]
```

**Permission options:**
```yaml
permissions:
  actions: read | write | none
  checks: read | write | none
  contents: read | write | none
  deployments: read | write | none
  id-token: write | none          # needed for OIDC
  issues: read | write | none
  packages: read | write | none
  pages: read | write | none
  pull-requests: read | write | none
  repository-projects: read | write | none
  security-events: read | write | none
  statuses: read | write | none
```

**Set defaults at repo level:**
Settings → Actions → General → Workflow permissions → "Read repository contents and packages permissions"

### Principle of Least Privilege

Grant only the minimum permissions needed for each job:

```yaml
jobs:
  test:
    permissions:
      contents: read        # just needs to read code
    steps: [...]

  comment-on-pr:
    permissions:
      pull-requests: write  # needs to post comments
      contents: read        # needs to read code
    steps: [...]

  deploy:
    permissions:
      id-token: write       # OIDC auth
      contents: read        # read code
    steps: [...]
```

---

## 8. Security Best Practices

### 1. Pin Action Versions to Commit SHAs

```yaml
# RISKY — a new v4 release could break your workflow or be malicious
- uses: actions/checkout@v4

# SAFER — pin to an exact commit SHA
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
```

Use a tool like Dependabot to keep action versions up to date safely.

### 2. Never Echo Secrets

```yaml
# WRONG — even though GitHub masks it, don't do this
- run: echo "Token is ${{ secrets.MY_TOKEN }}"

# RIGHT — pass secrets via environment variables
- run: ./script.sh
  env:
    MY_TOKEN: ${{ secrets.MY_TOKEN }}
```

### 3. Validate Third-Party Actions

Before using a community action:
- Check the action's source code on GitHub
- Look at the number of stars and community trust
- Check when it was last maintained
- Prefer official actions (`actions/*`, `github/*`)

### 4. Use `pull_request_target` Carefully

`pull_request_target` runs in the context of the base branch (has access to secrets). This is dangerous with PRs from forks because the fork's code could exfiltrate your secrets.

```yaml
# DANGEROUS without careful conditions
on: pull_request_target

# SAFER — only runs if PR is not from a fork
on:
  pull_request_target:
    types: [labeled]
# Then check: if: github.event.pull_request.head.repo.full_name == github.repository
```

### 5. Audit Your Workflows Regularly

- Use GitHub's built-in **Secret Scanning** — it auto-detects secrets committed by accident
- Use **Dependabot** for action version updates
- Review workflow permissions quarterly
- Rotate secrets even when you don't think they've been compromised

### 6. Restrict `workflow_dispatch` to Specific Branches

```yaml
on:
  workflow_dispatch:

jobs:
  deploy:
    if: github.ref == 'refs/heads/main'    # only actually deploy from main
    steps:
      - run: ./deploy.sh
```

---

## Lab — Deploy with Secrets and Approval Gate

### Objective

Build a workflow that:
1. Deploys to "staging" automatically on push to `main`
2. Requires manual approval before deploying to "production"
3. Uses different secrets per environment

### Setup

**Step 1: Create environments in GitHub**
- Settings → Environments → New environment: `staging`
- Settings → Environments → New environment: `production`
  - Add yourself as a required reviewer
  - Add branch protection: only `main` can deploy

**Step 2: Add environment secrets**
- `staging` environment: Add `DEPLOY_URL` = `https://staging.example.com`
- `production` environment: Add `DEPLOY_URL` = `https://example.com`
- Both environments: Add `API_KEY` with different values

**Step 3: Create the workflow**

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [develop]          # GitFlow: develop → staging
    tags: ['v*.*.*']             # GitFlow: version tag on main → production
  workflow_dispatch:
    inputs:
      target:
        description: 'Deploy target'
        required: true
        type: choice
        options: [staging, production]

jobs:
  # ─── Deploy to Staging ──────────────────────────────────────────
  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    environment:
      name: staging
      url: ${{ secrets.DEPLOY_URL }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Deploy to staging
        run: |
          echo "Deploying to staging..."
          echo "URL: ${{ secrets.DEPLOY_URL }}"
          echo "API Key last 4 chars: ...${API_KEY: -4}"
          # Real deploy command would go here
        env:
          API_KEY: ${{ secrets.API_KEY }}

      - name: Smoke test staging
        run: |
          echo "Running smoke tests against ${{ secrets.DEPLOY_URL }}"
          # curl -f ${{ secrets.DEPLOY_URL }}/health || exit 1

  # ─── Deploy to Production (requires approval) ───────────────────
  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: deploy-staging          # must run after staging succeeds
    environment:
      name: production             # has approval gate configured
      url: ${{ secrets.DEPLOY_URL }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Deploy to production
        run: |
          echo "Deploying to production..."
          echo "URL: ${{ secrets.DEPLOY_URL }}"
          echo "Deploying commit: ${{ github.sha }}"
        env:
          API_KEY: ${{ secrets.API_KEY }}

      - name: Tag the release
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git tag -a "release-$(date +%Y%m%d-%H%M%S)" -m "Production deployment"
          git push origin --tags
```

### What You'll See

1. Push to `main`
2. `deploy-staging` job runs immediately
3. When staging passes, `deploy-production` starts — but shows "Waiting for approval"
4. GitHub sends you an email notification
5. Go to the Actions tab → click "Review deployments" → Approve
6. Production deployment runs

---

## Summary

| Concept | Key Point |
|---|---|
| Secrets | Never hardcode — always use `${{ secrets.NAME }}` |
| GITHUB_TOKEN | Auto-created, scoped to current repo and run |
| Environments | Named targets (staging, prod) with protection rules |
| Approval gates | Pause workflow until human approves |
| OIDC | No stored credentials — GitHub proves identity to cloud |
| Least privilege | Only grant permissions your job actually needs |
| Secret masking | GitHub auto-redacts secrets from logs |

---

Next: [Module 4 — Continuous Deployment](../04-cd/README.md)
