# Sprint 3 Playbook: Observation Capture & Location Privacy

## Document status

This playbook is the authoritative staged implementation guide for TrackSea Sprint 3.

It is intended for both human contributors and AI coding agents, especially Codex. Read it together with the repository constitution, domain documentation, architecture decisions, engineering workflow, Definition of Done, and the completed Sprint 2 authentication implementation.

Do not execute the entire sprint in one pass. Complete one numbered step, stop, report, review, and only then continue.

---

## Objective

Create TrackSea's first marine-observation workflow on top of the authenticated Sprint 2 application.

Sprint 3 establishes the ability for an authenticated user to:

- record a marine encounter at a particular date, time, and place;
- submit the observation without knowing the taxon;
- optionally request identification help;
- record description, habitat, depth, quantity, and coordinate uncertainty where known;
- choose a location-privacy mode;
- keep exact coordinates separate from public coordinates;
- view their own observations in a list;
- view their own observations on a map;
- open an observation detail screen;
- correct editable observation metadata; and
- rely on backend authorization so one user cannot access another user's private observation data.

Sprint 3 must preserve the architectural distinction between an `Observation` and an `Identification`.

Sprint 3 deliberately does not implement taxonomy, observer identifications, community identifications, agreements, expert verification, Marine Life, Darwin Core export, or photo uploads.

Photos are deferred to a later media-focused sprint so ownership, geospatial persistence, privacy, and API boundaries are stable before upload/storage complexity is introduced.

---

## Product outcome

At the end of Sprint 3, a signed-in user should be able to say:

> I saw something in the sea, recorded when and where I saw it, kept control over location privacy, saved it even though I do not know what species it is, and can find it again in my observation journal and map.

This is the first TrackSea workflow that records real marine-domain data.

---

## Why this sprint follows authentication

Sprint 2 creates user identity and authenticated sessions.

Sprint 3 uses that identity to establish ownership and attribution of observations.

The intended dependency chain is:

1. user identity;
2. observation ownership;
3. observation media;
4. taxonomy and observer identifications;
5. community identifications and agreements;
6. expert verification;
7. Marine Life derivation;
8. privacy-safe public discovery and exports.

Do not invert this dependency chain without a new reviewed decision.

---

## Required reading

Before Step 0, and before any step that changes domain behavior, read the current versions of:

1. `AGENTS.md`
2. `docs/PROJECT_CONSTITUTION.md`
3. `docs/product/vision.md`
4. `docs/product/mvp-scope.md`
5. `docs/domain/domain-model.md`
6. `docs/domain/identification-workflow.md`
7. `docs/architecture/system-overview.md`
8. `docs/decisions/ADR-001-fastapi.md`
9. `docs/decisions/ADR-002-modular-monolith.md`
10. `docs/decisions/ADR-003-authentication-and-sessions.md`
11. `docs/engineering/git-workflow.md`
12. `docs/engineering/definition-of-done.md`
13. `docs/development/local-development.md`
14. `.ai/README.md`
15. `.ai/playbooks/implement-feature.md`
16. `.ai/playbooks/sprint-2-authentication.md`
17. this playbook.

If a referenced Sprint 2 file was renamed during implementation, locate its current equivalent instead of creating a duplicate.

---

## Preconditions

Do not start implementation until:

- Sprint 2 authentication is merged into `main`;
- local `main` is updated;
- authentication CI is green;
- registration/login/session behavior works locally;
- the working tree is clean.

If Sprint 2 is not merged, stop and report that Sprint 3 is blocked.

---

## Branch strategy

Create from the latest `main`:

```text
feat/observation-capture
```

Use one pull request for Sprint 3 while preserving meaningful semantic commits.

Recommended PR title:

```text
feat(observations): add observation capture workflow
```

Keep the PR as draft until final validation passes.

Do not merge before Steps 24 and 25 are complete.

Use a normal merge commit after approval so the semantic Sprint 3 commits remain visible.

---

## Global implementation rules

After every implementation step:

1. run the relevant checks;
2. inspect `git status`;
3. inspect the diff for unrelated changes;
4. create only the specified semantic commit unless a scoped fix is required;
5. push when instructed;
6. report files changed, commands run, results, migrations, privacy/security implications, assumptions, unresolved risks, and commit SHA.

Never claim a command passed unless it actually ran.

Never weaken a test just to make a step pass.

Do not add opportunistic unrelated cleanup.

### Architecture rules

Keep the modular monolith.

Do not introduce:

- microservices;
- Redis;
- Celery;
- Kafka;
- event buses;
- Kubernetes;
- Elasticsearch;
- GraphQL;
- CQRS infrastructure;
- a generic repository framework;
- a generic service framework;
- a second backend application;
- cloud-specific business logic.

Use the existing FastAPI app, SQLAlchemy/Alembic setup, PostgreSQL/PostGIS database, React frontend, Docker Compose stack, and quality tooling.

### Domain rules

An `Observation` records an encounter.

An `Identification` records a user's taxonomic proposal.

Therefore:

- do not add `species_id` directly to observations;
- do not add `taxon_id` directly to observations;
- do not add `confirmed_species` to observations;
- do not create identification tables in this sprint;
- an observation must remain valid with no taxon at all.

Unknown observations are first-class records.

### Authorization rules

Every Sprint 3 observation belongs to exactly one authenticated observer.

The backend must enforce ownership.

Do not rely on:

- hidden frontend links;
- disabled buttons;
- guessed UUID secrecy;
- client-provided observer IDs.

The authenticated user is the observer.

Create payloads must not allow the browser to choose another `observer_id`.

A user must not be able to read or mutate another user's owner-only observation endpoints.

### Privacy rules

Location privacy is a backend responsibility.

The application must store exact and public coordinates separately.

Never expose exact coordinates from a schema or endpoint intended for public use.

