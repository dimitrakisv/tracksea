# Sprint 2 Playbook: Authentication and User Identity

## Objective

Deliver TrackSea's first complete user-facing workflow: a person can create an account, sign in, remain signed in securely, inspect and update their own basic profile, sign out, and optionally authenticate with Google.

Sprint 2 establishes:

- the `users` module within the FastAPI modular monolith;
- internal TrackSea user identities;
- email-and-password authentication;
- Google Sign-In through Google Identity Services;
- PostgreSQL-backed opaque sessions;
- secure session and CSRF cookies;
- backend-owned authentication and authorization boundaries;
- frontend authentication state and screens;
- database migrations, tests, CI coverage, and documentation for authentication.

Sprint 2 must not implement observations, taxonomy, media uploads, maps, identifications, Marine Life, organizations, moderation, gamification, or other product features.

## Sprint success criteria

At the end of Sprint 2, a user must be able to:

1. Open the TrackSea frontend.
2. Register with an email address, password, and display name.
3. Sign in with email and password.
4. Sign in with Google using the official Google Identity Services button.
5. Refresh the browser and remain signed in while the TrackSea session is valid.
6. Retrieve their own profile from the backend.
7. Update their display name.
8. Sign out and have the current server-side session revoked.
9. Receive safe, understandable errors without password, token, or account-detail leakage.
10. Use the same TrackSea authorization model regardless of whether they authenticated by password or Google.

The following quality gates must also pass:

- database migration upgrade, downgrade, and re-upgrade;
- backend formatting, linting, type checking, unit tests, and integration tests;
- frontend formatting, linting, type checking, tests, and production build;
- pre-commit checks;
- GitHub Actions;
- full Docker Compose validation;
- manual email/password authentication flow;
- manual Google Sign-In flow when valid local Google credentials are available.

## Required reading

Before each step, read:

1. `AGENTS.md`
2. `docs/PROJECT_CONSTITUTION.md`
3. `docs/product/vision.md`
4. `docs/product/mvp-scope.md`
5. `docs/domain/domain-model.md`
6. `docs/domain/identification-workflow.md`
7. `docs/architecture/system-overview.md`
8. `docs/decisions/ADR-001-fastapi.md`
9. `docs/decisions/ADR-002-modular-monolith.md`
10. `docs/engineering/git-workflow.md`
11. `docs/engineering/definition-of-done.md`
12. `.ai/README.md`
13. `.ai/playbooks/implement-feature.md`
14. `.ai/playbooks/sprint-1-repository-bootstrap.md`
15. This playbook

When implementation begins, also read the accepted authentication ADR created in Step 1.

## Source-of-truth order

When instructions conflict, use this order:

1. Explicit maintainer instruction for the current task
2. Project Constitution
3. Accepted ADRs
4. MVP scope and domain documentation
5. This playbook
6. Existing code patterns

Do not silently resolve a meaningful conflict. Stop and report it.

## Branch and pull request

Use or create:

```text
feat/authentication
```

Use one draft pull request for Sprint 2 while preserving the meaningful semantic commits defined in this playbook.

Pull request title:

```text
feat(auth): add user authentication
```

Do not merge the pull request before final validation in Step 25 and review in Step 26.

## Global implementation rules

- Keep authentication inside the modular monolith.
- Backend code owns authentication and authorization decisions.
- Keep FastAPI route handlers thin.
- Put domain and application behavior in services.
- Put persistence operations behind repositories or clearly defined persistence functions.
- Use SQLAlchemy 2 typed mappings.
- Use Alembic for every schema change.
- Use UTC-aware timestamps.
- Use UUID primary keys for user-facing domain entities.
- Never expose password hashes, raw session tokens, CSRF secrets, provider credentials, or internal security metadata in API responses.
- Never log passwords, session tokens, Google ID tokens, CSRF tokens, or OAuth credentials.
- Do not use browser `localStorage` or `sessionStorage` for authentication tokens.
- Do not use JWT bearer tokens as TrackSea browser sessions.
- Do not add Redis, Celery, Kubernetes, microservices, or an external identity platform.
- Do not add social providers other than Google.
- Do not add password reset, email verification delivery, MFA, WebAuthn, public profiles, avatars, roles, expert permissions, or administration.
- Do not add Google API scopes such as Drive, Calendar, Contacts, or offline access.
- Do not store Google access tokens or refresh tokens.
- Do not use a Google email address as the permanent provider identifier; use the Google `sub` claim.
- Do not silently link an existing password account to Google only because the emails match.
- Do not weaken security checks merely to make tests pass.

## Authentication architecture fixed for this sprint

Unless Step 0 identifies a blocking incompatibility, Sprint 2 uses the following architecture.

### TrackSea session model

- Sessions are opaque, random identifiers generated by TrackSea.
- Generate at least 256 bits of randomness with Python's `secrets` module.
- Store only a SHA-256 or stronger one-way digest of the raw session token in PostgreSQL.
- Store session meaning and authorization state only on the server.
- Put the raw token only in a browser cookie.
- Revoke the current database session on logout.
- Reject expired and revoked sessions.
- Mint a new session after every successful registration or authentication event.
- Never reuse a pre-authentication session identifier as an authenticated session identifier.

### Session cookie

The session cookie must be configured with:

```text
HttpOnly=true
SameSite=Lax
Path=/
Secure=false only for local HTTP development
Secure=true outside local development
Domain omitted
```

Use a configurable cookie name. Production documentation should recommend a `__Host-` prefixed cookie name when HTTPS is available.

### CSRF protection

Because authentication uses cookies, state-changing requests require CSRF protection.

Sprint 2 uses a signed double-submit pattern plus origin checking:

- expose a CSRF bootstrap endpoint;
- set a readable CSRF cookie;
- return the same token in a safe response body;
- require the frontend to send the token in `X-CSRF-Token` for unsafe requests;
- verify cookie and header equality in constant time;
- verify the token signature and expiry;
- verify `Origin` or, when necessary, `Referer` against the configured frontend origin;
- protect registration, login, Google sign-in, logout, linking, and profile updates;
- never rely on `SameSite` alone.

The CSRF token is not an authentication token and must not be used for authorization.

### Password authentication

- Use `pwdlib[argon2]` or another explicitly approved Argon2id implementation.
- Use Argon2id recommended settings from the selected maintained library.
- Require a minimum of 15 Unicode characters for single-factor passwords.
- Allow at least 64 characters; use 128 as the initial safe maximum unless Step 0 justifies another value.
- Allow spaces and Unicode.
- Apply Unicode NFC normalization before hashing and verification.
- Do not require uppercase, lowercase, number, or symbol composition rules.
- Do not trim or silently change passwords beyond documented Unicode normalization.
- Reject known common passwords using a local, license-compatible blocklist selected and documented in Step 0.
- Do not call third-party breached-password services during registration in this sprint.
- Use a dummy password hash when an unknown email attempts login to reduce account-enumeration timing differences.

### Google authentication

Use Google Identity Services for authentication only.

