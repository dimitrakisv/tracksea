# TrackSea

**A personal marine journal that powers open marine science.**

TrackSea helps swimmers, snorkellers, divers, surfers, fishers, sailors, photographers, and researchers record marine-life observations with location, time, photos, and community-supported identifications.

Every confirmed observation should become both:

- a meaningful personal discovery; and
- a reusable biodiversity record for research and conservation.

## Product direction

The first release is a web-first MVP focused on:

- user accounts and observer attribution;
- observations with photos and geolocation;
- species and higher-taxon search;
- unknown-species submissions;
- community identifications and agreements;
- auditable identification history;
- a personal Marine Life list; and
- Darwin Core-compatible export mapping.

Forums, native mobile apps, AI identification, XP, levels, badges, and leaderboards are intentionally deferred.

## Technology direction

- Python 3.12+
- FastAPI
- SQLAlchemy 2 and Alembic
- PostgreSQL with PostGIS
- React with TypeScript
- Docker Compose
- S3-compatible object storage
- AWS Lightsail for the initial low-cost deployment

## Repository knowledge base

Before contributing, read:

1. `AGENTS.md`
2. `docs/PROJECT_CONSTITUTION.md`
3. `docs/product/vision.md`
4. `docs/product/mvp-scope.md`
5. Relevant architecture and domain documents

The repository is designed for both human contributors and AI coding agents. Product boundaries, domain rules, architecture decisions, and implementation expectations are version controlled alongside the code.

## Current status

**Sprint 0 — Knowledge Base and Governance**

Application code has not started yet. The current work establishes the product, scientific, privacy, architecture, and AI collaboration rules that will guide implementation.

## Guiding principle

> Every meaningful feature should improve both the user's experience and the quality, coverage, transparency, or usefulness of the marine biodiversity dataset.

## License

A project license will be selected before public contributions or production release.
