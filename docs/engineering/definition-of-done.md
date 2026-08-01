# Definition of Done

A TrackSea change is done only when all applicable conditions below are satisfied.

## Product and scope

- The change solves the linked issue or approved task.
- It remains within the documented MVP scope unless scope was explicitly changed.
- It passes the TrackSea test: user value, scientific value, privacy, and simplicity.

## Architecture and domain

- Domain rules are implemented outside transport and presentation layers.
- Observation, Identification, Agreement, and Verification remain separate concepts.
- Private and public coordinates remain separated.
- Scientific history is auditable and not silently overwritten.
- Significant architectural changes are documented in an ADR.

## Code quality

- Code is typed, readable, and appropriately documented.
- External inputs are validated.
- Errors are handled consistently without leaking secrets or private data.
- No unrelated refactoring is included.
- New dependencies are justified.

## Testing

- New or changed behavior has appropriate automated tests.
- Privacy and authorization boundaries are tested where relevant.
- Database migrations are tested where relevant.
- Formatting, linting, type checking, and tests pass locally and in CI.

## Documentation

- User-facing behavior changes are documented.
- API or schema changes update their contracts.
- Relevant domain, architecture, or operations documents are updated.
- Assumptions and known limitations are recorded.

## Security and privacy

- No secrets, credentials, or private configuration are committed.
- Exact coordinates cannot leak through public responses, logs, exports, or media metadata.
- Uploaded files are treated as untrusted input.
- Authorization is enforced in the backend.

## Git and review

- The branch is focused and based on current `main`.
- Commits follow the semantic commit convention.
- Commits are coherent and preserve meaningful history.
- The pull request explains what changed, why, tests performed, and risks.
- Review feedback is resolved.
- The PR is merged with a normal merge commit by default.

## Operations

- Configuration changes are reflected in `.env.example` or equivalent documentation.
- Deployment or migration impact is documented.
- The change is observable through useful logs or health checks where relevant.
- Rollback considerations are documented for high-risk changes.

## AI-assisted work

- The contributor understands and has reviewed generated changes.
- Generated code does not introduce unrelated files or abstractions.
- The final PR summary lists unresolved assumptions and risks.
