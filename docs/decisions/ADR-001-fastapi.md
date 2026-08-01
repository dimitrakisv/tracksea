# ADR-001: Use FastAPI for the backend

- Status: Accepted
- Date: 2026-08-01

## Context

TrackSea needs a Python backend that supports typed HTTP APIs, validation, authentication, geospatial workflows, background work, and clear separation between transport and domain logic.

The maintainer is already familiar with Python and wants a stack that works well with React, Docker, PostgreSQL, and AI-assisted development.

## Decision

Use FastAPI as the backend web framework.

Use Pydantic models for request and response validation, SQLAlchemy 2 for persistence, and Alembic for schema migrations.

Keep route handlers thin. Domain rules must live in dedicated services or domain modules rather than inside FastAPI endpoints.

## Why

- Strong Python typing and validation improve correctness and AI-agent comprehension.
- Automatic OpenAPI generation supports frontend integration and future API clients.
- The framework is lightweight enough for a modular monolith.
- Async support is available where useful without requiring the entire codebase to be asynchronous.
- FastAPI integrates well with PostgreSQL, Docker, pytest, and modern Python tooling.
- The maintainer can work productively in the chosen language.

## Alternatives considered

### Django

Django provides a mature ORM, admin interface, authentication system, and broad ecosystem.

It was not selected because TrackSea currently benefits more from an API-first structure and explicit architectural boundaries than from Django's integrated application model. Django remains a valid future reconsideration if the project develops strong admin or content-management requirements.

### Flask

Flask is simple and flexible.

It was not selected because FastAPI provides stronger built-in typing, validation, dependency injection, and OpenAPI support for this API-focused project.

### Node.js backend

A TypeScript backend could share language and types with the frontend.

It was not selected because the maintainer is more familiar with Python and the scientific, geospatial, and data-processing ecosystem is a strong fit for TrackSea.

## Consequences

### Positive

- Clear API contracts.
- Productive Python development.
- Good fit for automated testing and generated clients.
- Strong validation at system boundaries.

### Negative

- Authentication, administration, and some conventions require more explicit design than in Django.
- Poorly structured FastAPI projects can place too much logic in route handlers, so architecture rules must be enforced.
- Async and sync patterns must be chosen deliberately to avoid unnecessary complexity.

## Review triggers

Revisit this decision only if:

- the framework becomes a material operational limitation;
- the team cannot maintain the architecture effectively;
- a different framework substantially reduces verified project risk; or
- product needs change enough to justify migration cost.