Do not trust the frontend to strip sensitive fields.

Do not derive public coordinates only at render time.

Persist the public representation so it remains stable and auditable.

### Geospatial rules

Use PostGIS.

Use WGS 84 longitude/latitude semantics with SRID 4326.

Do not store location as arbitrary text such as `"37.9,23.7"`.

Use explicit API field names:

```text
latitude
longitude
```

When constructing geometry, coordinate order is:

```text
longitude, latitude
```

Test this explicitly.

### Time rules

`observed_at` represents when the encounter occurred, not when the row was inserted.

Require timezone-aware input.

Normalize persistence/output consistently.

Do not silently treat timezone-naive input as UTC.

Keep `created_at` and `updated_at` separate from `observed_at`.

---

## Sprint 3 scope

### In scope

- Observation module boundary.
- Observation database model.
- PostGIS point storage.
- Exact coordinates.
- Public coordinates.
- Location visibility/privacy state.
- Coordinate uncertainty.
- Observation date/time.
- Description.
- Habitat.
- Depth.
- Quantity.
- Identification-help request flag.
- Ownership.
- Owner-only creation endpoint.
- Owner-only list endpoint.
- Owner-only detail endpoint.
- Owner-only update endpoint.
- Pagination.
- Basic filtering.
- Public-safe serialization boundary.
- React observation API client.
- Observation creation form.
- Browser geolocation helper.
- Observation journal/list.
- Observation detail page.
- Observation editing.
- Personal observation map.
- Authorization/privacy tests.
- Migration and PostGIS tests.
- CI changes required for database-backed tests.
- Developer documentation.

### Explicitly out of scope

Do not implement:

- photo upload;
- image processing;
- object storage;
- S3 integration;
- MinIO;
- taxonomy tables;
- taxonomic search;
- observer taxon selections;
- identifications;
- agreements;
- community consensus;
- expert verification;
- Marine Life;
- public observation feed;
- public user profiles;
- comments;
- likes;
- bookmarks;
- notifications;
- direct messages;
- exports;
- Darwin Core adapter;
- AI identification;
- reverse geocoding;
- offline mode;
- native mobile;
- moderation;
- complex spatial search;
- heat maps;
- clustering infrastructure;
- production deployment changes.

If a step appears to require an out-of-scope feature, stop and report instead of expanding the sprint.

---

# Observation domain design

The following is the intended Sprint 3 model. Step 0 must inspect existing conventions and may propose small naming adjustments, but it must not weaken the invariants.

## Observation fields

Suggested conceptual fields:

```text
id
observer_id
observed_at
exact_location
public_location
location_visibility
coordinate_uncertainty_m
description
habitat
depth_m
quantity
needs_identification
created_at
updated_at
```

Do not add speculative future fields.

### `id`

Use the repository's established UUID strategy.

### `observer_id`

Required foreign key to the authenticated user.

Must not come from the request body.

### `observed_at`

Required and timezone-aware.

Represents the encounter time.

### `exact_location`

Required Sprint 3 PostGIS point using SRID 4326.

Contains the actual observer-submitted location.

Owner/private data.

### `public_location`

Nullable PostGIS point with the same SRID.

Derived by backend privacy logic.

Must not be directly writable by API clients.

### `location_visibility`

Use an explicit constrained value or enum:

```text
public
obscured
private
```

Semantics:

- `public`: public location may equal exact location;
- `obscured`: public location is coarser than exact location;
- `private`: public location is absent.

Do not reduce this to a boolean `is_private`.

### `coordinate_uncertainty_m`

Optional non-negative numeric value.

Represents uncertainty in the recorded exact coordinate.

It is not a privacy mechanism.

### `description`

Optional free text.

Trim surrounding whitespace and apply a documented maximum length.

### `habitat`

Optional concise free text in Sprint 3.

Do not build a habitat taxonomy yet.

### `depth_m`

Optional non-negative decimal/numeric value.

Do not store depth as formatted text.

### `quantity`

Optional positive integer.

Do not force users to estimate quantity.

### `needs_identification`

Boolean.

Allows an unknown observation to request help in a future identification sprint.

This sprint does not build the community queue.

### `created_at` / `updated_at`

Server controlled.

---

# Location privacy policy

Marine observations may reveal personal movement, fishing locations, sensitive habitats, vulnerable species, or private access points.

## Public

```text
public_location = exact_location
```

## Obscured

The public point must be stable but intentionally coarser than the exact point.

Implement obscuring behind a dedicated backend service, not inline in a router.

Recommended MVP strategy:

1. accept exact latitude/longitude;
2. place the point into a configurable geographic grid;
3. calculate the center of that grid cell;
4. persist the center as `public_location`;
5. keep exact location unchanged.

A simple initial value around `0.1` degrees may be used if Step 0 confirms it and ADR-004 documents it as an MVP compromise.

Tests must prove:

- public coordinate is backend-generated;
- same exact point/config gives the same obscured point;
- exact-location changes recalculate public location;
- visibility changes recalculate/remove public location;
- public-safe serializers never expose exact location.

Do not claim that coarse-grid obscuring guarantees anonymity.

## Private

```text
public_location = NULL
```

A public-safe serializer must not fall back to exact location.

## Default

Prefer a privacy-conscious default:

```text
obscured
```

unless current approved product documentation says otherwise.

---

# API boundary

Use the existing `/api/v1` convention.

Suggested endpoints:

```text
POST   /api/v1/observations
GET    /api/v1/observations
GET    /api/v1/observations/{observation_id}
PATCH  /api/v1/observations/{observation_id}
```

Do not add a public feed in Sprint 3.

Do not add deletion unless Step 0 finds an already-approved requirement.

## Owner create payload

Example:

