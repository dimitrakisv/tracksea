# Sprint 1 Playbook: Repository Technical Foundation

## Objective

Create the minimum technical foundation required to begin implementing TrackSea product features.

Sprint 1 establishes:

- a runnable FastAPI backend;
- a runnable React and TypeScript frontend;
- PostgreSQL with PostGIS;
- Docker-based local development;
- SQLAlchemy and Alembic foundations;
- formatting, linting, typing, testing, and CI;
- environment configuration; and
- accurate local-development documentation.

Sprint 1 must not implement TrackSea business features.

## Required reading

Before each step, read:

1. `AGENTS.md`
2. `docs/PROJECT_CONSTITUTION.md`
3. `docs/product/vision.md`
4. `docs/product/mvp-scope.md`
5. `docs/domain/domain-model.md`
6. `docs/domain/identification-workflow.md`
7. `docs/architecture/system-overview.md`
8. `docs/decisions/ADR-001-fastapi.md`
9. `docs/decisions/ADR-002-modular-monolith.md`
10. `docs/engineering/git-workflow.md`
11. `docs/engineering/definition-of-done.md`
12. `.ai/README.md`
13. `.ai/playbooks/implement-feature.md`

## Global rules

Use or create:

```text
feat/repository-bootstrap
```

Use one draft pull request for Sprint 1 while preserving meaningful semantic commits.

Do not implement:

- authentication;
- user domain models;
- observations;
- taxonomy;
- identifications;
- agreements;
- verifications;
- Marine Life;
- uploads;
- exports;
- gamification;
- forums;
- AI identification;
- native applications; or
- other product features.

Do not introduce Redis, Celery, Kubernetes, microservices, event buses, or cloud-specific application dependencies.

Keep the implementation minimal and aligned with the modular-monolith ADR.

After every step:

1. Run the relevant checks.
2. Review the diff for unrelated changes.
3. Create the specified semantic commit.
4. Report files changed, commands run, results, assumptions, and unresolved risks.

Never claim a command passed unless it was actually run.

## Step 0: Inspect and plan

### Goal

Understand the repository before modifying files.

### Actions

- Read all required documents.
- Inspect the repository structure.
- Confirm branch and Git status.
- Check available Python, Node.js, Docker, and Docker Compose versions.
- Identify existing configuration that must be preserved.
- Present the proposed directory structure.

Expected high-level structure:

```text
tracksea/
├── backend/
├── frontend/
├── docs/
├── .ai/
├── .github/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── AGENTS.md
├── CONTRIBUTING.md
└── README.md
```

Do not modify files in this step unless correcting a blocking documentation issue.

## Step 1: Bootstrap FastAPI

### Goal

Create a minimal, typed, testable FastAPI application.

### Requirements

Use Python 3.12 or newer with:

- FastAPI;
- Pydantic settings;
- SQLAlchemy 2;
- Alembic;
- a PostgreSQL driver;
- pytest;
- an HTTP test client;
- Ruff; and
- a Python type checker.

