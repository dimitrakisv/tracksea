# System Overview

## Architectural style

TrackSea begins as a modular monolith. The frontend, backend, database, object storage integration, and background jobs remain clearly separated by responsibility, but the core application is deployed and evolved as one coherent system.

This keeps the MVP understandable, inexpensive, and easy to run locally while preserving boundaries that can support future extraction if scale or team structure requires it.

## High-level components

```text
Browser
  |
  v
React application
  |
  v
FastAPI application
  |-- Authentication and users
  |-- Observations
  |-- Taxonomy
  |-- Identifications
  |-- Marine Life
  |-- Media
  |-- Exports
  |-- Moderation
  |
  +--> PostgreSQL + PostGIS
  +--> S3-compatible object storage
  +--> Background worker and queue, when required
```

## Frontend

The web frontend uses React with TypeScript.

Responsibilities include:

- public exploration views;
- authentication flows;
- observation creation and editing;
- species and higher-taxon search;
- identification and agreement workflows;
- personal Marine Life views; and
- administration or moderation views when introduced.

The frontend must not enforce scientific authority or coordinate privacy by itself. Those rules belong in the backend.

## Backend

The backend uses Python and FastAPI.

It exposes versioned HTTP APIs, validates external input, applies authorization, coordinates domain services, and persists data through repositories or equivalent data-access boundaries.

API route handlers should remain thin. Domain rules such as consensus, coordinate obscuring, and Marine Life qualification belong in dedicated services.

## Database

PostgreSQL is the primary system of record. PostGIS provides geospatial types and queries.

The database stores users, observations, taxa, common names, identifications, agreements, verifications, media metadata, privacy settings, audit events, and Marine Life entries.

Schema changes are managed through Alembic migrations.

## Object storage

Observation images and generated derivatives are stored in S3-compatible object storage rather than in PostgreSQL.

The media pipeline should support quarantine, validation, metadata removal, safe re-encoding, thumbnails, and licensing metadata.

## Background work

The MVP may initially process lightweight work synchronously. A worker and queue should be introduced only where required for tasks such as:

- image processing;
- export generation;
- notifications;
- duplicate checks; and
- scheduled maintenance.

## Darwin Core adapter

TrackSea uses its own domain model internally.

A separate adapter converts eligible observations into Darwin Core-compatible export records. Darwin Core terms must not leak into the user-facing form or dictate the internal application model.

## Deployment

The initial deployment target is a low-cost AWS Lightsail instance running Docker containers, with S3-compatible storage for media and backups.

A reverse proxy terminates TLS and routes requests to the frontend and API.

The system should remain portable to DigitalOcean, another virtual server, or a managed container platform because application services are packaged with Docker.

## Environments

TrackSea should maintain separate configuration for:

- local development;
- automated tests;
- staging; and
- production.

Secrets are injected through environment configuration or a secrets manager and are never committed.

## Evolution rules

- Do not introduce microservices without a demonstrated operational or ownership need.
- Do not add infrastructure that cannot be justified by an MVP requirement.
- Preserve domain boundaries even while running as a monolith.
- Prefer portable standards and containers over provider-specific coupling.
- Record significant architectural changes as ADRs.
