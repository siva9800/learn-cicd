# CI Concepts - GitHub Actions in Detail

> A complete, plain-English reference for **every GitHub Actions concept** used in CI, each one explained AND shown **where it appears in our real [`ci.yml`](ci.yml)**. Read [README.md](README.md) to *run* the demo; read this to *understand* it.

Contents:
1. [Workflow file anatomy](#1-workflow-file-anatomy)
2. [Triggers - the `on:` block (all the kinds)](#2-triggers---the-on-block-all-the-kinds)
3. [Runners (`runs-on`)](#3-runners-runs-on)
4. [Jobs](#4-jobs)
5. [Steps](#5-steps)
6. [Actions and version pinning](#6-actions-and-version-pinning)
7. [Contexts and expressions](#7-contexts-and-expressions)
8. [`if` conditions](#8-if-conditions)
9. [Setup actions and caching](#9-setup-actions-and-caching)
10. [Matrix builds](#10-matrix-builds)
11. [Caching in depth](#11-caching-in-depth)
12. [Artifacts](#12-artifacts)
13. [Outputs (step and job)](#13-outputs-step-and-job)
14. [Permissions](#14-permissions)
15. [Reusable workflows and composite actions](#15-reusable-workflows-and-composite-actions)
16. [Status checks and branch protection](#16-status-checks-and-branch-protection)
17. [Every concept, mapped to our ci.yml](#every-concept-mapped-to-our-ciyml)

---

## 1. Workflow file anatomy

A **workflow** is a YAML file in `.github/workflows/`. It has four nested levels:

```
workflow  (the file)
  └── jobs         (run in parallel by default)
        └── steps  (run in order, top to bottom)
              └── an action (uses:) OR a shell command (run:)
```

```yaml
name: CI (fastapi-demo)     # 1. the workflow's display name
on: [push]                  # 2. WHEN it runs (triggers)
jobs:                       # 3. WHAT it does
  test:                     #    a job
    runs-on: ubuntu-latest  #    which machine
    steps:                  #    the ordered steps
      - uses: actions/checkout@v4
      - run: pytest
```

- **Workflow** = the whole file (one pipeline).
- **Job** = a set of steps that run together on one runner. Jobs are **independent and parallel** unless you link them with `needs`.
- **Step** = one action or one shell command. Steps in a job run **in order** and **share the same machine and filesystem**.

---

## 2. Triggers - the `on:` block (all the kinds)

`on:` decides **when** the workflow runs. These are the events you will actually use:

| Trigger | Fires when | Typical use |
|---------|-----------|-------------|
| **`push`** | Commits are pushed to a branch | Run CI on every push |
| **`pull_request`** | A PR is opened/updated | Gate the PR before merge |
| **`workflow_dispatch`** | You click "Run workflow" (manual) | On-demand runs, with inputs |
| **`schedule`** | A cron time | Nightly builds, cleanup |
| **`workflow_run`** | Another workflow finishes | Chain CD after CI (see [cd/](../cd/concepts.md)) |
| **`release`** | A release is published | Publish artifacts |
| **`issues` / `issue_comment`** | Issue activity | ChatOps, automation |

**Filters** narrow a trigger:

```yaml
on:
  push:
    branches: [main, "release/**"]   # only these branches (glob patterns allowed)
    paths: ["fastapi-demo/**"]        # only when these files change (monorepo filter)
    tags: ["v*.*.*"]                  # or on version tags
  pull_request:
    branches: [main]
    paths-ignore: ["**/*.md"]         # the inverse: skip when ONLY these change
```

**Manual runs with inputs** (`workflow_dispatch`):

```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [staging, production]
        default: staging
# used later as ${{ inputs.environment }}
```

**Scheduled runs** use POSIX cron (UTC):

```yaml
on:
  schedule:
    - cron: "0 2 * * *"    # every day at 02:00 UTC
```

> **In our `ci.yml`:** we trigger on `push` and `pull_request`, both **path-filtered to `fastapi-demo/**`** so the pipeline only runs when the demo changes - not on unrelated notes edits. That is the monorepo pattern.

---

## 3. Runners (`runs-on`)

A **runner** is the machine that executes a job. It is **fresh and wiped after every job** - nothing survives to the next job unless you cache it or save an artifact.

| Type | `runs-on` | Notes |
|------|-----------|-------|
| **GitHub-hosted** | `ubuntu-latest`, `windows-latest`, `macos-latest` | Free for public repos; pre-loaded with common tools (Python, Node, Docker, git) |
| **Self-hosted** | `[self-hosted, gpu]` | Your own machine (GPU, private network, big caches). You maintain and secure it; it is NOT auto-wiped |

```yaml
jobs:
  test:
    runs-on: ubuntu-latest    # our demo uses hosted Ubuntu
```

---

## 4. Jobs

Jobs are the parallel units. Key controls:

**`needs`** - make one job wait for another (turns parallel jobs into a sequence / a DAG):

```yaml
jobs:
  lint: { runs-on: ubuntu-latest, steps: [...] }
  test: { runs-on: ubuntu-latest, steps: [...] }
  build:
    needs: [lint, test]     # build starts ONLY after lint AND test succeed
    runs-on: ubuntu-latest
    steps: [...]
```

**`defaults`** - shared settings for every `run:` step in the file/job (e.g. the working directory):

```yaml
defaults:
  run:
    working-directory: fastapi-demo   # every `run:` executes inside this folder
```

**`timeout-minutes`** - cap a job so a hung step cannot run for hours:

```yaml
jobs:
  test:
    timeout-minutes: 15
```

**`concurrency`** - stop overlapping runs of the same workflow/branch:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true    # cancel an older in-progress run (use false for deploys)
```

> **In our `ci.yml`:** three jobs - `lint`, `test`, `build`. `build` has `needs: [lint, test]`, so it only runs if both passed - the "gate". `defaults.run.working-directory: fastapi-demo` points every command at the demo folder.

---

## 5. Steps

A step is either an **action** (`uses:`) or a **shell command** (`run:`).

```yaml
steps:
  - name: Checkout code          # optional label shown in the UI
    uses: actions/checkout@v4    # an ACTION (reusable unit)

  - name: Install deps
    id: install                  # give it an id to reference its outputs
    run: pip install -r requirements.txt   # a SHELL command
    working-directory: fastapi-demo         # per-step override
    env:                                    # per-step env vars
      PIP_NO_INPUT: "1"
    shell: bash                             # bash | pwsh | python ...
```

- `uses:` vs `run:` - `uses` pulls in a prebuilt action; `run` runs shell you write.
- `name` is cosmetic; `id` lets later steps read this step's outputs.
- `with:` passes inputs to an action; `env:` sets environment variables.
- Steps share the runner's filesystem, so a file one step writes, the next can read.

---

## 6. Actions and version pinning

An **action** is a reusable unit of automation (like an npm package for CI). Sources: official (`actions/checkout`), the Marketplace, or your own repo.

```yaml
- uses: actions/checkout@v4          # official - checks out your code
- uses: actions/setup-python@v5      # official - installs Python
- uses: ./.github/actions/setup      # your own local composite action
```

**Always pin a version.** `@v4` follows the latest v4.x (gets fixes, no breaking changes). For maximum security, pin a full commit SHA. Never use `@main` - it can change under you and break your pipeline.

---

## 7. Contexts and expressions

`${{ ... }}` is an **expression**. Inside it you read **contexts** (objects of run data):

| Context | Holds | Example |
|---------|-------|---------|
| `github` | Event/repo info | `github.sha`, `github.ref`, `github.repository`, `github.actor` |
| `matrix` | The current matrix values | `matrix.python-version` |
| `steps` | Outputs of earlier steps | `steps.install.outputs.version` |
| `needs` | Outputs of jobs you depend on | `needs.build.outputs.image` |
| `env` | Environment variables | `env.MY_VAR` |
| `secrets` | Repo/org secrets | `secrets.GITHUB_TOKEN` |
| `inputs` | `workflow_dispatch`/reusable inputs | `inputs.environment` |
| `runner` | Runner info | `runner.os`, `runner.temp` |

**Functions** you will use often: `success()`, `failure()`, `always()`, `cancelled()`, `contains()`, `startsWith()`, `hashFiles('**/requirements.txt')`, plus operators `==`, `!=`, `&&`, `||`.

```yaml
- run: echo "Building ${{ github.sha }} on ${{ runner.os }}"
```

---

## 8. `if` conditions

Any step or job can be conditional with `if:`:

```yaml
steps:
  - run: pytest

  - name: Upload results even on failure
    if: always()                          # run regardless of earlier failures
    uses: actions/upload-artifact@v4

  - name: Only on main
    if: github.ref == 'refs/heads/main'

  - name: Only when something failed
    if: failure()
```

- `always()` - run no matter what (great for uploading logs/reports).
- `failure()` / `success()` - run only after a failure / only if all prior steps passed.
- Plain expressions like `github.event_name == 'pull_request'` also work.

---

## 9. Setup actions and caching

Language setup actions install a runtime AND can cache dependencies:

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
    cache: pip                                    # cache the pip download cache
    cache-dependency-path: fastapi-demo/requirements.txt   # what to key the cache on
```

- `cache: pip` (or `npm`, `yarn`, `pnpm` for Node; Maven/Gradle for Java) turns on built-in caching.
- `cache-dependency-path` tells it which lock/requirements file to hash for the cache key. We set it because our workflow lives at the repo root while `requirements.txt` is in `fastapi-demo/`.

> **In our `ci.yml`:** every job uses `setup-python@v5` with `cache: pip` so repeat runs restore dependencies in seconds instead of re-downloading.

---

## 10. Matrix builds

A **matrix** runs the same job many times in parallel with different values - the way you prove your app works on every version/OS you support.

```yaml
strategy:
  fail-fast: false                 # let ALL combos finish (see every failure)
  max-parallel: 4                  # optional cap on concurrent matrix jobs
  matrix:
    python-version: ["3.11", "3.12"]   # 2 parallel jobs
```

Multi-dimensional (a grid):

```yaml
matrix:
  os: [ubuntu-latest, windows-latest]
  python-version: ["3.11", "3.12"]     # 2 x 2 = 4 jobs
runs-on: ${{ matrix.os }}
```

Tune the grid:

```yaml
matrix:
  os: [ubuntu-latest, windows-latest]
  python-version: ["3.11", "3.12"]
  exclude:
    - { os: windows-latest, python-version: "3.11" }   # drop this combo
  include:
    - { os: ubuntu-latest, python-version: "3.13", experimental: true }  # add a special one
```

- **`fail-fast: true`** (default) cancels the other combos at the first failure. Set **`false`** to see all failures.
- **`include`/`exclude`** add or remove specific combinations.

> **In our `ci.yml`:** the `test` job runs on Python **3.11 and 3.12** in parallel, with `fail-fast: false`.

---

## 11. Caching in depth

Caching stores files (usually the dependency download cache) between runs so you do not re-fetch them every time.

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/pip                                     # what to cache
    key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}   # exact-match key
    restore-keys: ${{ runner.os }}-pip-                    # fallback prefix if no exact hit
```

- **`key`** - if it matches exactly, that cache is restored (a "hit"). It usually includes `hashFiles(<lock file>)`, so **changing the lock file changes the key and rebuilds the cache** - which is correct.
- **`restore-keys`** - if the exact key misses, restore the newest cache whose key starts with this prefix (a warm-ish start).
- **Rule:** cache the **download** cache (`~/.cache/pip`, `~/.npm`), NOT the installed env (`node_modules`, the venv), and always run the install step. Limits: ~10 GB/repo, evicted after 7 days unused, separate per OS.

> The built-in `cache: pip` in `setup-python` (Section 9) does all of this for you - reach for manual `actions/cache` only for something it does not cover (a build output dir, a custom tool).

---

## 12. Artifacts

An **artifact** is a file/folder a job produces that you keep or hand to another job. Needed because **each job runs on a fresh runner** - files do not travel between jobs otherwise.

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: coverage-report
    path: htmlcov/
    retention-days: 7          # auto-delete after a week (default 90)
    if-no-files-found: error   # fail if nothing was produced
```

Download it in a later job:

```yaml
jobs:
  test: { ... uploads "dist" ... }
  publish:
    needs: test
    steps:
      - uses: actions/download-artifact@v4
        with: { name: dist, path: dist/ }
```

Common artifacts: coverage reports, built packages, logs, and the **Docker image** (the big one - though images usually go to a registry, see [cd/](../cd/concepts.md), not artifact storage).

---

## 13. Outputs (step and job)

**Step outputs** - a step writes `key=value` to the `$GITHUB_OUTPUT` file; later steps read it:

```yaml
- id: ver
  run: echo "version=$(python -c 'import app.main as m; print(m.APP_VERSION)')" >> "$GITHUB_OUTPUT"
- run: echo "Version is ${{ steps.ver.outputs.version }}"
```

**Job outputs** - expose a value to jobs that `need` this one:

```yaml
jobs:
  build:
    outputs:
      image: ${{ steps.meta.outputs.tag }}
    steps:
      - id: meta
        run: echo "tag=ghcr.io/app:${{ github.sha }}" >> "$GITHUB_OUTPUT"
  deploy:
    needs: build
    steps:
      - run: echo "Deploying ${{ needs.build.outputs.image }}"
```

---

## 14. Permissions

Every workflow gets an automatic `GITHUB_TOKEN`. Its default permissions depend on repo settings (new repos default to **read-only**). Grant only what a job needs (least privilege):

```yaml
permissions:
  contents: read      # read the repo
  packages: write     # push to GHCR (used by CD, not CI)
```

Set it at the workflow level (all jobs) or per job. Our CI needs nothing beyond read, so it does not widen permissions; CD does (`packages: write`).

---

## 15. Reusable workflows and composite actions

Two ways to kill the repeated `checkout + setup-python + install` boilerplate:

**Composite action** - bundle repeated **steps** into one step (`.github/actions/setup/action.yml`):

```yaml
runs:
  using: composite
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.12", cache: pip }
    - run: pip install -r requirements.txt
      shell: bash          # composite run steps MUST set a shell
# use it:  - uses: ./.github/actions/setup
```

**Reusable workflow** - a whole workflow other workflows `call` (`on: workflow_call`), sharing entire pipelines across repos:

```yaml
# caller
jobs:
  ci:
    uses: ./.github/workflows/ci.yml
    with: { python-version: "3.11" }
```

Composite action = reuse **steps** inside a job. Reusable workflow = reuse **whole jobs** across repos.

---

## 16. Status checks and branch protection

Each job reports a **status** to GitHub (green check / red X). **Branch protection** turns those into required gates so a red check blocks the Merge button:

`Settings -> Branches -> Add rule -> require status checks -> add "lint", "test"`.

Without branch protection, a red pipeline is only a suggestion. With it, **only code that passed CI can merge** - which is the entire point.

---

## Every concept, mapped to our ci.yml

| Concept | Where it is in [`ci.yml`](ci.yml) |
|---------|-----------------------------------|
| Triggers + path filter | `on: push/pull_request` with `paths: fastapi-demo/**` |
| Runner | `runs-on: ubuntu-latest` |
| `defaults.working-directory` | points every `run:` at `fastapi-demo` |
| Jobs + `needs` | `lint`, `test`, `build`; `build` needs `[lint, test]` |
| Actions + pinning | `actions/checkout@v4`, `actions/setup-python@v5` |
| Setup + caching | `setup-python` with `cache: pip` + `cache-dependency-path` |
| Matrix + `fail-fast` | `test` runs on Python 3.11 and 3.12 |
| Steps (`uses`/`run`) | checkout, setup, `pip install`, `flake8`, `pytest`, `docker build` |
| Contexts | `${{ matrix.python-version }}`, `${{ github.sha }}` |

---

**See also:** [README.md](README.md) (run the demo) - [CD concepts](../cd/concepts.md) (the deploy side).
