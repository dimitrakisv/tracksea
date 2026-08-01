# TrackSea Development Instructions

## Product vision

TrackSea is a personal marine journal that powers open marine science.

Every feature should provide value to both:

1. The individual user.
2. The scientific community.

## Required reading

Before changing code or documentation, read:

- `docs/PROJECT_CONSTITUTION.md`
- `docs/product/mvp-scope.md`
- Relevant files under `docs/domain/`, `docs/architecture/`, and `docs/decisions/`

## MVP scope

Build only the capabilities documented in `docs/product/mvp-scope.md`.

Do not implement the following unless a later issue explicitly changes scope:

- XP, levels, leaderboards, or badges
- Forums or direct messaging
- AI species identification
- Native mobile applications
- Microservices
- Complex reputation weighting
- Organization dashboards

## Technology direction

- Python 3.12+
- FastAPI
- SQLAlchemy 2
- Alembic
- PostgreSQL with PostGIS
- React with TypeScript
- Docker Compose
- S3-compatible object storage

## Architecture rules

- Start as a modular monolith.
- Keep domain logic out of API route handlers and UI components.
- Keep exact coordinates separate from public coordinates.
- Store an observer's taxon choice as an `Identification`, not as unquestionable truth on the observation.
- Never silently overwrite identification or verification history.
- Allow identifications above species rank.
- Do not force users to identify a species.
- Keep TrackSea's domain model separate from its Darwin Core export adapter.
- Scientific authority must never be granted through participation points.

## Coding rules

- Use strict typing.
- Validate every external input.
- Add or update tests for behavior changes.
- Use database migrations for schema changes.
- Do not add dependencies without documenting the reason.
- Do not modify unrelated files.
- Never commit secrets or production credentials.
- Update documentation when behavior or architecture changes.

## Workflow

Before implementation:

1. Read the relevant documents.
2. Restate the task and acceptance criteria.
3. Identify affected modules and risks.
4. Propose the smallest implementation that satisfies the issue.

After implementation:

1. Run formatting.
2. Run linting.
3. Run type checking.
4. Run tests.
5. Summarize files changed.
6. Report unresolved assumptions and risks.

## Git discipline

- Do not commit directly to `main`.
- Work from a focused branch.
- Keep commits small, atomic, and descriptive.
- Open a pull request for review before merge.