```json
{
  "observed_at": "2026-08-28T18:42:00+03:00",
  "latitude": 37.9,
  "longitude": 23.7,
  "location_visibility": "obscured",
  "coordinate_uncertainty_m": 20,
  "description": "Small animal observed near rocks.",
  "habitat": "rocky shallow coast",
  "depth_m": 2.5,
  "quantity": 1,
  "needs_identification": true
}
```

The payload must not accept:

```text
observer_id
public_location
created_at
updated_at
taxon_id
species_id
identification_id
verification_status
```

## Owner response

Owner-only responses may contain exact coordinates because the authenticated owner is authorized to see them.

Do not leak ORM geometry objects directly.

## Public-safe boundary

Even though Sprint 3 does not expose a public feed, define a deliberately separate public-safe schema/mapper.

It must never contain exact coordinates or private account data.

For private observations, public location must be absent.

---

# Frontend product flow

```text
Authenticated application
        |
        +-- New observation
        |
        +-- My observations
               |
               +-- List
               |
               +-- Map
               |
               +-- Detail
                      |
                      +-- Edit
```

Keep the UI simple and accessible.

Do not attempt final branding in this sprint.

---

# Recommended step sequence

```text
Step 0   Inspect and design
Step 1   Record observation/location privacy decision
Step 2   Establish observation backend module
Step 3   Add geospatial dependency and model
Step 4   Add observation database migration
Step 5   Implement location privacy service
Step 6   Add observation schemas and validation
Step 7   Add observation repository/service boundary
Step 8   Add authenticated observation creation
Step 9   Add owner observation list
Step 10  Add owner observation detail
Step 11  Add owner observation update
Step 12  Add public-safe serialization boundary
Step 13  Add backend authorization/privacy tests
Step 14  Add PostGIS integration/migration tests
Step 15  Update CI for database-backed tests
Step 16  Add frontend observation API client
Step 17  Add observation creation form
Step 18  Add browser geolocation helper
Step 19  Add observation journal/list
Step 20  Add observation detail and edit flow
Step 21  Add personal observation map
Step 22  Add frontend workflow tests
Step 23  Update developer/domain documentation
Step 24  End-to-end local validation
Step 25  Final scope/privacy/architecture review
Step 26  Complete draft pull request
```

---

# Step 0: Inspect and design

## Goal

Understand the post-Sprint-2 repository before changing it and confirm how observations fit into the modular monolith.

## Actions

Read all required documents.

Inspect:

- backend application structure;
- authentication/user module;
- SQLAlchemy model conventions;
- UUID conventions;
- timestamp conventions;
- API router registration;
- Pydantic schema conventions;
- service/repository patterns;
- database-test infrastructure;
- frontend routing;
- authentication context/state;
- frontend API client patterns;
- test setup;
- Docker Compose;
- environment settings;
- CI workflow.

Confirm:

- branch is based on latest `main`;
- working tree is clean;
- Sprint 2 migrations are applied;
- authenticated current-user behavior works;
- PostGIS remains available.

## Required report

Before modifying files, report:

1. proposed backend module structure;
2. proposed Observation SQLAlchemy model and SQL types;
3. proposed PostGIS/GeoAlchemy integration;
4. exact/public coordinate representation;
5. privacy-obscuring algorithm;
6. owner API payloads/responses;
7. public-safe schema boundary;
8. pagination strategy;
9. frontend routes/screens;
10. CI/database-test changes;
11. likely files changed in Steps 1-26;
12. unresolved risks.

## Expected module shape

Adapt to existing conventions, but likely:

```text
backend/app/observations/
├── __init__.py
├── models.py
├── schemas.py
├── repository.py
├── service.py
├── privacy.py
└── router.py
```

Do not create abstractions merely to match this tree.

## Modification rule

No file changes unless fixing a blocking documentation error.

## Commit

None expected.

## Stop condition

Stop after reporting the design. Do not begin Step 1.

---

# Step 1: Record observation and location privacy decision

## Goal

Record the decision that exact and public coordinates are separate and backend-enforced.

## Create

```text
docs/decisions/ADR-004-observation-location-privacy.md
```

If an equivalent ADR exists, update/use it rather than duplicating it.

## Requirements

Document:

- context;
- decision;
- alternatives considered;
- consequences;
- exact/public separation;
- visibility modes;
- initial obscuring strategy;
- backend ownership/authorization;
- why the browser cannot choose the public coordinate;
- why Observation remains separate from Identification;
- future evolution for sensitive taxa/location rules.

Explicitly state that the MVP obscuring method is not a guarantee of anonymity.

## Out of scope

No code or migrations.

## Verification

Run markdown/pre-commit checks relevant to documentation.

## Commit

```text
docs: record observation location privacy decision
```

## Stop condition

Commit, push, and report.

---

# Step 2: Establish the observation backend module

## Goal

Create the module boundary without implementing persistence yet.

## Requirements

Create the observation package following current backend conventions.

Likely files:

```text
backend/app/observations/__init__.py
backend/app/observations/router.py
backend/app/observations/schemas.py
backend/app/observations/service.py
backend/app/observations/repository.py
backend/app/observations/privacy.py
```

Keep files minimal.

Do not add fake endpoints or speculative abstractions.

## Out of scope

- ORM model;
- migration;
- endpoints;
- frontend.

## Verification

Run backend format, lint, type checking, and tests.

## Commit

```text
build(observations): establish observation module
```

## Stop condition

Commit, push, report.

---

# Step 3: Add geospatial dependency and Observation model

## Goal

Introduce the persistence model and PostGIS point types.

## Requirements

Add the minimum SQLAlchemy/PostGIS integration dependency if not already present.

Prefer established integration such as GeoAlchemy2 when appropriate.

Define `Observation` with the approved Step 0 fields.

Required invariants:

- observer FK required;
- observed time required;
- exact Point/SRID 4326 required;
- public Point/SRID 4326 nullable;
- visibility constrained;
- uncertainty non-negative if present;
- depth non-negative if present;
- quantity positive if present;
- timestamps server controlled;
- no taxon/species column.

Add only relationships useful now.

Consider indexes on observer, observed time, and spatial point only when justified.

## Verification

Backend quality checks and tests.

## Commit

```text
feat(observations): add observation persistence model
```

## Stop condition

Commit, push, report dependency/schema decisions.

---

# Step 4: Add the Observation migration

## Goal

Create a reversible Alembic migration.

## Requirements

Generate and inspect migration carefully.

It must:

- create observation table;
- create enum/check constraints;
- add user FK;
- add timestamps;
- add geometry columns with correct SRID;
- add justified indexes;
- downgrade cleanly;
- avoid unrelated authentication-table changes.

If PostGIS extension lifecycle is already managed elsewhere, do not duplicate it carelessly.

## Verification

Against a disposable/local DB:

1. start from Sprint 2 schema;
2. `alembic current`;
3. `alembic upgrade head`;
4. inspect table and geometry metadata;
5. `alembic downgrade -1`;
6. confirm only Sprint 3 schema is removed;
7. `alembic upgrade head` again;
8. run backend tests.

## Commit

```text
db(observations): add observation schema
```

## Stop condition

Commit, push, report migration revision and results.

---

# Step 5: Implement location privacy service

## Goal

Centralize exact-to-public location behavior.

## Requirements

Implement focused behavior for:

```text
public
obscured
private
```

The router must not implement privacy calculations directly.

### Public

Public point equals exact point.

### Obscured

Generate a stable coarse public point using the Step 0/ADR-approved algorithm.

If using a grid:

- grid size configurable;
- coordinate ordering documented;
- bounds handled;
- positive and negative coordinates tested;
- boundary cells tested.

Do not use random jitter on every response.

### Private

No public point.

## Recalculation

The service must be used on create and whenever exact location/visibility changes.

## Tests

Cover all modes, stability, changes, bounds, and a regression assertion that a representative obscured point is not simply the exact point.

## Verification

Backend checks/tests.

## Commit

```text
feat(observations): add location privacy service
```

## Stop condition

Commit, push, report algorithm/config.

---

# Step 6: Add observation schemas and validation

## Goal

Define explicit safe API contracts.

## Suggested schemas

```text
ObservationCreate
ObservationUpdate
ObservationOwnerRead
ObservationPublicRead
ObservationListItem
ObservationLocation
```

Adapt names to project conventions.

## Create validation

Validate:

- timezone-aware observed time;
- latitude;
- longitude;
- visibility;
- uncertainty;
- description;
- habitat;
- depth;
- quantity.

Reject server-only fields.

Do not accept observer ID, public location, taxon, species, or verification status.

## Update validation

Use true partial semantics and distinguish omitted fields from explicit nulls.

## Strings

Trim where appropriate and document maximum lengths without destructively normalizing free text.

## Owner/Public separation

Owner schema may contain exact coordinates.

Public schema must never contain them.

## Tests

Add valid/invalid payload tests.

## Verification

Backend format/lint/type/test.

## Commit

```text
feat(observations): add observation API schemas
```

## Stop condition

Commit, push, report validation decisions.

---

# Step 7: Add observation repository and service behavior

## Goal

Keep persistence and domain orchestration out of routers.

## Repository responsibilities

At minimum:

- create;
- get for owner;
- list for owner;
- update.

Do not create a generic base repository.

## Service responsibilities

At minimum:

- bind authenticated observer;
- build exact geometry;
- compute public geometry;
- coordinate update behavior;
- enforce ownership/business rules;
- map output safely where appropriate.

## Query discipline

Use current SQLAlchemy 2 style.

Default stable ordering:

```text
observed_at DESC
id DESC
```

Avoid N+1 behavior.

## Verification

Backend checks and focused tests.

## Commit

```text
feat(observations): add observation persistence service
```

## Stop condition

Commit, push, report query behavior.

---

# Step 8: Add authenticated observation creation

## Goal

Allow a signed-in user to create an unknown observation.

## Endpoint

```text
POST /api/v1/observations
```

## Authentication

Reuse the Sprint 2 current-user/session dependency.

Anonymous requests fail using existing auth conventions.

## Behavior

Backend:

1. authenticates;
2. validates payload;
3. binds current user as observer;
4. creates exact point;
5. derives public point;
6. persists;
7. returns owner-safe representation.

## Tests

Cover:

- authenticated success;
- anonymous failure;
- all three visibility modes;
- invalid lat/lon;
- naive datetime;
- negative depth;
- invalid quantity;
- observer spoof attempt;
- public-location injection attempt;
- taxon-free observation accepted.

Respect Sprint 2 CSRF behavior for state-changing cookie-auth requests.

## Verification

Backend checks and PostGIS-backed integration where required.

## Commit

```text
feat(observations): add observation creation
```

## Stop condition

Commit, push, report endpoint/tests.

---

# Step 9: Add owner observation list

## Goal

Allow a signed-in user to view their own journal.

## Endpoint

```text
GET /api/v1/observations
```

## Requirements

Return only authenticated user's observations.

Add bounded predictable pagination.

Offset/limit is acceptable for MVP if documented.

Useful filters only:

- observed date range;
- needs identification;
- visibility.

No generic query language.

## Sorting

Newest observed encounter first with deterministic tie-breaker.

## Tests

With users A and B prove:

- A sees only A;
- B never leaks into A list;
- pagination works;
- ordering stable;
- filters remain owner-scoped.

## Verification

Backend checks.

## Commit

```text
feat(observations): add owner observation list
```

## Stop condition

Commit, push, report pagination/filter design.

---

# Step 10: Add owner observation detail

## Goal