- Render the official Sign in with Google button.
- Use the JavaScript credential callback flow for the React frontend unless Step 0 identifies a blocker.
- The browser receives a short-lived Google ID token credential and immediately posts it to TrackSea's backend.
- The backend verifies the Google ID token using a maintained Google library.
- Verify signature, issuer, audience, expiration, and required claims.
- Require `email_verified=true` before using the Google email to create a TrackSea user.
- Use `sub` as the external identity key.
- Do not require or store a Google client secret for this credential flow.
- Do not request Google access tokens, refresh tokens, or API scopes.
- Both Google and password authentication create the same TrackSea server-side session.
- TrackSea, not Google, owns authorization.

### Account-linking rule

For Sprint 2:

- Existing `(provider=google, subject=sub)` identity: sign in the linked TrackSea user.
- New Google identity with an unused verified email: create a new TrackSea user and external identity.
- New Google identity whose normalized email matches an existing password account: do not silently link; return a stable `account_link_required` error.
- An authenticated password user may explicitly link Google through a CSRF-protected endpoint and minimal account-settings action.
- A Google-only user does not gain a password in this sprint.
- Unlinking the only authentication method is out of scope.

### Abuse controls

Implement PostgreSQL-backed login throttling without Redis.

At minimum, rate-limit failed password-login attempts by:

- normalized email-derived key; and
- client-IP-derived key.

Hash or HMAC throttle keys before persistence. Do not store raw email/IP combinations in throttle rows.

Thresholds must be configurable. Suggested initial defaults:

```text
5 failed attempts per account key per 15 minutes
20 failed attempts per IP key per 15 minutes
15 minute block window
```

Do not trust `X-Forwarded-For` unless the deployment explicitly configures trusted proxies.

## Proposed backend module structure

The exact file split may change slightly when justified, but the domain boundary should resemble:

```text
backend/app/
├── api/
├── auth/
│   ├── __init__.py
│   ├── cookies.py
│   ├── csrf.py
│   ├── dependencies.py
│   ├── google.py
│   ├── passwords.py
│   ├── schemas.py
│   ├── service.py
│   └── throttling.py
├── users/
│   ├── __init__.py
│   ├── models.py
│   ├── repository.py
│   ├── router.py
│   ├── schemas.py
│   └── service.py
├── core/
│   └── config.py
└── db/
    ├── base.py
    └── session.py
```

Tests should mirror meaningful boundaries rather than every file.

## Proposed frontend structure

```text
frontend/src/
├── api/
│   ├── client.ts
│   └── auth.ts
├── auth/
│   ├── AuthProvider.tsx
│   ├── GoogleSignInButton.tsx
│   ├── ProtectedRoute.tsx
│   ├── types.ts
│   └── useAuth.ts
├── pages/
│   ├── SignInPage.tsx
│   ├── RegisterPage.tsx
│   ├── AppHomePage.tsx
│   └── ProfilePage.tsx
└── test/
```

Use React context and hooks unless Step 0 demonstrates a real need for a state-management library.

## API contract target

The exact Pydantic schema names may vary, but Sprint 2 should provide:

```text
GET   /api/v1/auth/csrf
POST  /api/v1/auth/register
POST  /api/v1/auth/login
POST  /api/v1/auth/logout
GET   /api/v1/auth/me
POST  /api/v1/auth/google
POST  /api/v1/auth/google/link
PATCH /api/v1/users/me
```

Suggested status behavior:

```text
GET csrf              200
POST register          201
POST login             200
POST logout            204
GET me                 200 or 401
POST google            200 for existing user, 201 for newly created user
POST google/link       200
PATCH users/me         200
CSRF failure           403
Invalid credentials    401 with generic error
Account conflict       409 with stable non-secret error code
Rate limit             429 with Retry-After when practical
Validation failure     422 using the established API convention
```

Do not return the raw session token in JSON.

## Standard report after every implementation step

After every step, Codex must report:

1. Files changed.
2. Dependencies added or removed and why.
3. Database changes and migration behavior.
4. Commands run.
5. Verification and test results.
6. Commit SHA, when a commit is required.
7. Remote and working-tree status.
8. Security assumptions.
9. Known risks or follow-up items.

Never claim a command passed unless it was actually run.

## Common stop conditions

Stop and ask for maintainer direction when:

- an instruction conflicts with the Constitution or an accepted ADR;
- a new external service is required;
- a client secret appears necessary for the selected Google flow;
- account linking cannot be made safe with the documented rules;
- destructive migration behavior is required;
- a production domain or HTTPS assumption must be invented;
- a dependency is unmaintained, unclear, or has an incompatible license;
- CI would require real Google credentials;
- a security check would need to be disabled;
- the task expands into password reset, email delivery, roles, or other out-of-scope work.

---

# Step 0: Inspect and prepare the authentication design brief

## Goal

Understand the merged Sprint 1 repository and confirm that this playbook fits the actual implementation before modifying files.

## Scope

Inspect:

- current `main` and Git status;
- backend application factory and router structure;
- SQLAlchemy base, engine, and session management;
- Alembic configuration and migration history;
- frontend component and test structure;
- Docker Compose networking and environment values;
- Makefile, pre-commit, and CI;
- local development documentation;
- current dependency versions and lockfiles.

## Required design brief

Report a concrete plan covering:

- final backend module structure;
- final frontend auth structure;
- database tables and constraints;
- session token generation and hashing;
- cookie names and attributes in local and production environments;
- CSRF token format, signing, expiry, and origin checks;
- password library and common-password blocklist source/license;
- Google Identity Services credential flow;
- Google verification library and test seam;
- account-linking behavior;
- rate-limit storage and key derivation;
- API response and error conventions;
- testing strategy, including when PostgreSQL is required in CI;
- migration sequencing;
- expected semantic commits.

## Verification

- Confirm the branch starts from updated `main`.
- Confirm no uncommitted work will be overwritten.
- Confirm Docker and existing Sprint 1 checks pass or report blockers.
- Confirm the proposed libraries support Python 3.12 and the current frontend versions.

## Files

Do not modify files unless correcting a blocking factual error in existing documentation.

## Commit

No commit is expected.

## Stop condition

Stop after the design brief. Do not start Step 1 without maintainer approval.

---

# Step 1: Record the authentication and session architecture decision

## Goal

Create the accepted architecture record that makes the core authentication decisions explicit and durable.

## File

```text
docs/decisions/ADR-003-authentication-and-sessions.md
```

## Requirements

The ADR must document:

- the problem and context;
- opaque PostgreSQL-backed TrackSea sessions;
- why browser JWT bearer sessions were not selected;
- Argon2id password hashing;
- session-token hashing before persistence;
- HttpOnly cookie configuration;
- CSRF signed double-submit plus origin validation;
- explicit credentialed CORS or same-origin proxy expectations;
- Google Identity Services as an external identity provider;
- use of Google `sub` as provider identity;
- no Google client secret for the selected ID-token credential flow;
- no Google API access or token persistence;
- explicit account linking instead of silent email-only linking;
- PostgreSQL-backed login throttling;
- deferred password reset, email verification, MFA, and other providers;
- positive and negative consequences;
- review triggers.

