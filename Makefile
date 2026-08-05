UV ?= uv
UVX ?= uvx
NPM ?= npm
DOCKER_COMPOSE ?= docker compose

.PHONY: format format-check lint type-check test build pre-commit

format:
	cd backend && $(UV) run ruff format .
	cd frontend && $(NPM) run format:write

format-check:
	cd backend && $(UV) run ruff format --check .
	cd frontend && $(NPM) run format

lint:
	cd backend && $(UV) run ruff check .
	cd frontend && $(NPM) run lint

type-check:
	cd backend && $(UV) run mypy
	cd frontend && $(NPM) run type-check

test:
	cd backend && $(UV) run pytest
	cd frontend && $(NPM) run test

build:
	cd frontend && $(NPM) run build
	$(DOCKER_COMPOSE) --env-file .env.example build backend frontend

pre-commit:
	$(UVX) --from pre-commit==3.5.0 pre-commit run --all-files