Suggested structure:

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── health.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   └── db/
│       ├── __init__.py
│       ├── base.py
│       └── session.py
├── tests/
│   └── test_health.py
├── alembic/
├── alembic.ini
└── pyproject.toml
```

Provide:

```text
GET /api/v1/health
```

with a minimal response such as:

```json
{"status":"ok"}
```

Do not add domain models or database tables.

### Verification

Run backend formatting, linting, type checking, and tests.

### Commit

```text
build(backend): initialize FastAPI application
```

## Step 2: Bootstrap React

### Goal

Create a minimal React and TypeScript application.

### Requirements

Use:

- React;
- TypeScript;
- Vite;
- ESLint;
- a formatter;
- Vitest; and
- React Testing Library.

Suggested structure:

```text
frontend/
├── src/
│   ├── app/
│   ├── components/
│   ├── test/
│   ├── App.tsx
│   └── main.tsx
├── package.json
├── tsconfig.json
├── vite.config.ts
└── eslint.config.js
```

Create only a minimal landing or system-status screen with the TrackSea name, tagline, and an indication that the technical foundation is running.

Do not design final product screens.

### Verification

Run formatting, linting, type checking, tests, and a production build.

### Commit

```text
build(frontend): initialize React application
```

## Step 3: Add PostgreSQL and PostGIS

### Goal

Provide a local PostgreSQL database with PostGIS through Docker Compose.

### Requirements

Create or update `docker-compose.yml` with a maintained PostGIS image.

Include:

- database name;
- application user;
- password from environment variables;
- persistent volume;
- health check; and
- exposed local port.

Create `.env.example` with safe placeholders, including values such as:

```text
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
DATABASE_URL
BACKEND_PORT
FRONTEND_PORT
```

Keep names consistent across the repository.

### Verification

Confirm the database starts, becomes healthy, and has PostGIS available.

### Commit

```text
infra: add PostgreSQL and PostGIS environment
```

## Step 4: Add the Docker development stack

### Goal

Run backend, frontend, and database consistently through Docker Compose.

### Requirements

Add:

```text
backend/Dockerfile
frontend/Dockerfile
```

Add backend and frontend services to Docker Compose.

The intended local command should be:

```bash
docker compose up --build
```

Avoid reverse proxies, TLS, Kubernetes, and production deployment automation.

### Verification

Confirm all containers build, the database becomes healthy, the backend health endpoint responds, the frontend loads, service-name networking works, and the database volume persists.

### Commit

```text
infra: add local Docker development stack
```

## Step 5: Configure SQLAlchemy and Alembic

### Goal

Prepare the backend for future persistence and migrations.

### Requirements

Configure:

- SQLAlchemy 2 engine and session factory;
- application database settings;
- Alembic environment;
- metadata import boundary; and
- database connectivity verification.

Do not create TrackSea domain tables.

Do not automatically run destructive migrations at application startup.

### Verification

Check Alembic configuration and run safe upgrade and downgrade verification against the local database where practical.

### Commit

```text
build(backend): configure database and migrations
```

## Step 6: Add quality tooling

### Goal

Make formatting, linting, typing, and testing consistent.

### Requirements

Backend:

- Ruff formatting;
- Ruff linting;
- Python type checking;
- pytest.

Frontend:

- formatting;
- ESLint;
- TypeScript type checking;
- Vitest.

Repository:

- `.pre-commit-config.yaml`;
- fast checks for whitespace, EOF, YAML, backend formatting and linting, and practical frontend checks;
- clear commands for format, lint, type-check, test, and build.

Do not introduce a complex task runner without a demonstrated need.

### Verification

Run all configured repository checks.

### Commit

```text
build: add repository quality tooling
```

## Step 7: Add GitHub Actions

### Goal

Run quality checks on pull requests and pushes to `main`.

### Requirements

Create workflows under `.github/workflows/`.

Backend CI should run dependency installation, formatting verification, linting, type checking, and tests.

Frontend CI should run lockfile-based dependency installation, formatting verification, linting, type checking, tests, and production build.

Only add a PostgreSQL CI service when a current test requires it.

Use trusted, pinned or major-version-pinned actions.

### Verification

Validate workflow syntax locally where possible, then inspect the actual GitHub Actions result after pushing.

### Commit

```text
ci: add backend and frontend quality checks
```

## Step 8: Document local development

### Goal

Allow a developer or coding agent to run TrackSea without relying on chat history.

### Requirements

Update the README and/or add:

```text
docs/development/local-development.md
```

Document prerequisites, environment setup, Docker startup, supported non-Docker startup, migrations, tests, linting, formatting, type checking, builds, troubleshooting, shutdown, and reset procedures.

Every command must match the implementation.

Do not document unimplemented deployment processes.

### Commit

```text
docs: add local development guide
```

## Step 9: Final validation

From a clean working tree:

1. Copy `.env.example` to the local environment file.
2. Build and start the complete Docker stack.
3. Confirm database health.
4. Confirm the backend health endpoint.
5. Confirm the frontend loads.
6. Run backend formatting, linting, typing, and tests.
7. Run frontend formatting, linting, typing, tests, and build.
8. Run pre-commit across all files.
9. Review the complete diff from `main`.

Confirm that no business features, domain models, secrets, or cloud-provider coupling were introduced.

Fix only issues within Sprint 1 scope.

## Step 10: Open the draft pull request

Use the title:

```text
build: establish repository technical foundation
```

The PR body must include:

- Sprint 1 objective;
- summary by backend, frontend, database, Docker, tooling, CI, and documentation;
- commit list;
- commands run;
- test and build results;
- migration behavior;
- local startup instructions;
- assumptions;
- known limitations;
- unresolved risks; and
- explicit confirmation that no TrackSea business features were implemented.

Keep the PR as a draft until the Definition of Done is satisfied.

Use a normal merge commit after approval so the meaningful Sprint 1 commits remain visible.

## Recommended execution pattern

Do not ask Codex to complete the entire playbook in one pass.

Use staged instructions such as:

```text
Read `.ai/playbooks/sprint-1-repository-bootstrap.md`. Complete Step 0 only. Do not modify files. Report the repository assessment and proposed structure.
```

Then continue one step at a time, reviewing the result before authorizing the next step.