## Verification

- Ensure the ADR does not contradict ADR-001 or ADR-002.
- Ensure terminology matches the domain model.
- Ensure the selected design can run locally through Docker Compose.

## Commit

```text
docs: record authentication and session decision
```

## Stop condition

Commit, push, report, and stop.

---

# Step 2: Establish the users and auth module boundaries

## Goal

Create clear module boundaries before adding database models or endpoints.

## Scope

Create minimal packages for:

- users;
- authentication services;
- schemas and dependency boundaries.

## Likely files

```text
backend/app/users/__init__.py
backend/app/users/schemas.py
backend/app/users/repository.py
backend/app/users/service.py
backend/app/users/router.py
backend/app/auth/__init__.py
backend/app/auth/schemas.py
backend/app/auth/dependencies.py
```

Only create files that contain a justified minimal boundary. Avoid empty abstraction layers that add no value.

## Requirements

- Define safe public user schemas without persistence implementation details.
- Define stable error-code conventions for auth failures.
- Keep route registration compatible with the existing application factory.
- Do not add ORM models yet.
- Do not add endpoints yet.
- Do not add password, session, Google, or CSRF behavior yet.

## Verification

- Import the application successfully.
- Run backend formatting, linting, type checking, and existing tests.
- Confirm no database schema change.

## Commit

```text
build(users): establish authentication modules
```

## Stop condition

Commit, push, report, and stop.

---

# Step 3: Add User, ExternalIdentity, Session, and throttle models

## Goal

Create the persistent authentication model without exposing it through HTTP yet.

## User model

Required fields:

```text
id                  UUID primary key
email               canonical display email
normalized_email    unique normalized email
email_verified_at   nullable UTC timestamp
display_name        non-empty string
password_hash       nullable string
is_active           boolean, default true
created_at          UTC timestamp
updated_at          UTC timestamp
```

Rules:

- Password accounts have a password hash.
- Google-only accounts may have `password_hash=NULL`.
- API schemas never serialize `password_hash`.
- Normalize email consistently in one service function.
- Database uniqueness must be enforced on `normalized_email`.

## ExternalIdentity model

Required fields:

```text
id                  UUID primary key
user_id             foreign key to users
provider            string or constrained enum value
subject             provider subject identifier
email_snapshot      nullable provider email snapshot
created_at          UTC timestamp
last_login_at       nullable UTC timestamp
```

Constraints:

- unique `(provider, subject)`;
- provider initially supports only `google`;
- deleting a user deletes or otherwise safely removes identities according to the documented relationship behavior.

## Session model

Required fields:

```text
id                  UUID primary key
token_hash          unique fixed-length digest
user_id             foreign key to users
created_at          UTC timestamp
expires_at          UTC timestamp
last_seen_at        nullable UTC timestamp
revoked_at          nullable UTC timestamp
```

Rules:

- Never store the raw token.
- Index user ID, token hash, and expiration fields as justified.
- Do not store unnecessary IP addresses or user-agent strings in the session table in this sprint.

## Throttle model

Suggested fields:

```text
id                  UUID primary key
scope               constrained string, such as account or ip
key_hash            HMAC digest
failure_count       integer
window_started_at   UTC timestamp
blocked_until       nullable UTC timestamp
updated_at          UTC timestamp
```

Constraint:

- unique `(scope, key_hash)`.

## Shared model behavior

- Use SQLAlchemy 2 `Mapped` annotations and `mapped_column`.
- Use named constraints through the project's metadata convention when available.
- Use timezone-aware database timestamps.
- Avoid ORM event magic unless justified.
- Add model-level tests only for behavior that is not better verified through migrations or services.

## Verification

- Import all models into the Alembic metadata boundary.
- Run formatting, linting, type checking, and non-database tests.
- Do not create tables directly with `metadata.create_all`.

## Commit

```text
feat(users): add authentication persistence models
```

## Stop condition

Commit, push, report, and stop.

---

# Step 4: Add and verify the authentication migration

## Goal

Create the first TrackSea domain migration for authentication tables and constraints.

## Requirements

Generate or write an Alembic revision that creates:

- users;
- external identities;
- sessions;
- throttle buckets;
- required indexes;
- named unique constraints;
- foreign keys and deletion behavior.

Review generated SQL manually. Do not accept autogenerated migration output without inspection.

## Verification sequence

Use a disposable or resettable local database.

1. Start PostgreSQL.
2. Confirm the database contains no TrackSea domain tables before upgrade.
3. Run `alembic upgrade head`.
4. Inspect created tables, columns, indexes, constraints, and foreign keys.
5. Run `alembic downgrade base`.
6. Confirm authentication tables are removed while PostGIS remains usable.
7. Run `alembic upgrade head` again.
8. Run backend tests.

Do not use `docker compose down -v` unless intentionally resetting local data and explicitly reporting it.

## Commit

```text
db(users): add authentication schema
```

## Stop condition

Commit, push, report migration verification, and stop.

---

# Step 5: Implement email normalization and password policy

## Goal

Create deterministic, tested email and password handling before registration or login endpoints exist.

## Email requirements

- Parse and validate email through the existing Pydantic approach.
- Normalize the domain portion according to standards and lower-case the normalized comparison value.
- Treat the complete normalized email comparison consistently across registration and login.
- Preserve a safe canonical email for display.
- Do not implement provider-specific dot removal or plus-address rewriting.

## Password policy

Implement:

- Unicode NFC normalization;
- minimum 15 characters;
- maximum 128 characters unless the Step 0 design justifies another safe maximum;
- spaces and Unicode accepted;
- no composition rules;
- no periodic-expiry concept;
- local common-password blocklist;
- project-specific blocked values such as obvious TrackSea variants;
- actionable registration errors that do not echo the password.

The common-password list must:

- have a compatible license;
- be stored locally or provided by a maintained dependency;
- be documented with source and license;
- not require a network request during validation.

## Password hashing

- Add `pwdlib[argon2]` or the approved library from Step 0.
- Create a single password service.
- Hash with Argon2id recommended settings.
- Verify valid and invalid passwords.
- Support future rehash detection when the library provides it.
- Precompute or configure a dummy hash for unknown-account login attempts.
- Never expose raw hashes outside the auth service and persistence model.

## Tests

Cover:

- normalization consistency;
- Unicode password behavior;
- minimum and maximum length;
- spaces accepted;
- common-password rejection;
- unique salts for equal passwords;
- successful verification;
- failed verification;
- dummy-hash path;
- no password or hash in representations and errors.

## Verification

Run backend formatting, linting, type checking, and tests.

## Commit

```text
feat(auth): add password policy and hashing
```

## Stop condition

Commit, push, report dependencies and parameters, and stop.

---

# Step 6: Implement server-side session lifecycle

## Goal

Create and resolve secure TrackSea sessions without HTTP endpoints yet.

## Token requirements

- Generate at least 32 random bytes with `secrets`.
- Encode the browser token using a URL-safe representation.
- Hash the token before database persistence.
- Compare digests safely.
- Store only the digest.
- Treat raw token values as secrets in memory.

