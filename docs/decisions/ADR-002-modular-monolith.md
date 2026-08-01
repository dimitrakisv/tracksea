# ADR-002: Start with a modular monolith

- Status: Accepted
- Date: 2026-08-01

## Context

TrackSea is beginning as a low-cost, web-first MVP maintained by a small team with AI-assisted development. The project needs clear domain boundaries, straightforward local development, simple deployment, and room to grow without introducing unnecessary operational complexity.

The main backend domains are expected to include users, observations, taxonomy, identifications, Marine Life, media, exports, and moderation.

## Decision

Build TrackSea as a modular monolith.

The backend is deployed as one application, but its internal modules must have explicit responsibilities and boundaries. Modules may share one PostgreSQL database initially, but domain logic should not be coupled through arbitrary cross-module access.

Suggested modules include:

- users;
- observations;
- taxonomy;
- identifications;
- marine_life;
- media;
- exports;
- moderation; and
- shared infrastructure.

Each module should own its domain services, API boundaries, persistence logic, and tests where practical.

## Why

- One deployment unit keeps hosting and operations inexpensive.
- One local environment is easier to understand and run.
- Integration testing is simpler.
- Debugging is easier with one application and one primary datastore.
- AI coding agents can reason about one coherent repository more reliably than many distributed services.
- Explicit module boundaries preserve a path to later extraction if evidence justifies it.

## Alternatives considered

### Microservices from the start

Rejected for the MVP because they would add service discovery, network failure modes, distributed tracing, inter-service authentication, more CI/CD pipelines, and higher operating cost before TrackSea has proven scale or team ownership needs.

### Unstructured monolith

Rejected because a single application without clear boundaries would encourage domain logic to spread across routes, models, and utilities, making future maintenance and extraction difficult.

### Multiple deployable services in one repository

Not selected initially because it retains much of the operational complexity of microservices without a demonstrated benefit for the MVP.

## Consequences

### Positive

- Faster development and onboarding.
- Lower infrastructure cost.
- Easier local development and testing.
- Clearer context for AI-assisted implementation.
- Simpler transactions for workflows spanning observations and identifications.

### Negative

- The application is one deployment unit.
- Poor discipline could allow module boundaries to erode.
- Some modules may later require extraction work.
- Shared database access must be controlled deliberately.

## Boundary rules

- Route handlers remain thin.
- Domain rules stay inside the owning module.
- Modules communicate through explicit services or interfaces, not arbitrary imports.
- Cross-module database writes must be coordinated through domain services.
- Shared code must be genuinely generic; domain-specific logic does not belong in `shared`.
- New infrastructure must be justified by an actual requirement.

## Extraction criteria

A module should become an independent service only when evidence shows one or more of the following:

- materially different scaling requirements;
- independent deployment cadence;
- separate team ownership;
- security or compliance isolation;
- operational fault isolation; or
- a clear reduction in total system complexity.

Fashion, speculation, or theoretical future scale are not sufficient reasons.

## Review triggers

Revisit this decision when production evidence shows that the monolith is a material constraint, or when organizational ownership makes independent services clearly beneficial.
