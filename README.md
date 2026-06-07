# Learn CI/CD with GitHub Actions

Module 5 of the DevOps Masterclass. By now you can version code (Git), package it (Docker), run it at scale (Kubernetes), and provision the infrastructure (Terraform). CI/CD is the glue that ties it all together: it automatically builds, tests, and ships your code every time you push.

## What problem does CI/CD solve?

Doing builds, tests, and deployments by hand is slow and error-prone. Someone forgets a step, tests get skipped under deadline pressure, and a bad change reaches users. CI/CD removes the manual work: every push runs the same checks automatically, and only code that passes every gate is allowed to ship.

A useful way to picture it: a CI/CD pipeline is a factory assembly line with quality inspectors at each station. Your code is the raw material. Each station (build, test, lint, security scan) inspects it. If any inspector finds a defect, the line stops and the product never reaches the customer. Only goods that pass every check get shipped, and a human supervisor signs off before the final delivery to production.

```mermaid
flowchart LR
    Dev["Developer pushes code"] --> CI["CI: build + test + lint + scan"]
    CI -->|all checks pass| Stage["Deploy to staging"]
    CI -->|any check fails| Block["Stop - merge blocked"]
    Stage --> Gate["Human approval"]
    Gate --> Prod["Deploy to production"]
```

## Interactive demo

Open [animations/cicd-pipeline.html](animations/cicd-pipeline.html) in any browser. Push a good commit and watch it flow to production; push a buggy commit and watch CI stop it before it ships.

## Course structure

This module uses GitHub Actions, GitHub's built-in CI/CD platform. It is free for public repositories and needs no extra tools beyond a GitHub account.

| Module | Topic | What you will learn |
|---|---|---|
| [1. Foundations](01-foundations/README.md) | CI/CD concepts and GitHub Actions basics | What CI, CD, and pipelines are; workflows, jobs, steps, runners, triggers; your first workflow |
| [2. Continuous Integration](02-ci/README.md) | Automated testing and quality gates | Running tests, linting, matrix builds, caching, artifacts, branch protection |
| [3. Secrets and Environments](03-secrets/README.md) | Security and safe deployments | GitHub Secrets, environments, approval gates, OIDC keyless auth, least privilege |
| [4. Continuous Deployment](04-cd/README.md) | Shipping to production | Building and pushing Docker images, deploying to cloud platforms, versioning, rollbacks, smoke tests |

## Prerequisites

- A GitHub account
- Comfort with Git basics (see the [Git module](../learn-git))
- Helpful but not required: the [Docker module](../learn-docker), since Continuous Deployment builds and ships container images

## Learning outcomes

By the end of this module you will be able to:

- Explain CI, Continuous Delivery, and Continuous Deployment, and how they differ
- Write GitHub Actions workflows that build and test code on every push and pull request
- Run tests across multiple versions in parallel, cache dependencies, and share build artifacts
- Store secrets safely and require human approval before production deployments
- Build and publish Docker images and deploy them to a cloud platform
- Roll back a bad release quickly and verify deployments with smoke tests

## How to use this module

1. Work through the four lessons in order; each builds on the previous one.
2. Create a throwaway GitHub repository and actually run the workflows. Watching a pipeline run live in the Actions tab teaches more than reading about it.
3. Try the labs at the end of each lesson, then attempt the challenges.

Start with [Module 1: Foundations](01-foundations/README.md). When you finish, return to the [main DevOps course](../README.md).
