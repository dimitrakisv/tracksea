# Git Workflow

## Purpose

This document defines how TrackSea branches, commits, pull requests, and merges should be managed by human contributors and AI coding agents.

## Core rules

- Never commit directly to `main`.
- Start work from an approved issue or clearly defined task.
- Use focused branches.
- Keep commits small, atomic, and semantically named.
- Open a pull request before merging.
- Use a normal merge commit by default so meaningful commits remain visible.
- Use another merge strategy only when the maintainer explicitly chooses it.

## Branch naming

Use:

```text
<category>/<short-kebab-case-description>
```

Examples:

```text
feat/observation-create
fix/public-coordinate-leak
docs/project-foundation
test/identification-history
infra/lightsail-deployment
db/taxonomy-common-names
```

Recommended categories:

- `feat`
- `fix`
- `docs`
- `test`
- `refactor`
- `infra`
- `ci`
- `db`
- `chore`

## Commit format

TrackSea follows Conventional Commits with project-specific types.

```text
<type>(optional-scope): concise imperative summary
```

Allowed types:

- `feat`: new user-facing capability
- `fix`: bug fix
- `docs`: documentation-only change
- `test`: test-only change
- `refactor`: internal restructuring without behavior change
- `perf`: performance improvement
- `style`: formatting-only change
- `build`: dependency or build-system change
- `ci`: continuous-integration change
- `infra`: deployment or infrastructure change
- `db`: schema or migration change
- `chore`: repository maintenance
- `revert`: revert a previous commit

Examples:

```text
docs: define MVP scope
feat(observations): add photo upload endpoint
fix(privacy): prevent exact coordinates in public responses
test(identifications): cover withdrawal history
db(taxonomy): add common names table
ci: run backend tests on pull requests
```

## Commit rules

- Use lowercase types and scopes.
- Use imperative mood.
- Keep the first line concise.
- Do not add a trailing period.
- Keep one coherent change per commit.
- Do not mix unrelated refactoring with feature work.
- Add a body when reasoning, trade-offs, or migration impact are not obvious.
- Use `BREAKING CHANGE:` in the footer only for intentional contract breaks.

## Pull request lifecycle

1. Create a branch from the current `main`.
2. Implement only the scoped task.
3. Add or update tests.
4. Update documentation.
5. Run formatting, linting, type checks, and tests.
6. Open a draft PR when work is incomplete.
7. Mark it ready when the Definition of Done is satisfied.
8. Address review feedback with additional commits.
9. Merge using a normal merge commit by default.
10. Delete the branch after merge when no longer needed.

## Pull request expectations

Every PR should include:

- linked issue or task context;
- summary of the change;
- reason for the change;
- tests performed;
- documentation updates;
- privacy, migration, compatibility, or operational risks;
- screenshots for meaningful UI changes; and
- unresolved assumptions.

## Merge policy

Default:

```text
feature commits
      |
      v
normal merge commit into main
```

This preserves meaningful commit history.

Squash merging may be used only when the maintainer explicitly prefers a single commit for a noisy or temporary branch.

Rebase merging is not the default because it removes the explicit branch integration point.

## Hotfixes

Urgent production fixes still require:

- a focused `fix/` branch;
- a pull request;
- regression tests where practical;
- review; and
- a documented release or deployment note.

## Release tags

When releases begin, use semantic version tags:

```text
v0.1.0
v0.2.0
v1.0.0
```

Release automation may later derive changelogs from semantic commits.
