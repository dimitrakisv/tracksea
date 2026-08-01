# Contributing to TrackSea

Thank you for helping build TrackSea.

TrackSea is a personal marine journal that powers open marine science. Contributions must support both a clear user experience and trustworthy biodiversity data.

## Before you start

Read:

1. `README.md`
2. `AGENTS.md`
3. `docs/PROJECT_CONSTITUTION.md`
4. `docs/product/mvp-scope.md`
5. Relevant domain and architecture documents
6. `docs/engineering/git-workflow.md`
7. `docs/engineering/definition-of-done.md`

## Contribution workflow

1. Start from an approved GitHub issue.
2. Create a focused branch from `main`.
3. Make small, coherent commits.
4. Add or update tests.
5. Update documentation when behavior or architecture changes.
6. Open a pull request.
7. Address review feedback.
8. Merge with a normal merge commit unless the maintainer explicitly selects another strategy.

## Branch naming

Use a short category and kebab-case description:

```text
feat/observation-create
fix/public-coordinate-leak
docs/project-foundation
test/identification-history
infra/lightsail-deployment
```

Recommended categories:

- `feat/`
- `fix/`
- `docs/`
- `test/`
- `refactor/`
- `infra/`
- `ci/`
- `db/`
- `chore/`

## Semantic commits

Use:

```text
<type>(optional-scope): concise imperative summary
```

Common examples:

```text
feat(observations): add photo upload endpoint
fix(privacy): prevent exact coordinates in public responses
docs: define taxonomy workflow
test(identifications): cover withdrawal history
db(taxonomy): add common names table
ci: run checks on pull requests
```

Use the allowed types and detailed rules in `docs/engineering/git-workflow.md`.

## Pull requests

A pull request should:

- solve one clear problem;
- link the relevant issue;
- explain what changed and why;
- list tests performed;
- mention documentation changes;
- identify privacy, migration, or compatibility risks;
- avoid unrelated refactoring; and
- satisfy the Definition of Done.

## Review expectations

Reviewers should check:

- product and MVP alignment;
- domain correctness;
- privacy and authorization boundaries;
- auditability of scientific history;
- test coverage;
- documentation accuracy; and
- unnecessary complexity.

## AI-assisted contributions

AI-generated changes are welcome, but they are reviewed by the same standard as human-written changes.

The contributor remains responsible for:

- understanding the change;
- verifying correctness;
- running tests;
- checking security and privacy;
- removing unrelated generated changes; and
- documenting assumptions.

## Scope changes

Do not silently change product scope, domain rules, architecture, scientific authority, privacy policy, or governance.

Propose significant changes through an issue and, when appropriate, an Architecture Decision Record.