Allow owner to open one observation.

## Endpoint

```text
GET /api/v1/observations/{observation_id}
```

## Authorization

Only owner may access owner detail.

Preserve existing security convention for inaccessible resources, including 404-vs-403 behavior.

## Tests

Cover owner success, anonymous failure, cross-user denial, unknown UUID, malformed ID behavior, exact location available to owner, and no private account-field leak.

## Verification

Backend checks.

## Commit

```text
feat(observations): add owner observation detail
```

## Stop condition

Commit, push, report authorization behavior.

---

# Step 11: Add owner observation update

## Goal

Allow correction of observation metadata.

## Endpoint

```text
PATCH /api/v1/observations/{observation_id}
```

## Editable fields

May include:

- observed time;
- latitude;
- longitude;
- visibility;
- uncertainty;
- description;
- habitat;
- depth;
- quantity;
- needs-identification.

Never allow:

- id;
- observer ID;
- direct public location;
- created time;
- taxon;
- verification state.

## Location recalculation

Recompute public location if exact coordinate or visibility changes.

## Tests

Cover partial update, null semantics, all visibility transitions, unauthorized user, invalid values, immutable-field rejection, and stale-public-location prevention.

## Verification

Backend checks.

## Commit

```text
feat(observations): add observation updates
```

## Stop condition

Commit, push, report update semantics.

---

# Step 12: Add public-safe serialization boundary

## Goal

Prevent future public APIs from accidentally leaking exact coordinates.

## Requirements

Implement explicit public-safe representation.

Do not add a public feed yet.

Do not reuse owner schema and delete keys dynamically.

Public-safe output:

- uses `public_location`;
- omits exact location entirely;
- has no location for private observations;
- omits private account/email data.

## Tests

Prove:

- exact-latitude key absent;
- exact-longitude key absent;
- private has no fallback location;
- obscured uses obscured point;
- public uses public point;
- user email cannot leak.

Prefer structural assertions over only snapshot tests.

## Verification

Backend checks.

## Commit

```text
feat(observations): add public-safe observation representation
```

## Stop condition

Commit, push, report privacy assertions.

---

# Step 13: Add backend authorization and privacy regression tests

## Goal

Concentrate high-value security tests.

## Required matrix

Use two authenticated users.

### Create

- current identity decides observer;
- client cannot spoof another observer.

### List

- A never receives B data.

### Detail

- A cannot read B observation.

### Update

- A cannot update B observation.

### Location

- owner gets authorized exact point;
- public-safe output never gets exact point;
- private has no public point;
- visibility/location changes recalculate correctly.

### Session

Expired/revoked session cannot create/read/update.

### CSRF

POST/PATCH obey Sprint 2 CSRF protection.

Do not bypass existing security middleware for convenience.

## Verification

Focused tests plus full backend suite.

## Commit

```text
test(observations): cover ownership and location privacy
```

## Stop condition

Commit, push, report matrix/results.

---

# Step 14: Add PostGIS and migration integration tests

## Goal

Verify real geospatial behavior.

## Requirements

Use PostgreSQL with PostGIS, not SQLite.

Test:

- migration from Sprint 2 to Sprint 3;
- point persistence;
- SRID;
- longitude/latitude round trip;
- exact/public separation;
- FK behavior;
- DB constraints;
- downgrade where practical.

Tests must isolate and clean data deterministically.

## Verification

Run documented database-backed test command.

## Commit

```text
test(observations): add PostGIS integration coverage
```

## Stop condition

Commit, push, report DB setup/results.

---

# Step 15: Update CI for database-backed backend tests

## Goal

Run observation/PostGIS tests in GitHub Actions.

## Requirements

Sprint 1 intentionally skipped a database service until tests needed one. Sprint 3 now needs it.

Add a PostGIS-capable CI service/container or a dedicated integration job.

Use safe test-only credentials, health checks, explicit test DATABASE_URL, and migrations if required.

Do not add production secrets or cloud DB dependencies.

Keep CI understandable and reasonably fast.

## Verification

Validate YAML locally where practical, push, and inspect actual remote Actions.

Do not call complete until remote CI is green.

## Commit

```text
ci: run observation tests with PostGIS
```

## Stop condition

Commit, push, report workflow run.

---

# Step 16: Add frontend observation API client

## Goal

Create typed frontend access to observation endpoints.

## Requirements

Follow Sprint 2 API-client conventions.

Implement typed calls for:

```text
create observation
list own observations
get own observation
update own observation
```

Reuse:

```text
credentials: "include"
```

and existing CSRF logic for writes.

Do not duplicate authentication fetch wrappers.

Avoid `any`.

Handle validation errors, expired sessions, inaccessible resource behavior, and network failures using current app conventions.

## Tests

Mock at the API boundary as existing frontend tests do.

## Verification

Frontend format/lint/type/test/build.

## Commit

```text
feat(frontend): add observation API client
```

## Stop condition

Commit, push, report API surface.

---

# Step 17: Add observation creation form

## Goal

Allow an authenticated user to record an unknown encounter.

## Route

Use an authenticated route such as:

```text
/observations/new
```

following current routing conventions.

## Fields

- observed date/time;
- latitude;
- longitude;
- visibility;
- optional uncertainty;
- optional description;
- optional habitat;
- optional depth;
- optional quantity;
- request-identification-help control.

No taxon field.

No photo upload yet.

## UX

Explain:

- exact location is stored privately;
- public/obscured/private choices;
- unknown observations are allowed.

Make "I don't know the species" a supported state, not an error.

## Validation

Useful client validation, backend remains authoritative.

## States

Handle idle, submitting, success, validation error, session failure, and network failure.

Prevent accidental duplicate submission while a request is active.

## Tests

Cover render, required fields, success, validation error, loading state, privacy options, and absence of a taxon field.

## Verification