## Session service behavior

Implement:

- create a session for a user;
- find an active session by raw token digest;
- reject expired sessions;
- reject revoked sessions;
- revoke one session;
- optionally revoke all sessions for a user through a service method, without exposing a route in this sprint;
- update `last_seen_at` no more frequently than a documented interval to avoid a write on every request;
- use configurable absolute lifetime;
- do not implement sliding expiration unless explicitly accepted in Step 0.

Suggested initial lifetime:

```text
30 days absolute
```

The lifetime must be configuration, not a scattered constant.

## Cookie helpers

Create centralized helpers for:

- setting the session cookie;
- clearing the session cookie;
- selecting secure attributes by environment;
- selecting cookie name by environment.

Do not set cookies directly in unrelated route handlers.

## Tests

Cover:

- token uniqueness;
- raw token not persisted;
- valid lookup;
- unknown token;
- expired token;
- revoked token;
- revocation;
- cookie attributes in local mode;
- cookie attributes in production mode;
- cookie clearing;
- session fixation prevention through new-token creation.

## Verification

Use PostgreSQL-backed tests where persistence behavior matters.

Run backend formatting, linting, type checking, tests, and migration checks.

## Commit

```text
feat(auth): add server-side session management
```

## Stop condition

Commit, push, report cookie configuration and session lifetime, and stop.

---

# Step 7: Implement CSRF and trusted-origin protection

## Goal

Protect all cookie-authenticated state-changing requests, including login and registration.

## Configuration

Add settings for:

```text
FRONTEND_ORIGIN
CSRF_SECRET
CSRF_COOKIE_NAME
CSRF_HEADER_NAME
CSRF_TOKEN_TTL_SECONDS
SESSION_COOKIE_SECURE
```

Use safe placeholders in `.env.example`. Document how to generate secrets locally. Never commit real production values.

## CSRF endpoint

Add:

```text
GET /api/v1/auth/csrf
```

Behavior:

- create a cryptographically random nonce;
- include issuance/expiry information in the signed token format;
- HMAC-sign with the configured secret;
- set a readable CSRF cookie;
- return the token in a response field;
- set `SameSite=Lax`, `Path=/`, and environment-appropriate `Secure`;
- do not mark the CSRF cookie HttpOnly because the frontend must send the token header.

## CSRF dependency or middleware

For `POST`, `PUT`, `PATCH`, and `DELETE` authentication/profile routes:

- require configured header;
- require CSRF cookie;
- compare values in constant time;
- validate HMAC signature;
- validate expiry;
- verify `Origin` against `FRONTEND_ORIGIN`;
- use `Referer` only as a documented fallback;
- reject with 403 and a stable error code.

Do not apply CSRF validation to safe read-only routes such as health, CSRF bootstrap, and current-user retrieval.

## CORS and proxy behavior

- Prefer relative frontend API URLs.
- Keep local Vite proxy or explicit CORS configuration consistent.
- If CORS is used, allow only configured origins and set credentials explicitly.
- Never use wildcard origin with credentialed requests.

## Tests

Cover:

- valid token;
- missing header;
- missing cookie;
- mismatch;
- invalid signature;
- expired token;
- invalid origin;
- allowed origin;
- safe route unaffected;
- cookie attributes by environment.

## Verification

Run backend checks and manually inspect response cookies.

## Commit

```text
feat(auth): add CSRF and origin protection
```

## Stop condition

Commit, push, report token design without revealing secrets, and stop.

---

# Step 8: Add authentication dependencies and safe current-user resolution

## Goal

Create backend dependencies that translate an HttpOnly session cookie into an authenticated TrackSea user.

## Requirements

Implement:

- optional current-user dependency;
- required current-user dependency;
- session-cookie extraction;
- active-session lookup;
- active-user check;
- generic 401 response;
- no database lookup when no cookie is present unless required;
- no user or session details in unauthorized errors.

The dependency must not:

- trust frontend state;
- trust a user ID header;
- accept bearer tokens;
- expose session database rows to route handlers unnecessarily.

## Tests

Cover:

- missing cookie;
- malformed/unknown cookie;
- expired session;
- revoked session;
- inactive user;
- valid user;
- optional dependency returns `None` for anonymous request;
- required dependency returns generic 401.

## Verification

Run backend checks and ensure existing health routes remain public.

## Commit

```text
feat(auth): add current-user dependencies
```

## Stop condition

Commit, push, report, and stop.

---

# Step 9: Add email-and-password registration

## Goal

Create the first complete user-account creation flow.

## Endpoint

```text
POST /api/v1/auth/register
```

## Request

```json
{
  "email": "person@example.com",
  "password": "a sufficiently long passphrase",
  "display_name": "Marine Observer"
}
```

## Behavior

- require valid CSRF and trusted origin;
- validate and normalize email;
- validate display name length and content;
- validate password policy;
- check normalized email uniqueness;
- hash password;
- create the user and session in one transaction where practical;
- set the TrackSea session cookie;
- return a safe user representation;
- return 201;
- never return password, hash, token, CSRF secret, or internal session fields.

## Display-name rules

Define and test:

- minimum and maximum length;
- Unicode support;
- whitespace normalization;
- rejection of empty/only-whitespace names;
- no uniqueness requirement in Sprint 2.

## Conflict handling

Do not leak authentication method details.

Use a stable generic conflict response such as:

```text
account_conflict
```

Do not say whether the existing account is password or Google based.

## Concurrency

- Rely on the database unique constraint as the final authority.
- Catch and map unique-constraint races safely.
- Do not allow duplicate users from concurrent requests.

## Tests

Cover:

- successful registration;
- returned safe user;
- session row created;
- cookie set;
- invalid email;
- weak/common password;
- invalid display name;
- duplicate email;
- case-insensitive duplicate;
- concurrent uniqueness behavior where practical;
- CSRF rejection;
- no secret leakage.

## Verification

Run migration-backed tests and manually register through HTTP.

## Commit

```text
feat(auth): add user registration
```

## Stop condition

Commit, push, report endpoint contract and tests, and stop.

---

# Step 10: Add password login and logout

## Goal

Authenticate existing password users and safely terminate the current session.

## Login endpoint

```text
POST /api/v1/auth/login
```

Request:

```json
{
  "email": "person@example.com",
  "password": "the passphrase"
}
```

Behavior:

- require CSRF and trusted origin;
- normalize email;
- load user by normalized email;
- run real password verification for known password users;
- run dummy verification for unknown or Google-only users;
- use the same generic failure for unknown email, wrong password, inactive user, and Google-only account;
- create a new session on success;
- never reuse an existing cookie token;
- set session cookie;
- return safe user profile.

Generic failure:

```text
401 invalid_credentials
```

Do not identify whether an account exists or which login method it uses.

## Logout endpoint

```text
POST /api/v1/auth/logout
```

Behavior:

- require CSRF and trusted origin;
- if a valid session exists, revoke it;
- clear the session cookie;
- return 204;
- remain idempotent when the cookie is missing or already invalid;
- do not revoke every session in this sprint.

## Tests

Cover:

