# TrackSea AI Contributor Guide

## Purpose

The `.ai/` directory contains concise operating guidance for AI coding agents working on TrackSea.

It does not replace the project knowledge base. AI agents must use it together with `AGENTS.md`, the Constitution, domain documentation, architecture documentation, ADRs, and the relevant GitHub issue.

## Required reading order

Before changing code or documentation, read:

1. `AGENTS.md`
2. `docs/PROJECT_CONSTITUTION.md`
3. `docs/product/mvp-scope.md`
4. Relevant files under `docs/domain/`
5. Relevant files under `docs/architecture/`
6. Relevant ADRs under `docs/decisions/`
7. `docs/engineering/git-workflow.md`
8. `docs/engineering/definition-of-done.md`
9. The assigned GitHub issue
10. The relevant playbook under `.ai/playbooks/`

## Source-of-truth hierarchy

When instructions conflict, use this order:

1. Explicit maintainer direction in the current task
2. Project Constitution
3. Accepted ADRs
4. Product and MVP documentation
5. Domain and architecture documentation
6. `AGENTS.md`
7. Engineering and AI playbooks
8. Existing implementation patterns

Do not silently resolve a meaningful conflict. Report it before implementation.

## Operating principles

AI agents must:

- implement only the scoped issue;
- prefer the smallest complete solution;
- preserve domain boundaries;
- protect exact coordinates and private data;
- preserve identification and verification history;
- keep Darwin Core as an adapter, not the internal domain model;
- add or update tests;
- update documentation when behavior changes;
- use semantic commits;
- report assumptions, risks, and unresolved questions; and
- leave the repository easier to understand.

## Prohibited behavior

AI agents must not:

- commit directly to `main`;
- invent product requirements;
- expand MVP scope without approval;
- introduce microservices or major infrastructure without an accepted decision;
- grant scientific authority through points or popularity;
- force users to identify a species;
- expose private coordinates through APIs, exports, logs, or media metadata;
- silently overwrite scientific history;
- add dependencies without justification;
- perform unrelated refactoring; or
- claim checks passed without running them.

## Working style

### Before implementation

- Restate the problem and acceptance criteria.
- Identify relevant documentation and modules.
- Note privacy, data migration, and scientific-integrity risks.
- Propose a minimal implementation sequence.

### During implementation

- Keep changes focused.
- Use explicit module boundaries.
- Add tests with the behavior.
- Make small semantic commits when the task permits multiple coherent stages.

### After implementation

- Run formatting, linting, type checking, and tests.
- Review the diff for unrelated changes.
- Update documentation.
- Summarize changed files and decisions.
- Report commands run, results, assumptions, and remaining risks.

## Human responsibility

AI-generated work is a proposal until reviewed.

The maintainer or contributor remains responsible for correctness, security, privacy, scientific integrity, and merge decisions.

## Directory structure

```text
.ai/
├── README.md
└── playbooks/
    └── implement-feature.md
```

Additional playbooks or checklists should be added only when they capture a repeated, valuable workflow.