Frontend full checks.

## Commit

```text
feat(frontend): add observation creation form
```

## Stop condition

Commit, push, report form behavior.

---

# Step 18: Add browser geolocation helper

## Goal

Make coordinate capture practical without making geolocation mandatory.

## Requirements

Add a clear user-triggered action such as:

```text
Use my current location
```

Use browser Geolocation API.

Do not request permission automatically on page load.

Handle:

- granted;
- denied;
- unavailable API;
- timeout;
- inaccurate location.

When reasonable, populate browser accuracy into coordinate uncertainty.

Do not overwrite manual coordinates without clear user action.

Do not send location to backend until form submission.

Do not continuously track location.

## Tests

Mock geolocation success/denial/unavailable cases.

## Verification

Frontend checks.

## Commit

```text
feat(frontend): add observation geolocation helper
```

## Stop condition

Commit, push, report permission behavior.

---

# Step 19: Add personal observation journal/list

## Goal

Give user a useful journal of recorded encounters.

## Route

```text
/observations
```

or current router equivalent.

## Requirements

Show:

- observed date/time;
- concise location/privacy indication;
- description/habitat summary;
- needs-identification status;
- detail link.

Handle loading, empty, error, and pagination states.

Empty state should guide the user to create their first observation.

Do not use fake data.

The list is owner-only in Sprint 3.

## Tests

Cover empty, populated, loading, error, pagination, navigation.

## Verification

Frontend checks/build.

## Commit

```text
feat(frontend): add observation journal
```

## Stop condition

Commit, push, report UI states.

---

# Step 20: Add observation detail and edit flow

## Goal

Allow owner to review and correct saved data.

## Routes

For example:

```text
/observations/:observationId
/observations/:observationId/edit
```

## Detail

Display:

- observed date/time;
- exact owner location;
- visibility;
- public location if present;
- uncertainty;
- description;
- habitat;
- depth;
- quantity;
- needs-identification;
- useful created/updated metadata.

Clearly distinguish exact location from public location.

## Edit

Reuse form parts where practical without over-generalizing.

Only fields allowed by PATCH are editable.

## Tests

Cover detail render, edit initialization, successful update, privacy/location update, and error state.

## Verification

Frontend checks.

## Commit

```text
feat(frontend): add observation detail and editing
```

## Stop condition

Commit, push, report routes/behavior.

---

# Step 21: Add personal observation map

## Goal

Let owner see observations spatially.

## Requirements

Add a simple map view associated with My Observations.

Use a lightweight open mapping approach consistent with licensing and low-cost goals.

Leaflet plus an OpenStreetMap-compatible tile source may be considered during implementation.

Do not add commercial map vendor lock-in without an ADR.

Because this is the authenticated owner's personal map, it may show exact owner coordinates.

Do not reuse owner-map payloads later as public-map payloads.

Support:

- markers;
- click marker to open/navigate to observation;
- empty state;
- basic fit-to-observations;
- accessible list/link alternative.

Do not implement heatmaps, advanced clustering, drawing tools, spatial analytics, public map, or reverse geocoding.

Document tile-source assumptions/limits.

## Tests

Test map integration logic without live network tile requests.

## Verification

Frontend checks/build and manual local browser verification.

## Commit

```text
feat(frontend): add personal observation map
```

## Stop condition

Commit, push, report dependency/manual verification.

---

# Step 22: Add frontend workflow tests

## Goal

Cover the observation workflow across frontend state/components.

## Scenarios

At minimum:

1. authenticated user opens new observation;
2. enters valid unknown observation;
3. submits;
4. sees saved result;
5. opens journal;
6. opens detail;
7. edits metadata;
8. handles expired session;
9. handles validation errors;
10. map receives expected locations.

Use current testing level.

Do not introduce a heavy browser E2E framework solely for this sprint unless Step 0 finds an existing decision requiring it.

## Accessibility checks

- form inputs labeled;
- validation understandable;
- privacy choices explained;
- submit loading/disabled state;
- map is not the only way to access observation information.

## Verification

Frontend tests/type/lint/build.

## Commit

```text
test(frontend): cover observation workflow
```

## Stop condition

Commit, push, report scenarios/results.

---

# Step 23: Update developer and domain documentation

## Goal

Make the implemented observation system understandable without chat history.

## Add/update

Add when useful:

```text
docs/development/observations.md
```

Update existing docs rather than duplicating authoritative domain text.

Document:

### Domain behavior

- Observation vs Identification;
- unknown observations;
- ownership;
- needs-identification flag.

### Fields

- observed time;
- exact/public locations;
- visibility;
- uncertainty;
- description;
- habitat;
- depth;
- quantity.

### Privacy

- public/obscured/private;
- backend enforcement;
- obscuring algorithm;
- limitations.

### API

Current endpoints and owner/public schema distinction.

### Development

- migration application;
- creating a test observation;
- PostGIS-backed tests;
- relevant env settings;
- map configuration;
- troubleshooting.

### Deferred work

Explicitly state no photos, taxonomy, identifications, public feed, or community review yet.

Update README current status only if needed.

## Verification

Run doc/pre-commit checks and manually verify commands match code.

## Commit

```text
docs: add observation development guide
```

## Stop condition

Commit, push, report docs changed.

---

# Step 24: End-to-end local validation

## Goal

Validate the complete Sprint 3 workflow in a realistic local environment.

This is validation, not a feature step.

Normally no commit.

## Clean start

From a clean working tree:

1. confirm feature branch;
2. confirm `.env`;
3. rebuild/start Docker stack;
4. confirm PostgreSQL health;
5. confirm PostGIS;
6. apply migrations;
7. confirm backend health;
8. confirm frontend loads.

## Authentication prerequisite

Using Sprint 2:

1. register/sign in;
2. confirm session;
3. confirm current-user endpoint.

