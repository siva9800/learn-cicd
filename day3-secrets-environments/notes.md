# Day 3 - Secrets, Environments & Security

> Goal: Learn how to store sensitive values safely, control where and when your code deploys, and let GitHub Actions prove its identity to cloud providers without ever holding a permanent password.

## Learning Objectives

By the end of this module you will be able to:

- Explain what a secret is and why it must never live in a workflow file or git history
- Create and use repository, environment, and organization secrets
- Define environments such as staging and production and protect them with approval gates and wait timers
- Use OIDC to authenticate to AWS, Azure, and GCP without storing long-lived credentials
- Apply the principle of least privilege to the built-in GITHUB_TOKEN
- Write the real AWS trust and permission policies a pipeline needs, and say why a build role
  and an infrastructure role must be separate
- Give a deployed workload its own cloud identity with EKS Pod Identity, instead of putting an
  access key in a Kubernetes Secret
- Recognise and avoid the most common security mistakes in CI/CD pipelines

## Table of Contents

1. [Why Secrets Matter](#1-why-secrets-matter)
2. [GitHub Secrets](#2-github-secrets)
3. [Environments](#3-environments)
4. [Approval Gates](#4-approval-gates)
5. [Environment-Specific Secrets](#5-environment-specific-secrets)
6. [OIDC - Keyless Authentication](#6-oidc---keyless-authentication)
7. [Permissions & Least Privilege](#7-permissions--least-privilege)
8. [Security Best Practices](#8-security-best-practices)
9. [AWS IAM in Practice](#9-aws-iam-in-practice)
10. [Lab - Deploy with Secrets and Approval Gate](#lab---deploy-with-secrets-and-approval-gate)

---

## 1. Why Secrets Matter

Think of a secret like the PIN for your bank card. You never write the PIN on the card itself, because anyone who picks up the card would then have everything they need. In the same way, a password or key must never be written directly into a file that travels with your code. The card (your code) and the PIN (the secret) are kept apart on purpose.

A **secret** is any sensitive value that must not be exposed publicly:
- API keys (Stripe, SendGrid, OpenAI)
- Cloud credentials (AWS_ACCESS_KEY_ID, AZURE_CLIENT_SECRET)
- Database connection strings
- SSH private keys
- JWT signing keys
- Passwords

### The Wrong Way (Never Do This)

```yaml
# WRONG - hardcoded secret in workflow file
- run: aws s3 cp dist/ s3://my-bucket/ --region us-east-1
  env:
    AWS_ACCESS_KEY_ID: AKIAIOSFODNN7EXAMPLE    # ← PUBLIC! Anyone can see this!
    AWS_SECRET_ACCESS_KEY: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**Why is this terrible?**
- The `.github/workflows/*.yml` files are committed to git
- Git history is permanent - even if you delete the file, the secret is in history
- Public repos expose this to everyone on the internet
- GitHub will warn you and secret scanning tools will flag it

### The Right Way

```yaml
# CORRECT - secrets are stored in GitHub, referenced by name
- run: aws s3 cp dist/ s3://my-bucket/
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

---

## 2. GitHub Secrets

A GitHub secret is like a key kept inside a locked safe. The workflow can ask the safe to use the key on its behalf, but it can never open the safe and read the key out loud. You hand the value to GitHub once, and from then on you only ever refer to it by name.

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

1. **Encrypted at rest** - secrets are encrypted using libsodium before storage
2. **Masked in logs** - GitHub automatically redacts secret values from log output. If a secret appears in a log, it shows as `***`
3. **Not passed to fork PRs** - workflows triggered by PRs from forks do NOT have access to secrets (security feature)
4. **Not available via API** - you can create/update secrets via API but never read them

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

An environment is like the difference between a dress rehearsal and opening night. Staging is the rehearsal stage where you can make mistakes in front of a small, friendly audience. Production is opening night with the real crowd, so it deserves stricter rules about who is allowed on stage and when.

A GitHub **Environment** is a named deployment target - like `staging`, `production`, `preview`. Environments let you:
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

An approval gate is like the second key needed to launch a missile, or a bouncer at the door of a club. The workflow can do everything up to the door, but it cannot step through until a trusted person turns their key and lets it in. This puts a human in the loop right before the riskiest moment.

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
2. `deploy-production` starts - but immediately pauses
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
# No need to change your workflow - environment secrets override repo secrets
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

## 6. OIDC - Keyless Authentication

### The Problem with Static Credentials

Traditional approach: create a cloud IAM user, generate long-lived access keys, store in GitHub Secrets.

**Problems:**
- Keys never expire (huge security risk if leaked)
- Keys have to be rotated manually
- Every rotation requires updating GitHub Secrets
- One compromised key = full access until discovered

### What is OIDC?

OIDC is like showing a trusted ID badge at a door instead of carrying a permanent house key around in your pocket all day. With a permanent key, anyone who steals it can get in forever. With a badge check, the guard confirms who you are at that moment and gives you a pass that expires when your shift ends. GitHub Actions shows its badge, the cloud provider checks it, and hands back a short-lived pass.

**OpenID Connect (OIDC)** allows GitHub Actions to authenticate with cloud providers (AWS, GCP, Azure) **without storing any long-lived credentials**. Instead:

1. GitHub generates a **short-lived JWT token** for each workflow run
2. The cloud provider validates the token directly with GitHub
3. The cloud provider grants temporary credentials that expire when the job ends

```mermaid
sequenceDiagram
    participant GA as GitHub Actions
    participant GH as GitHub OIDC Endpoint
    participant AWS as AWS STS
    GA->>AWS: I am run #1234 on repo org/myapp, branch main
    AWS->>GH: Verify this token is genuine
    GH-->>AWS: Confirmed, this token is valid
    AWS-->>GA: I trust GitHub. Here are 1-hour credentials for role X
    Note over GA: Workflow uses credentials, they expire when the job ends
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

> One role and one trust policy is where you start, not where you finish. A real project
> needs several identities, and the trust policy above has a trap in it that costs people an
> afternoon. [Section 9](#9-aws-iam-in-practice) takes this
> from the toy example to the real thing.

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

The `GITHUB_TOKEN` default depends on repo/org settings: **older repos** default to broad **read/write**, but **new repositories (and orgs) since early 2023 default to read-only `contents` and nothing else**. Do not assume - check **Settings - Actions - General - Workflow permissions**, and set an explicit `permissions:` block so your workflow is the same everywhere:

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

Least privilege is like giving a house-sitter a key to only one room rather than the whole house. If that one key is lost or misused, the damage is limited to a single room. Give each job only the permissions it genuinely needs, and nothing more.

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
# RISKY - a new v4 release could break your workflow or be malicious
- uses: actions/checkout@v4

# SAFER - pin to an exact commit SHA
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
```

Use a tool like Dependabot to keep action versions up to date safely.

### 2. Never Echo Secrets

```yaml
# WRONG - even though GitHub masks it, don't do this
- run: echo "Token is ${{ secrets.MY_TOKEN }}"

# RIGHT - pass secrets via environment variables
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

# SAFER - only runs if PR is not from a fork
on:
  pull_request_target:
    types: [labeled]
# Then check: if: github.event.pull_request.head.repo.full_name == github.repository
```

### 5. Audit Your Workflows Regularly

- Use GitHub's built-in **Secret Scanning** - it auto-detects secrets committed by accident
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

## 9. AWS IAM in Practice

Section 6 showed the OIDC handshake with one role and one trust policy. That is the right
place to start and it is not what a real project looks like. This section takes it the rest
of the way, using the end-to-end project from Day 5 as the worked example.

A pipeline that builds an application and manages its infrastructure needs **more than one
identity**, and the workloads it deploys need identities of their own. Five, in the project
we build:

| Identity | Who uses it | Created by | How it authenticates |
|---|---|---|---|
| the infra role | the Terraform pipeline | you, by hand, once | GitHub OIDC |
| the build role | the application CI pipeline | Terraform | GitHub OIDC |
| the app role | the application pod | Terraform | EKS Pod Identity |
| the controller role | the load balancer controller pod | Terraform | EKS Pod Identity |
| the storage driver role | the EBS CSI driver pod | Terraform | EKS Pod Identity |

Two ideas run through all of it. **Nothing holds a long-lived access key**, which is the
point of Section 6, extended to the workloads and not just the pipeline. And **the order
matters**, because one role has to exist before the automation that creates the others can
run at all.

### Why two pipeline roles, not one

This is the single most useful habit in this section, and it costs nothing to adopt.

Building a container image and destroying a VPC are wildly different levels of trust. If
one role does both, then every routine application build, on every branch, runs with the
power to delete your entire environment.

So there are two:

- **The infra role** is assumed only by the Terraform workflow. It has broad permissions
  because it genuinely creates networks, clusters and IAM roles.
- **The build role** is assumed by the application workflow. It can push container images
  to two specific repositories and do nothing else at all.

Keeping the workflows separate is what makes the two trust levels possible. Combine the
workflows and you are forced to give the combined role the union of both permission sets.

### The chicken and egg problem

Terraform creates the build role and the three workload roles. But Terraform needs somewhere
to store its state, and the workflow needs permission to run Terraform. Neither can be
created by the thing that needs them.

So exactly three things are created **once, by hand, with admin credentials**. This is
called the bootstrap, or stage zero:

1. An S3 bucket for Terraform state, versioned, encrypted and private.
2. The GitHub OIDC identity provider.
3. The infra role that the pipeline assumes.

Everything else is created by Terraform through the pipeline. Students often try to
automate the bootstrap too and get stuck in a loop; the answer is that a small, documented,
one-time manual step is correct here.

### The trust policy trap that wastes an afternoon

Section 6 gave the documented subject form:

```
repo:myorg/myrepo:ref:refs/heads/main
```

Some GitHub accounts emit an **immutable id** form instead:

```
repo:myorg@12345/myrepo@67890:ref:refs/heads/main
```

A trust policy matching `repo:myorg/myrepo:*` does not match the second form. The failure is
maddening, because every name in your pattern is spelled correctly and the error says
nothing about why:

```
Not authorized to perform sts:AssumeRoleWithWebIdentity
```

Write the pattern so it matches both forms:

```json
"StringLike": {
  "token.actions.githubusercontent.com:sub": "repo:OWNER@*/REPO@*:*"
}
```

If you want to see the subject your account actually sends rather than guessing, the failed
call is recorded in **AWS CloudTrail**. Open Event history, filter on the
`AssumeRoleWithWebIdentity` event name, and read the subject from the request parameters.

Never solve this by removing the subject condition. Without it, any repository on GitHub can
assume your role.

### What the build role may actually do

This is a complete, real permission policy. It is short on purpose.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:BatchGetImage"
      ],
      "Resource": [
        "arn:aws:ecr:REGION:ACCOUNT:repository/myapp-backend",
        "arn:aws:ecr:REGION:ACCOUNT:repository/myapp-frontend"
      ]
    }
  ]
}
```

Two details students get wrong here every time.

**`ecr:GetAuthorizationToken` must be on `"*"`.** It is not a resource-scoped action, so
putting a repository ARN there produces a policy that looks careful and then fails at
`docker login` with an access denied that names no resource at all.

**Everything else is pinned to two repositories.** Push and pull on those two, and nothing
anywhere else in the registry. That is the whole permission set for the pipeline that ships
your application.

### The workloads need identities too

Section 6 solved authentication for the pipeline. The pods you deploy have the same problem:
an application that reads and writes S3 needs credentials, and putting an access key in a
Kubernetes Secret recreates exactly the problem OIDC removed.

On EKS the answer is **Pod Identity**, the modern successor to IRSA. The shape is the same
idea as OIDC, applied inside the cluster:

1. Create a normal IAM role that trusts the EKS service.
2. Create an **association** mapping a specific cluster, namespace and ServiceAccount to
   that role.
3. An agent on the cluster hands short-lived credentials to pods running under that
   ServiceAccount, and to nothing else.

The ServiceAccount needs no annotation. That is the visible difference from IRSA, where the
role ARN had to be annotated onto the ServiceAccount itself. Here the mapping lives on the
AWS side, in the association.

Every Pod Identity role shares this trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "pods.eks.amazonaws.com"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
    }
  ]
}
```

`sts:TagSession` is **required, not optional**. EKS tags the session with the cluster,
namespace and ServiceAccount, which is what makes the association enforceable and what shows
up in CloudTrail. Leave it out and the role cannot be assumed.

The application's own permission policy is a good example of real least privilege:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::my-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::my-bucket"
    }
  ]
}
```

Look carefully at the two resource forms. Object actions apply to the **objects**, written
as the bucket ARN followed by a slash and a star. ListBucket applies to the **bucket
itself**, with no trailing slash and no star. Swapping those two is the most common S3
policy mistake there is, and it fails in a way that looks exactly like the permission is
missing entirely.

### Verifying it, layer by layer

Creating a role always succeeds. Whether it authenticates only shows up later, so check each
layer separately rather than guessing.

**The pipeline roles.** The first AWS step in the workflow either assumes the role or it does
not. A failure reading `Not authorized to perform sts:AssumeRoleWithWebIdentity` is a trust
policy problem and is almost always the subject claim. An access denied during `docker login`
is a permission policy problem, and usually the authorization token action.

**The workload roles.** Check the association exists, then check a pod actually received
credentials:

```bash
aws eks list-pod-identity-associations --cluster-name my-cluster --region REGION --output table
kubectl -n my-namespace exec deploy/my-app -- env | grep AWS_
```

A pod that picked up Pod Identity has `AWS_CONTAINER_CREDENTIALS_FULL_URI` and
`AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE` in its environment. If those are missing, the
association does not match the pod: check that the namespace and ServiceAccount name are
exactly the ones the pod runs under, and that the `eks-pod-identity-agent` add-on is
installed and running.

**End to end.** Exercise the feature that needs the permission. In our project, uploading a
photo tests the application role writing to S3, and the image appearing afterwards tests the
presigned URL reading it back.

### One teardown gotcha worth knowing

Volumes created by a PersistentVolumeClaim are created by **Kubernetes**, not by Terraform.
So `terraform destroy` does not know they exist and leaves them behind, still billing.

After tearing down a cluster, look for orphans:

```bash
aws ec2 describe-volumes --region REGION --filters Name=status,Values=available --output table
```

This is not a hypothetical. Our own project teardown left a 20 GiB volume from the database
behind after Terraform reported a clean destroy of everything it managed.

### Hardening checklist for production

The version we build in this course is a teaching build, and the infra role gets broad
permissions so the lesson stays about pipelines rather than policy authoring. Before any of
this goes near something real:

- **Split plan from apply.** Two roles, with the plan role read-only, so a pull request from
  a fork can never change infrastructure.
- **Replace broad administrator permissions** on the infra role with a policy scoped to the
  services the project actually manages.
- **Add a permissions boundary.** Without one, the ability to create IAM roles is effectively
  the ability to escalate to administrator, because a role that can create roles can create a
  more powerful one.
- **Narrow the subject condition** from the whole repository down to a branch or a GitHub
  environment, so only workflows on `main` can deploy.
- **Require environment approval** on the apply job, using the approval gates from Section 4,
  so a human stands between a merge and a production change.

---

## Lab - Deploy with Secrets and Approval Gate

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
          # Do NOT echo any part of a secret (even a slice) - see 8.2 "Never Echo Secrets".
          # Just USE it; the mask keeps full values out of logs, partial values may not be masked.
          curl -sf -H "Authorization: Bearer $API_KEY" "${{ secrets.DEPLOY_URL }}/health"
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
3. When staging passes, `deploy-production` starts - but shows "Waiting for approval"
4. GitHub sends you an email notification
5. Go to the Actions tab → click "Review deployments" → Approve
6. Production deployment runs

---

## Common Mistakes

- Hardcoding secrets directly in a workflow YAML file. Once committed, the value lives in git history forever, even after you delete the line. Always reference `${{ secrets.NAME }}` instead.
- Echoing secrets to the log with `echo "$MY_SECRET"`. GitHub tries to mask values, but masking is not guaranteed for transformed or partial values. Pass secrets through environment variables and never print them.
- Giving the built-in `GITHUB_TOKEN` broad write-all permissions. Set `permissions:` explicitly at the workflow or job level and grant only what each job needs.
- Using `pull_request_target` carelessly with fork pull requests. That trigger runs with access to your secrets in the base repository context, so untrusted fork code could exfiltrate them. Guard it with strict conditions or avoid it.
- Forgetting `id-token: write` when setting up OIDC, or leaving old static access keys in Secrets after switching to OIDC. The dormant keys remain a liability until removed.
- Reusing the same secret value across staging and production. A leak in the low-trust staging environment then compromises production too. Use environment-specific secrets.
- Using one AWS role for both the application build and the infrastructure pipeline. Every routine image build then runs with the power to delete your whole environment. Split them.
- Scoping `ecr:GetAuthorizationToken` to a repository ARN. It is not a resource-scoped action, so the policy looks careful and then fails at `docker login` with an access denied naming no resource.
- Writing an S3 policy with the object actions and `s3:ListBucket` on the same resource. Object actions need `bucket/*`, ListBucket needs the bare bucket, and getting it wrong looks exactly like a missing permission.

## Quick Self-Check

1. Why is deleting a hardcoded secret from a workflow file not enough to make it safe again?
2. What is the difference between a repository secret and an environment secret, and which one wins when both define the same name?
3. What does an approval gate add to a deployment, and where do you configure required reviewers?
4. In plain terms, how does OIDC let GitHub Actions deploy to AWS without storing an access key?
5. Which single line must appear under `permissions:` for a job to request an OIDC token, and why should you still keep the other permissions minimal?
6. Your OIDC trust policy names the right repository and the workflow still fails with `Not authorized to perform sts:AssumeRoleWithWebIdentity`. What is the most likely cause, and where would you look to confirm it?
7. Why can the bootstrap role not be created by the same Terraform that creates every other role?
8. A pod needs to read from S3. Why is putting an access key in a Kubernetes Secret the wrong answer, and what replaces it on EKS?

## Summary

| Concept | Key Point |
|---|---|
| Secrets | Never hardcode - always use `${{ secrets.NAME }}` |
| GITHUB_TOKEN | Auto-created, scoped to current repo and run |
| Environments | Named targets (staging, prod) with protection rules |
| Approval gates | Pause workflow until human approves |
| OIDC | No stored credentials - GitHub proves identity to cloud |
| Least privilege | Only grant permissions your job actually needs |
| Two pipeline roles | Build role pushes images; infra role builds infrastructure. Never one role for both |
| Subject claim | Some accounts emit an immutable-id form, so match `repo:OWNER@*/REPO@*:*` |
| Bootstrap | State bucket, OIDC provider and infra role are created once, by hand |
| Pod Identity | Workloads get short-lived cloud credentials too, with no key in a Secret |
| Secret masking | GitHub auto-redacts secrets from logs |

---

**Next up ->** [Day 4 - Continuous Deployment](../day4-continuous-deployment/notes.md)