- successful login;
- wrong password;
- unknown email;
- Google-only account using password endpoint;
- inactive account;
- timing path uses dummy hash;
- new session per login;
- logout revokes session;
- logout clears cookie;
- repeated logout;
- revoked session cannot access protected routes;
- CSRF failures.

## Verification

Manually register, logout, login, refresh, and logout again.

## Commit

```text
feat(auth): add password login and logout
```

## Stop condition

Commit, push, report, and stop.

---

# Step 11: Add PostgreSQL-backed authentication throttling

## Goal

Reduce automated password guessing without Redis or a misleading per-process-only limiter.

## Requirements

Implement a throttling service that:

- derives account and IP keys;
- HMAC-hashes keys with a configured secret;
- never stores raw passwords, raw email keys, or combined raw email/IP strings;
- tracks failures in fixed or rolling windows;
- blocks requests after configurable thresholds;
- returns a generic 429 response;
- supplies `Retry-After` when practical;
- resets or reduces account failure state after successful login according to the documented design;
- cleans expired throttle rows opportunistically or through a testable cleanup method;
- uses transaction-safe updates.

## Client address rules

- Use the direct request client address locally.
- Do not trust forwarded headers unless trusted proxies are explicitly configured.
- Document production proxy requirements.

## Configuration

Add settings for:

```text
AUTH_THROTTLE_SECRET
AUTH_ACCOUNT_FAILURE_LIMIT
AUTH_IP_FAILURE_LIMIT
AUTH_THROTTLE_WINDOW_SECONDS
AUTH_BLOCK_SECONDS
```

## Integration

Apply throttling to password login.

Do not apply failure counters to successful registrations or Google credential validation unless Step 0 explicitly includes separate Google abuse controls.

## Tests

Cover:

- failures increment;
- account threshold;
- IP threshold;
- block expiry;
- success reset behavior;
- keys are not stored raw;
- 429 response;
- concurrent updates where practical;
- unknown and known accounts receive equivalent responses.

## Verification

Run backend checks and manually trigger a test threshold using safe local values.

## Commit

```text
feat(auth): add login throttling
```

## Stop condition

Commit, push, report configured defaults and limitations, and stop.

---

# Step 12: Add current-user profile endpoints

## Goal

Expose safe authenticated identity and a minimal editable profile.

## Current-user endpoint

```text
GET /api/v1/auth/me
```

Return only:

- user ID;
- email;
- email verification status;
- display name;
- authentication-method summary if useful and non-sensitive;
- creation timestamp if product-approved.

Do not return:

- password hash;
- external provider subject;
- session token hash;
- throttle state;
- internal audit metadata.

## Profile update endpoint

```text
PATCH /api/v1/users/me
```

Sprint 2 permits only:

- display-name update.

Require:

- authenticated user;
- CSRF token;
- trusted origin;
- same display-name validation as registration.

Out of scope:

- email change;
- password change;
- account deletion;
- avatar;
- bio;
- location;
- roles;
- public profile settings.

## Tests

Cover:

- current user success;
- anonymous 401;
- safe serialized fields;
- valid display-name update;
- invalid update;
- attempt to update disallowed fields;
- CSRF failure;
- inactive user.

## Verification

Run checks and manually update the profile through HTTP.

## Commit

```text
feat(users): add current-user profile
```

## Stop condition

Commit, push, report, and stop.

---

# Step 13: Configure Google Identity Services and verifier boundary

## Goal

Prepare safe Google authentication without implementing user creation or linking yet.

## Dependencies

Backend:

- add Google's maintained authentication library or another explicitly approved verifier;
- do not add a generic OAuth framework unless justified.

Frontend:

- prefer loading the official Google Identity Services script directly;
- do not add an unmaintained wrapper package.

## Environment variables

Add safe placeholders for:

```text
GOOGLE_CLIENT_ID
VITE_GOOGLE_CLIENT_ID
```

The values are client identifiers, not secrets, but production values should still be managed through deployment configuration.

Do not add `GOOGLE_CLIENT_SECRET` for the selected GIS credential callback flow.

## Backend verifier boundary

Create an interface or injectable service such as:

```text
GoogleCredentialVerifier
```

It must return a typed verified identity containing only required claims:

```text
subject
email
email_verified
name
picture (optional and not persisted in this sprint)
```

Real verification must check:

- signature via Google's maintained verification path;
- issuer;
- audience equals configured client ID;
- expiration;
- subject exists;
- email exists;
- email verification for account creation.

Do not use Google's token-info endpoint in production request handling. It may be used only for manual debugging.

## Frontend setup

- Add type declarations for the required `google.accounts.id` API surface.
- Load the script once.
- Do not enable One Tap or automatic sign-in in Sprint 2.
- Do not render the button until a client ID is configured.
- Show a clear development message when Google is not configured.

## Tests

- Use a fake verifier in service/API tests.
- Unit-test claim mapping.
- Unit-test invalid audience, issuer, expiration, missing subject, and unverified email through mocked verifier outcomes.
- CI must not require real Google credentials or network calls.

## Verification

Run backend/frontend checks and confirm the app still works without Google configuration.

## Commit

```text
build(auth): configure Google identity services
```

## Stop condition

Commit, push, report dependency and configuration choices, and stop.

---

# Step 14: Implement Google sign-in backend

## Goal

Authenticate existing Google identities and create new Google-only TrackSea accounts safely.

## Endpoint

```text
POST /api/v1/auth/google
```

Request:

```json
{
  "credential": "google-id-token"
}
```

The credential is transient and must never be logged or persisted.

## Behavior

1. Require CSRF and trusted origin.
2. Verify the Google credential through the verifier boundary.
3. Look up `(provider=google, subject=sub)`.
4. When identity exists:
   - load active TrackSea user;
   - update `last_login_at`;
   - create TrackSea session;
   - return 200.
5. When identity does not exist and normalized verified email is unused:
   - create TrackSea user with `password_hash=NULL`;
   - mark email verified from provider evidence;
   - choose display name from verified profile name with validation/fallback;
   - create external identity;
   - create TrackSea session;
   - return 201.
6. When normalized email matches an existing TrackSea user without this identity:
   - do not link;
   - return 409 `account_link_required`;
   - do not reveal password or other provider details.

## Transaction behavior

- User, external identity, and session creation must be atomic where practical.
- Database constraints remain final authority for duplicate subject and email races.
- Map integrity errors to stable safe responses.

## Tests

Cover:

- existing Google identity login;
- new Google user creation;
- verified email requirement;
- duplicate subject race;
- email collision returns link-required;
- inactive linked user;
- safe profile response;
- session cookie;
- credential not logged or persisted;
- invalid credential outcomes;
- CSRF and origin failures.

## Verification

Run automated tests. Manual real-Google verification may wait until Step 19 frontend button and local Cloud setup exist.

## Commit

```text
feat(auth): add Google sign-in backend
```

## Stop condition

Commit, push, report, and stop.

---

# Step 15: Implement explicit Google account linking

## Goal

Allow a signed-in password user to prove Google ownership and link that identity safely.

## Endpoint