## Observation validation

Create an observation with:

- timezone-aware observed time;
- lat/lon;
- obscured visibility;
- description;
- habitat;
- depth;
- quantity;
- needs identification enabled.

Confirm:

- correct owner in DB;
- exact geometry correct;
- obscured public geometry generated;
- journal shows observation;
- detail loads;
- personal map shows it;
- edit works.

Then change visibility to public and confirm public coordinate recalculates.

Then change to private and confirm public location becomes null.

Use browser geolocation where available and verify permission behavior.

## Two-user isolation

Create/sign in as a second user.

Confirm user B cannot:

- list A observation;
- read A owner detail;
- update A observation.

## Quality checks

Run repository commands equivalent to:

```text
make format-check
make lint
make type-check
make test
make build
make pre-commit
```

Use actual current command names if changed.

## Database scope check

Confirm no accidental tables for:

- taxonomy;
- identification;
- agreement;
- verification;
- Marine Life;
- media.

## Git review

Review complete diff from `main`.

## Commit

Normally none.

If validation reveals a Sprint 3 defect, make the smallest scoped semantic fix, rerun validation, push, and report.

## Stop condition

Report complete validation. Do not merge.

---

# Step 25: Final scope, privacy, and architecture review

## Goal

Perform final review before making the PR ready.

## Scope checklist

Confirm no taxonomy, identification workflow, media upload, public feed, gamification, or cloud-deployment expansion.

## Domain checklist

Confirm:

- observation always has observer;
- observation works without taxon;
- no final species field;
- needs-identification does not create Identification;
- observed time separate from row creation time.

## Privacy checklist

Confirm:

- exact/public DB fields separate;
- public location backend-derived;
- observer backend-derived;
- private mode yields no public point;
- public-safe schema has no exact point;
- cross-user owner endpoint access blocked;
- frontend cannot bypass privacy logic.

## Security checklist

Confirm Sprint 2 protections remain active:

- session cookie;
- CSRF on writes where applicable;
- no localStorage auth;
- no secrets committed.

## Architecture checklist

Confirm:

- modular monolith preserved;
- no unnecessary infrastructure;
- PostGIS used correctly;
- domain logic not concentrated in routers;
- migrations reversible;
- real DB tests exist.

## Performance sanity

Inspect owner list/map query shape and indexes for obvious problems.

Do not prematurely optimize.

## Commit

None unless a scoped correction is necessary.

## Stop condition

Report findings and unresolved risks. Do not merge.

---

# Step 26: Complete the draft pull request

## Goal

Prepare Sprint 3 for final review and merge.

## PR title

```text
feat(observations): add observation capture workflow
```

## PR body must include

### Sprint objective

Authenticated unknown-observation capture with location privacy and personal list/map views.

### Backend summary

- model;
- PostGIS;
- privacy service;
- APIs;
- ownership;
- public-safe schema.

### Frontend summary

- create form;
- geolocation helper;
- journal;
- detail/edit;
- personal map.

### Database summary

- migration revision;
- geometry fields;
- constraints/indexes.

### Privacy summary

- exact/public separation;
- visibility modes;
- obscuring method;
- limitations.

### Authentication integration

Explain reuse of Sprint 2 session/CSRF mechanisms.

### Tests

List backend, privacy, PostGIS, frontend, and CI results.

### Validation commands

Include actual commands run.

### Manual validation

Summarize create/list/detail/edit/map and two-user isolation.

### Known limitations

Include:

- no photos;
- no taxonomy;
- no public feed;
- MVP obscuring limitations;
- tile-service constraints if any.

### Scope confirmation

Explicitly confirm Observation remains separate from Identification and stores no taxonomic conclusion.

## Draft/ready rule

Do not mark ready until Steps 24 and 25 pass.

Do not merge before review.

Use normal merge commit.

## Commit

None normally.

---

# Data validation reference

Suggested initial constraints:

```text
latitude                 -90 <= x <= 90
longitude               -180 <= x <= 180
coordinate_uncertainty   null or >= 0
depth_m                  null or >= 0
quantity                 null or integer >= 1
description              null or bounded text after trim
habitat                  null or bounded concise text after trim
observed_at              timezone-aware
```

Do not invent scientifically misleading precision.

---

# Error-handling reference

Use existing API conventions.

Expected classes include:

```text
authentication required
validation failure
observation not found / inaccessible
internal database failure
network failure
```

Do not reveal another user's email, resource existence when policy hides it, internal SQL/PostGIS errors, or stack traces.

---

# Pagination reference

Keep pagination simple.

If using limit/offset:

- sensible default;
- bounded maximum;
- deterministic ordering;
- reject negative values.

Do not add cursor infrastructure unless existing conventions already require it.

---

# Geospatial checklist

Before accepting implementation, confirm:

- geometry type POINT;
- SRID explicit;
- longitude/latitude order tested;
- API names latitude/longitude explicit;
- PostGIS available locally and in CI;
- geometry serialization explicit;
- public/exact fields independent;
- private public-location nullable;
- updates recalculate public location;
- no accidental WKT leakage to frontend.

---

# Privacy regression checklist

Tests should fail if a future refactor accidentally:

- exposes exact location in public schema;
- uses exact location when visibility is private;
- trusts client-provided public location;
- lets A read B exact location;
- fails to recalculate after exact-location update;
- changes obscured location on every read;
- confuses coordinate uncertainty with privacy.

---

# Authentication integration checklist

Reuse Sprint 2.

Do not create:

- second session system;
- API keys;
- JWT browser auth;
- localStorage auth;
- observation-specific auth middleware.

Use existing current-user dependency, session cookie, CSRF strategy, logout/expiry behavior.

---

# Frontend accessibility checklist

For observation capture:

