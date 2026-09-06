# Local Development

This guide describes how to run TrackSea locally for Sprint 1 repository foundation work. It documents only the development setup that exists in this repository.

## Prerequisites

Use WSL 2 on Windows or a Linux environment with:

- Git
- Docker Desktop with WSL integration enabled
- Docker Compose
- Python 3.12
- `uv`
- Node.js 24 and npm
- `make`

Verify the tools:

```bash
git --version
docker --version
docker compose version
uv --version
cd backend && uv run python --version && cd ..
node --version
npm --version
make --version
```

## Clone and Open in WSL

Clone the repository and enter it from WSL. This SSH command requires a GitHub
SSH key that has access to the repository:

```bash
git clone git@github.com:dimitrakisv/tracksea.git
cd tracksea
```

If the repository already exists locally:

```bash
cd ~/projects/tracksea
git status --short --branch
```

## Environment Setup

Create the local environment file from safe placeholders:

```bash
cp .env.example .env
```

Do not commit `.env`. It is ignored by Git and is for local values only.

### Optional Google sign-in

Real Google sign-in requires an OAuth 2.0 Web application client in Google
Cloud. Add this authorized JavaScript origin to that client:

```text
http://localhost:5173
```

Set both identifiers to the same Web client ID in the local, untracked `.env`:

```dotenv
GOOGLE_CLIENT_ID=<same-web-client-id>
VITE_GOOGLE_CLIENT_ID=<same-web-client-id>
```

The browser-visible client ID is not a secret, and this credential-callback
flow does not use a Google client secret. Do not commit real local values.
Google sign-in remains optional when the identifiers are empty. Restart the
backend and frontend containers after changing them:

```bash
docker compose --env-file .env up --build -d backend frontend
```

## Docker Startup

Start the full local stack:

```bash
docker compose --env-file .env up --build -d
```

Check services:

```bash
docker compose --env-file .env ps
```

Verify the backend:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
```

Verify the frontend:

```bash
curl -fsS http://127.0.0.1:5173
```

Verify PostGIS:

```bash
docker compose --env-file .env exec -T postgres psql -U tracksea -d tracksea -c 'SELECT postgis_version();'
```

## Backend Without Docker

Install backend dependencies:

```bash
cd backend
uv sync --locked
```

Run the backend against the Docker PostgreSQL service exposed on the host:

```bash
DATABASE_URL=postgresql+psycopg://tracksea:tracksea_dev_password@127.0.0.1:5432/tracksea uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
```

Check the health endpoint:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
```

## Frontend Without Docker

Install frontend dependencies:

```bash
cd frontend
npm ci
```

Run the frontend:

```bash
npm run dev -- --host 0.0.0.0
```

Check that Vite responds:

```bash
curl -fsS http://127.0.0.1:5173
```

## Database Migrations

Run Alembic from the backend directory:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://tracksea:tracksea_dev_password@127.0.0.1:5432/tracksea uv run alembic current
DATABASE_URL=postgresql+psycopg://tracksea:tracksea_dev_password@127.0.0.1:5432/tracksea uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://tracksea:tracksea_dev_password@127.0.0.1:5432/tracksea uv run alembic downgrade base
```

The current Sprint 1 migration history is empty, so `upgrade head` and `downgrade base` are safe no-ops.

## Formatting

Format backend and frontend files:

```bash
make format
```

Check formatting without writing changes:

```bash
make format-check
```

## Linting

Run backend Ruff linting and frontend ESLint:

```bash
make lint
```

## Type Checking

Run backend mypy and frontend TypeScript checks:

```bash
make type-check
```

## Tests

Run backend pytest and frontend Vitest:

```bash
make test
```

## Frontend Production Build

Build the frontend production bundle:

```bash
cd frontend
npm run build
```

The repository build target also builds frontend assets and backend/frontend Docker images:

```bash
make build
```

## Pre-commit

Run all configured pre-commit hooks:

```bash
make pre-commit
```

The Makefile pins the pre-commit runner to a version compatible with the current WSL Git version.

## Stop Containers

Stop the local Docker stack without deleting volumes:

```bash
docker compose --env-file .env down
```

## Reset Local Database Volume

Warning: this deletes local PostgreSQL data, including the PostGIS database volume.

```bash
docker compose --env-file .env down -v
```

Start again after a reset:

```bash
docker compose --env-file .env up --build -d
```

## WSL and Docker Troubleshooting

If Docker is installed but containers cannot start from WSL, verify Docker Desktop WSL integration and restart WSL:

```powershell
wsl --shutdown
```

Then reopen WSL and verify:

```bash
docker --version
docker compose version
docker run --rm hello-world
```

If `localhost` does not resolve correctly in WSL, use `127.0.0.1`:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:5173
```

If `npm` resolves to a Windows path under `/mnt/c/`, use a native Linux Node.js install in WSL, such as `nvm`, and open a fresh shell:

```bash
node --version
npm --version
```

If Docker reports socket permission errors, restart Docker Desktop and WSL, then rerun:

```bash
docker run --rm hello-world
```
