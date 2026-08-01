# AI Playbook: Implement a Feature

## Purpose

Use this playbook whenever an AI coding agent implements a TrackSea feature, fix, refactor, migration, or substantial documentation change.

The goal is to produce a focused, reviewable change that follows the Constitution, the domain model, the architecture, and the Definition of Done.

## 1. Read the authoritative context

Read, in order:

1. `AGENTS.md`
2. `docs/PROJECT_CONSTITUTION.md`
3. `docs/product/mvp-scope.md`
4. Relevant domain documents
5. Relevant architecture documents
6. Relevant ADRs
7. `docs/engineering/git-workflow.md`
8. `docs/engineering/definition-of-done.md`
9. The assigned GitHub issue
10. `.ai/README.md`

Do not start implementation before this context is understood.

## 2. Restate the task

Before editing files, provide a concise implementation brief containing:

- the problem being solved;
- acceptance criteria;
- out-of-scope items;
- affected modules;
- privacy, security, migration, and scientific-integrity risks;
- assumptions; and
- the smallest implementation sequence.

If the issue conflicts with an accepted ADR or the Constitution, stop and report the conflict.

## 3. Inspect the existing implementation

Identify:

- existing patterns to follow;
- relevant tests;
- related migrations;
- public API contracts;
- module boundaries;
- documentation that may need updates; and
- any stale or contradictory code.

Do not invent a new pattern when a suitable project pattern already exists.

## 4. Plan the change

Prefer a minimal plan with small, coherent stages.

Example:

1. Add or update domain behavior.
2. Add persistence changes and migration.
3. Add API boundary changes.
4. Add tests.
5. Update documentation.
6. Run checks and review the diff.

Avoid unrelated cleanup.

## 5. Implement within boundaries

During implementation:

- keep route handlers and UI components thin;
- keep business rules in the owning domain module;
- validate external input;
- enforce authorization in the backend;
- preserve exact-coordinate privacy;
- preserve identification and verification history;
- keep Darwin Core mapping in the export adapter;
- justify new dependencies;
- use migrations for schema changes; and
- keep the implementation understandable.

## 6. Test the behavior

Add or update tests that verify externally meaningful behavior.

Prioritize tests for:

- authorization;
- coordinate privacy;
- audit history;
- validation;
- state transitions;
- migration behavior;
- API contracts;
- error handling; and
- regressions related to the issue.

Do not test only implementation details.

## 7. Update documentation

Update all affected documentation, including when applicable:

- README or contributor guidance;
- domain documents;
- architecture documents;
- API contracts;
- environment examples;
- deployment notes;
- ADRs; and
- known limitations.

A behavior change is incomplete when the knowledge base remains inaccurate.

## 8. Use semantic commits

Create small commits using:

```text
<type>(optional-scope): concise imperative summary
```

Examples:

```text
feat(observations): add photo upload endpoint
db(observations): add media relationship
fix(privacy): hide exact coordinates from public responses
test(observations): cover private coordinate access
docs(observations): document upload workflow
```

Do not combine unrelated changes in one commit.

## 9. Run required checks

Run all checks relevant to the change, including:

- formatting;
- linting;
- type checking;
- unit tests;
- integration tests;
- frontend tests;
- migration checks; and
- build checks.

Never claim a check passed unless it was actually run.

If a check cannot be run, state exactly why.

## 10. Review the final diff

Before opening the PR, inspect the complete diff for:

- unrelated files;
- accidental secrets;
- private data leakage;
- debug code;
- incomplete migrations;
- duplicated logic;
- outdated documentation;
- unnecessary abstractions; and
- scope creep.

Remove anything not required by the issue.

## 11. Prepare the pull request

The PR summary must include:

- issue or task reference;
- what changed;
- why it changed;
- tests and checks run;
- documentation updated;
- migration or deployment impact;
- privacy and security considerations;
- screenshots for meaningful UI changes;
- assumptions; and
- remaining risks or follow-up work.

Use a draft PR until the Definition of Done is satisfied.

## 12. Stop conditions

Stop and ask for maintainer direction when:

- the task requires changing the Constitution;
- an accepted ADR must be reversed;
- MVP scope must expand;
- a new service or major infrastructure component is required;
- scientific authority rules would change;
- coordinate privacy policy is unclear;
- data migration could be destructive; or
- the issue does not contain enough information for a safe implementation.

## Completion report

At the end, report:

1. Files changed.
2. Commits created.
3. Tests and checks run with results.
4. Documentation updated.
5. Assumptions made.
6. Remaining risks or follow-up work.