- every input has accessible label;
- coordinate fields explain expected values;
- validation errors understandable;
- privacy choices explain consequences;
- submit control has loading/disabled state;
- keyboard navigation works;
- map is not the only way to access information.

Do not require map interaction to create or inspect an observation.

---

# Manual test personas

Use at least two temporary local accounts:

```text
Observer A
Observer B
```

No admin/expert role is required.

Suggested observations:

### A1

```text
visibility: obscured
needs identification: yes
habitat: rocky shore
depth: 2.5 m
quantity: 1
```

### A2

```text
visibility: private
needs identification: no
```

### B1

```text
visibility: public
```

Use these to verify owner scoping.

---

# Definition of Done

Sprint 3 is done only when all are true.

## Product

- authenticated user can create unknown observation;
- observation persists;
- journal works;
- detail works;
- edit works;
- personal map works;
- browser geolocation works or fails gracefully.

## Domain

- observer attribution mandatory;
- no taxon required;
- Observation remains separate from Identification;
- contextual fields behave as documented.

## Privacy

- exact/public coordinates separate;
- visibility modes work;
- obscured backend-derived;
- private has no public point;
- public-safe schema cannot expose exact point;
- ownership backend-enforced.

## Database

- migration applies;
- downgrade safe;
- geometry correct SRID;
- PostGIS tests pass.

## Backend

- formatting passes;
- lint passes;
- type checking passes;
- tests pass.

## Frontend

- formatting passes;
- lint passes;
- type checking passes;
- tests pass;
- production build passes.

## CI

- GitHub Actions passes with PostGIS-backed testing.

## Documentation

- ADR exists;
- observation development docs match code;
- privacy behavior documented;
- deferred features explicit.

## Git

- working tree clean;
- semantic commits preserved;
- full diff reviewed;
- no secrets;
- PR not merged before final validation.

---

# Sprint 3 commit map

Expected commits:

```text
docs: record observation location privacy decision
build(observations): establish observation module
feat(observations): add observation persistence model
db(observations): add observation schema
feat(observations): add location privacy service
feat(observations): add observation API schemas
feat(observations): add observation persistence service
feat(observations): add observation creation
feat(observations): add owner observation list
feat(observations): add owner observation detail
feat(observations): add observation updates
feat(observations): add public-safe observation representation
test(observations): cover ownership and location privacy
test(observations): add PostGIS integration coverage
ci: run observation tests with PostGIS
feat(frontend): add observation API client
feat(frontend): add observation creation form
feat(frontend): add observation geolocation helper
feat(frontend): add observation journal
feat(frontend): add observation detail and editing
feat(frontend): add personal observation map
test(frontend): cover observation workflow
docs: add observation development guide
```

Do not collapse the sprint into one giant commit.

---

# Recommended Codex execution pattern

Do not ask Codex to complete the whole playbook.

## Step 0 prompt

```text
Read `.ai/playbooks/sprint-3-observation-capture.md` and all documents listed under Required reading.

Work on `feat/observation-capture`.

Complete Step 0 only.

Do not modify files unless there is a blocking documentation error.

Inspect the post-Sprint-2 backend, frontend, database, authentication integration, tests, Docker setup, and CI.

Report the design required by Step 0, including the proposed Observation model, exact/public coordinate handling, privacy algorithm, API boundary, frontend routes, PostGIS test strategy, likely files, and unresolved risks.

Stop after the report. Do not begin Step 1.
```

## Generic implementation prompt

```text
Read `.ai/playbooks/sprint-3-observation-capture.md`.

Confirm the current branch is `feat/observation-capture`, the working tree is clean, and previous authorized Sprint 3 steps are present.

Complete Step N only.

Follow the Goal, Requirements, Out of scope, Verification, Commit, and Stop condition exactly.

Do not implement later steps.

Run every required check. Never claim a check passed unless it actually ran.

Review the diff for unrelated changes.

Create the exact semantic commit specified by the playbook, push it, and report:
- files changed;
- commands run;
- results;
- migration/database effects;
- privacy/security implications;
- assumptions;
- unresolved risks;
- commit SHA.

Stop after reporting.
```

## Final validation prompt

```text
Read `.ai/playbooks/sprint-3-observation-capture.md`.

Complete Step 24 only.

Treat this as validation, not feature development.

Use the full local Docker/PostGIS stack and completed Sprint 2 authentication flow.

Validate observation creation, privacy modes, exact/public coordinate persistence, list, detail, edit, map, geolocation behavior, and two-user ownership isolation.

Run all repository quality checks.

Inspect the database and complete diff from `main`.

Do not create a commit unless a Sprint 3 defect requires a scoped fix.

Report all results and stop. Do not merge.
```

## Final review prompt

```text
Read `.ai/playbooks/sprint-3-observation-capture.md`.

Complete Step 25 only.

Review Sprint 3 scope, domain invariants, privacy, authorization, architecture, migrations, tests, and diff from `main`.

Confirm no taxonomy, identification, media upload, public feed, or unrelated infrastructure was introduced.

Do not merge.

Report findings and stop.
```

---

# Likely later sprint sequence

After Sprint 3, a sensible direction is:

```text
Sprint 4  Observation media/photos
Sprint 5  Taxonomy catalog and search
Sprint 6  Observer identifications and identification requests
Sprint 7  Community identifications and agreements
Sprint 8  Expert verification and derived identification status
Sprint 9  Personal Marine Life
Sprint 10 Public discovery/map and privacy-safe sharing
Sprint 11 Darwin Core mapping and exports
```

This sequence is directional, not yet authoritative. Each future sprint should get its own reviewed playbook before implementation.

---

# Non-goal reminder

Sprint 3 succeeds when a user can record and manage an **unknown marine observation with safe location handling**.

It is not necessary for Sprint 3 to know what the organism is.

That uncertainty is intentional and central to TrackSea's scientific design.