```text
POST /api/v1/auth/google/link
```

## Requirements

- Require an authenticated TrackSea user.
- Require CSRF and trusted origin.
- Verify Google credential.
- Require verified provider email.
- Require normalized Google email to match the authenticated TrackSea user's normalized email for Sprint 2.
- Reject an identity already linked to another TrackSea user.
- Create the external identity atomically.
- Do not create a new user.
- Do not create or return Google access tokens.
- Return a safe updated authentication-method summary.

## Linking collision behavior

- Same identity already linked to current user: idempotent success or documented safe conflict.
- Identity linked to another user: generic conflict.
- Email mismatch: reject.
- Google email missing/unverified: reject.

## Out of scope

- unlinking Google;
- changing TrackSea email;
- adding a password to a Google-only account;
- merging two TrackSea users;
- transferring identities.

## Tests

Cover all linking and collision cases, CSRF, inactive users, and transaction races.

## Verification

Run backend checks and inspect external-identity rows using non-secret fields only.

## Commit

```text
feat(auth): add explicit Google account linking
```

## Stop condition

Commit, push, report, and stop.

---

# Step 16: Add the typed frontend API client

## Goal

Create one safe, typed browser boundary for TrackSea authentication APIs.

## Requirements

Implement a central fetch client that:

- uses relative API paths where practical;
- sends `credentials: "include"`;
- obtains a CSRF token before unsafe requests;
- sends `X-CSRF-Token`;
- stores CSRF state only in memory or reads the CSRF cookie as designed;
- never stores session tokens;
- parses structured API errors;
- handles empty 204 responses;
- handles 401 without infinite retry loops;
- provides request cancellation where useful;
- does not log credentials or tokens.

Create typed methods for:

- get CSRF token;
- register;
- login;
- logout;
- get current user;
- update profile;
- Google sign-in;
- Google linking.

## Vite and local networking

- Use the existing Docker development stack.
- Configure or preserve a Vite proxy for relative `/api` requests if that is the selected local architecture.
- Avoid hard-coded Docker service names in browser-visible code.
- Keep `VITE_API_BASE_URL` optional and documented if introduced.

## Tests

Mock fetch and cover:

- credentials included;
- CSRF bootstrap and header;
- success responses;
- structured errors;
- 401 handling;
- 204 logout;
- no token persistence.

## Verification

Run frontend format, lint, type check, tests, and build.

## Commit

```text
feat(frontend): add authentication API client
```

## Stop condition

Commit, push, report, and stop.

---

# Step 17: Add frontend authentication state

## Goal

Represent anonymous, loading, authenticated, and failed session states consistently.

## Requirements

Create an `AuthProvider` and `useAuth` hook with states similar to:

```text
loading
anonymous
authenticated
error
```

Behavior:

- on application startup, call current-user endpoint;
- treat 401 as anonymous, not an application crash;
- store only safe user profile in React memory;
- update state after registration, login, Google login, profile update, and logout;
- clear user state on logout or expired-session 401;
- prevent duplicate startup requests in development strict mode where practical;
- avoid a global state library.

Create protected-route behavior that:

- waits while loading;
- redirects anonymous users to sign in;
- renders authenticated content only with a current user.

## Tests

Cover:

- initial loading;
- anonymous startup;
- authenticated startup;
- login transition;
- logout transition;
- expired-session transition;
- error state;
- protected-route behavior.

## Verification

Run frontend checks and build.

## Commit

```text
feat(frontend): add authentication state
```

## Stop condition

Commit, push, report, and stop.

---

# Step 18: Add email registration and sign-in screens

## Goal

Deliver accessible, minimal password-authentication UI without final product styling.

## Routes

Suggested routes:

```text
/register
/sign-in
```

Use React Router if accepted in Step 0. Do not create a custom router.

## Registration form

Fields:

- display name;
- email;
- password.

Requirements:

- labels associated with inputs;
- `autocomplete="name"`;
- `autocomplete="email"`;
- `autocomplete="new-password"`;
- allow paste and password managers;
- explain the 15-character minimum without complexity-rule language;
- loading state;
- disabled duplicate-submit state;
- accessible field and form errors;
- safe conflict message;
- redirect to authenticated application after success.

## Sign-in form

Fields:

- email;
- password.

Requirements:

- `autocomplete="username"` or email as appropriate;
- `autocomplete="current-password"`;
- generic invalid-credentials message;
- loading and disabled state;
- no account enumeration;
- redirect to authenticated application after success.

## Out of scope

- password confirmation unless product explicitly requests it;
- password-strength theatrics;
- password reset link functionality;
- email verification messaging;
- final branding system;
- social feed or onboarding wizard.

## Tests

Cover validation, submission, loading, errors, successful transitions, and accessibility-oriented queries.

## Verification

Run frontend checks, build, and manual form navigation.

## Commit

```text
feat(frontend): add registration and sign-in screens
```

## Stop condition

Commit, push, report, and stop.

---

# Step 19: Add the official Google Sign-In button

## Goal

Connect Google Identity Services UI to the TrackSea Google authentication endpoint.

## Google Cloud prerequisites

Document that the maintainer must create an OAuth 2.0 Web client in Google Cloud and configure authorized JavaScript origins such as:

```text
http://localhost:5173
```

Production origins are not invented in this sprint.

No client secret is required for the selected Google Identity Services credential callback flow.

## Frontend component

Implement a focused `GoogleSignInButton` that:

- loads Google's official script once;
- initializes `google.accounts.id` once per client ID;
- renders the official button into a stable element;
- uses button flow only;
- does not enable One Tap or automatic sign-in;
- receives the credential callback;
- immediately sends the credential to TrackSea backend through the typed client;
- does not decode the token for authorization decisions;
- does not persist the credential;
- clears transient credential references after completion;
- handles missing client ID clearly in development;
- handles script-load and provider errors accessibly.

## Placement

Show the button on:

- registration page;
- sign-in page;
- authenticated profile/settings page for explicit linking when the user has no Google identity.

## Account-link-required UX

When Google sign-in returns `account_link_required`:

- explain that an account already exists for that email;
- ask the user to sign in with their existing method;
- after password sign-in, offer the explicit link action;
- do not silently link.

## Logout behavior

If Google automatic selection is not enabled, no Google logout is required. TrackSea logout revokes only the TrackSea session.

Do not revoke the user's Google account consent on normal TrackSea logout.

## Tests

Mock the global GIS API and cover:

- script success;
- script failure;
- missing client ID;
- credential callback;
- backend success;
- backend failure;
- link-required response;
- component cleanup;
- no token persistence.

## Verification

- Run frontend checks and build.
- With a local Google client ID, manually render the official button and complete a real sign-in.
- Confirm the backend creates a TrackSea session and the browser does not store the Google credential.

## Commit

```text
feat(frontend): add Google sign-in
```

## Stop condition

Commit, push, report manual Google result or explain why credentials are unavailable, and stop.

---

# Step 20: Add the authenticated application shell and profile page

## Goal

Provide the first meaningful signed-in TrackSea shell without beginning later product features.

## Application shell

Display:

- TrackSea name and tagline;
- signed-in display name;
- safe email display;
- logout action;
- minimal placeholder explaining that observations arrive in a later sprint.

Do not add observation forms, maps, species search, uploads, dashboards, or gamification.

## Profile page

Allow:

- display-name editing;
- viewing safe email and verification status;
- viewing available authentication methods;
- linking Google for an authenticated password user when eligible.

Do not allow:

- email change;
- password change;
- unlinking only auth method;
- avatar upload;
- account deletion;
- public profile settings.

## Routing

- Anonymous user visiting authenticated routes is redirected to sign in.
- Authenticated user visiting sign-in/register is redirected to app home unless a documented linking flow requires otherwise.
- Preserve a safe internal return path if implemented.
- Never redirect to an arbitrary external URL from query parameters.

## Tests

Cover protected routes, logout, profile update, linking action visibility, successful update, and error states.

## Verification

Run frontend checks, build, and manual flow.

## Commit

```text
feat(frontend): add authenticated application shell
```

## Stop condition

Commit, push, report, and stop.

---

# Step 21: Expand backend authentication and security tests

## Goal

Create comprehensive automated coverage for security boundaries and database behavior.

## Test categories

### Password and identity

- email normalization;
- password policy;
- Argon2id hashing and verification;
- dummy-hash path;
- Google-only user password-login failure;
- inactive user behavior.

### Sessions

- creation;
- digest persistence;
- expiration;
- revocation;
- cookie flags;
- no raw token storage;
- session fixation prevention;
- current-user dependency.

### CSRF and origin

- every unsafe auth/profile endpoint requires valid CSRF;
- safe endpoints do not mutate state;
- invalid origin fails;
- wildcard CORS is absent when credentials are enabled.

### Registration and login

- success;
- duplicate/race behavior;
- generic failures;
- throttling;
- transaction rollback;
- safe responses.

### Google

- signature/verifier success path through fake boundary;
- invalid audience;
- invalid issuer;
- expiration;
- missing subject;
- unverified email;
- existing identity;
- new user;
- collision/link-required;
- explicit linking;
- duplicate identity race.

### Migrations

- upgrade from empty schema;
- constraints exist;
- downgrade;
- re-upgrade;
- no unrelated TrackSea tables.

## Database test strategy

- Use PostgreSQL for integration tests involving models, migrations, constraints, and transactions.
- Isolate test data reliably.
- Do not depend on the developer's normal database.
- Do not call real Google endpoints in automated tests.

## Verification

Run the entire backend suite, formatting, linting, type checking, migration tests, and coverage reporting if the repository already supports it.

Do not introduce a coverage percentage gate unless justified and agreed.

## Commit

```text
test(auth): cover backend authentication workflows
```

## Stop condition

Commit, push, report test count and remaining gaps, and stop.

---

# Step 22: Expand frontend and full-stack authentication tests

## Goal

Verify frontend behavior and the browser-to-backend contract without making CI depend on real Google credentials.

## Frontend tests

Cover:

- auth API client;
- CSRF handling;
- AuthProvider states;
- protected routes;
- registration form;
- sign-in form;
- Google button wrapper;
- account-link-required UX;
- profile update;
- logout;
- safe error display;
- no storage of session/Google tokens.

## Full-stack integration

Add practical integration coverage for:

- frontend request credentials;
- CORS or Vite proxy behavior;
- cookie persistence;
- registration to current-user flow;
- logout to unauthorized current-user flow.

A browser automation framework is optional. Do not introduce Playwright or Cypress merely for one smoke test unless Step 0 and the maintainer approve the dependency and CI cost.

Manual validation remains required in Step 25.

## Verification

Run:

- frontend formatting;
- frontend linting;
- TypeScript type checking;
- Vitest;
- production build;
- relevant full-stack tests.

## Commit

```text
test(auth): cover frontend authentication workflows
```

## Stop condition

Commit, push, report, and stop.

---

# Step 23: Update authentication documentation

## Goal

Make authentication understandable and runnable without relying on this conversation.

## Documentation files

Create or update as appropriate:

```text
docs/architecture/authentication-overview.md
docs/development/authentication.md
docs/development/local-development.md
README.md
.env.example
```

Do not duplicate the ADR. The architecture overview should explain how the accepted decision works in practice.

## Required documentation

Document:

### Local authentication configuration

- required environment variables;
- safe secret generation commands;
- local cookie behavior;
- frontend/backend origin behavior;
- database migration commands;
- starting and resetting the local stack;
- creating a test user through the UI.

### Google Cloud setup

- create or select a Google Cloud project;
- configure the OAuth consent screen;
- create OAuth 2.0 Web client credentials;
- add authorized JavaScript origins;
- use `http://localhost:5173` for local development when applicable;
- set `GOOGLE_CLIENT_ID` and `VITE_GOOGLE_CLIENT_ID`;
- explain that no client secret is needed for the selected GIS credential callback flow;
- never commit credentials;
- explain manual test steps;
- explain that CI uses fakes and requires no Google credentials.

### Cookie behavior

- session cookie purpose;
- HttpOnly;
- Secure by environment;
- SameSite=Lax;
- Path `/`;
- no Domain attribute;
- production `__Host-` recommendation;
- session lifetime;
- logout revocation.

### CSRF requirements

- why cookie auth requires CSRF defense;
- CSRF bootstrap endpoint;
- readable CSRF cookie;
- `X-CSRF-Token` header;
- origin validation;
- which methods are protected;
- common troubleshooting.

### Account-linking behavior

- existing Google identity;
- new Google user;
- email collision;
- explicit password-user linking;
- no silent linking;
- deferred unlinking and merging.

### Error and privacy behavior

- generic invalid credentials;
- no raw secrets in logs;
- no localStorage auth;
- no Google access-token storage;
- rate-limiting behavior;
- proxy/IP caution.

### Known limitations and deferred work

- password reset;
- email verification delivery;
- password change;
- email change;
- MFA/WebAuthn;
- additional providers;
- account deletion;
- session-management UI;
- global logout;
- advanced security monitoring;
- production reverse proxy and TLS deployment.

Every documented command must match the implementation.

## Verification

- Follow the documentation from a clean local environment as closely as practical.
- Run format/pre-commit checks.
- Confirm no secret values are present.

## Commit

```text
docs: add authentication development guide
```

## Stop condition

Commit, push, report documentation verification, and stop.

---

# Step 24: Update CI for authentication integration tests

## Goal

Run authentication quality and database integration checks automatically on pull requests.

## Backend CI

Update the existing workflow only as required to add:

- PostgreSQL/PostGIS service when database tests require it;
- test database environment variables;
- Alembic upgrade verification;
- authentication test suite;
- existing format, lint, and type checks.

Use safe CI-only credentials.

Do not use production secrets.

## Frontend CI

Preserve:

- lockfile install;
- format check;
- lint;
- type check;
- tests;
- production build.

Do not require a real Google client ID. Use tests that mock Google Identity Services.

## Workflow security

- keep minimal permissions such as `contents: read`;
- do not expose secrets to pull requests from forks;
- do not add deployment behavior;
- use trusted action versions;
- avoid unnecessary third-party actions.

## Verification

- Validate YAML locally.
- Run equivalent commands locally.
- Push and inspect actual GitHub Actions jobs.
- Fix failures only within Sprint 2 scope.

## Commit

```text
ci: add authentication integration checks
```

## Stop condition

Commit, push, report actual CI result, and stop.

---

# Step 25: Final Sprint 2 validation

## Goal

Prove the complete authentication workflow works from a clean environment before merge.

This is a validation step. Normally it creates no commit.

## Clean environment

1. Update the branch from current `main` using the project's chosen workflow.
2. Confirm clean working tree.
3. Create local `.env` from `.env.example` and provide local-only secrets.
4. Configure a valid local Google client ID when available.
5. Reset or create a disposable test database.
6. Build and start the Docker stack.
7. Run migrations from empty schema.

## Manual email/password flow

Verify:

1. Open frontend.
2. Fetch CSRF bootstrap successfully.
3. Register a user.
4. Confirm safe profile response.
5. Confirm session cookie flags in browser developer tools.
6. Refresh and remain signed in.
7. Update display name.
8. Log out.
9. Confirm session row is revoked.
10. Confirm current-user endpoint returns 401.
11. Log back in.
12. Trigger invalid credentials and verify generic response.
13. Trigger local rate limit with safe test thresholds and verify 429.

## Manual Google flow

When valid local Google configuration is available:

1. Render official Google button.
2. Sign in with a Google account whose email is unused.
3. Confirm TrackSea user and external identity are created.
4. Confirm TrackSea session cookie is set.
5. Confirm no Google credential is stored in browser storage or database.
6. Log out of TrackSea.
7. Sign in again with the same Google identity.
8. Confirm same TrackSea user is used.
9. Test email collision with an existing password account.
10. Confirm `account_link_required` behavior.
11. Sign in by password and explicitly link Google.
12. Confirm subsequent Google sign-in reaches the same TrackSea user.

If real Google credentials are unavailable, automated fake-verifier coverage may pass, but Sprint 2 must remain draft and the missing manual verification must be reported clearly.

## Database inspection

Confirm:

- password hashes are Argon2id hashes;
- raw passwords are absent;
- raw session tokens are absent;
- Google ID tokens are absent;
- Google access/refresh tokens are absent;
- external identity uses Google `sub`;
- session expiry/revocation values behave correctly;
- throttle keys are not stored raw;
- no unrelated product tables exist.

## Security inspection

Confirm:

- session cookie is HttpOnly;
- Secure behavior changes by environment;
- SameSite is explicit;
- no Domain attribute;
- CSRF token required on unsafe endpoints;
- invalid Origin rejected;
- wildcard credentialed CORS absent;
- no secrets in Git;
- no secrets in logs;
- no auth tokens in localStorage/sessionStorage;
- generic login errors;
- inactive users cannot authenticate;
- revoked and expired sessions fail.

## Automated checks

Run:

```text
make format-check
make lint
make type-check
make test
make build
make pre-commit
```

Also run migration upgrade/downgrade/re-upgrade and inspect GitHub Actions.

## Scope review

Confirm Sprint 2 did not add:

- observations;
- taxonomy;
- media uploads;
- maps;
- identifications;
- Marine Life;
- organizations;
- roles;
- moderation;
- gamification;
- password reset;
- email delivery;
- MFA;
- providers beyond Google;
- production deployment automation.

## Completion behavior

If everything passes and no files change:

- do not create a commit;
- report Step 25 passed without changes.

If a small Sprint 2 defect requires correction:

- create a focused semantic commit;
- push it;
- rerun affected and full validation;
- report the commit.

Do not merge during this step.

---

# Step 26: Complete the Sprint 2 pull request

## Goal

Present Sprint 2 for review with complete evidence and merge only after approval.

## Pull request title

```text
feat(auth): add user authentication
```

## Required PR body

Include:

- Sprint objective;
- architecture summary;
- email/password flow;
- session and cookie design;
- CSRF design;
- Google Identity Services flow;
- account-linking rules;
- throttling design;
- backend modules and endpoints;
- frontend routes and state;
- database tables and migration behavior;
- commit list;
- dependencies added and why;
- commands run;
- automated test results;
- GitHub Actions results;
- manual email/password test result;
- manual Google test result or explicit blocker;
- privacy and security review;
- environment variables;
- local startup instructions;
- known limitations;
- deferred work;
- unresolved risks;
- explicit confirmation that no other product domains were added.

## Review checklist

Before marking ready:

- Step 25 passed;
- CI passed;
- migration reviewed;
- no secret-scanning concern;
- no raw tokens persisted;
- Google credential flow manually tested when credentials are available;
- docs match implementation;
- PR is not merged prematurely.

## Merge strategy

Use a normal merge commit after approval so meaningful Sprint 2 commits remain visible.

Delete the feature branch after merge when safe.

---

# Definition of Done for Sprint 2

Sprint 2 is done only when:

- the authentication ADR is accepted;
- user, external identity, session, and throttle persistence is migrated;
- passwords use Argon2id;
- registration works;
- password login works;
- logout revokes the current server session;
- current-user retrieval works;
- display-name update works;
- CSRF protection covers unsafe routes;
- trusted-origin checks work;
- session cookies have correct attributes;
- raw session tokens are never stored;
- browser storage contains no auth token;
- Google Sign-In uses the official GIS button;
- Google ID tokens are validated server-side;
- Google `sub` is the provider identity;
- Google access and refresh tokens are not stored;
- account collision requires explicit linking;
- authenticated Google linking works for an eligible password user;
- login throttling works;
- backend and frontend tests pass;
- migration verification passes;
- GitHub Actions passes;
- local development and Google setup are documented;
- full validation passes;
- the PR is reviewed before merge.

# Recommended Codex execution pattern

Do not ask Codex to complete the whole playbook in one pass.

Begin with:

```text
Read `.ai/playbooks/sprint-2-authentication.md` and all required documents. Complete Step 0 only. Do not modify files. Report the authentication design brief and stop.
```

After reviewing Step 0:

```text
Proceed with Step 1 only on `feat/authentication`. Follow the playbook exactly, create the specified semantic commit, push, report, and stop.
```

Repeat one step at a time.

Before every next step:

- review the report;
- inspect the pushed commit when practical;
- confirm scope;
- confirm checks passed;
- confirm no security shortcut was introduced.

# Official references reviewed for this playbook

The implementation should prefer current official documentation and maintained libraries. Re-check these sources during Step 0 because security guidance and provider APIs evolve.

- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP OAuth 2.0 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
- NIST SP 800-63B: https://pages.nist.gov/800-63-4/sp800-63b.html
- Google Identity Services overview: https://developers.google.com/identity/gsi/web/guides/overview
- Display the Sign in with Google button: https://developers.google.com/identity/gsi/web/guides/display-button
- Verify Google ID tokens server-side: https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
- Google OpenID Connect reference: https://developers.google.com/identity/openid-connect/reference
- FastAPI password hashing tutorial: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
