# ADR-003: Authentication and server-side sessions

- Status: Accepted
- Date: 2026-08-28

## Context

TrackSea needs a user identity boundary before observations and other attributed
scientific records can be created. The MVP must support email-and-password
authentication and optional Google authentication while keeping authorization
decisions inside the TrackSea backend.

Authentication data includes passwords, browser session credentials, external
identity claims, and private account information. A compromised or incorrectly
linked identity could expose a user's private data and allow records to be
created under the wrong attribution. The design therefore needs revocable
sessions, explicit account linking, protection against cross-site requests, and
generic failure behavior that does not disclose whether an account exists.

The solution must fit the FastAPI modular monolith established by ADR-001 and
ADR-002. PostgreSQL remains the system of record. The MVP does not justify an
external identity platform, Redis, a separate authentication service, or a
browser bearer-token architecture.

## Decision

TrackSea owns authentication, application sessions, and authorization. External
identity providers may establish evidence about an identity, but they do not
grant TrackSea permissions. The backend is the authority for the current user
and every authorization decision; frontend state is never an authorization
boundary.

Authentication and user identity remain modules within the FastAPI modular
monolith. Route handlers stay thin, authentication behavior belongs in services,
and persistence operations use explicit repository or data-access boundaries.

### Email and password authentication

TrackSea supports registration and sign-in with an email address and password.
Passwords are normalized with Unicode NFC and hashed with Argon2id using the
maintained library's recommended parameters. Passwords are never encrypted or
stored in plaintext.

The password policy favors length over composition rules. It requires at least
15 Unicode characters, permits spaces, supports a practical maximum of 128
characters, and checks the complete candidate against a local, license-compatible
common-password blocklist. Login uses a dummy Argon2id hash for unknown or
passwordless accounts to reduce useful timing differences. Authentication
failures remain generic and do not reveal whether an account exists or which
authentication method it uses.

### Opaque server-side sessions

Every successful registration or authentication event creates a new opaque
TrackSea session using at least 256 bits of cryptographically secure randomness.
The raw session token exists only in the browser cookie and transient server
memory. PostgreSQL stores only a SHA-256 or stronger one-way digest of the raw
token together with the user, creation time, absolute expiry, last-seen time,
and revocation state.

Sessions have a configurable absolute lifetime, initially 30 days. Expired or
revoked sessions are rejected. Logout revokes the current database session and
clears its cookie. TrackSea does not use sliding expiry for Sprint 2 and does not
reuse a pre-authentication or previous session identifier after authentication.

The browser session cookie is configured centrally with:

```text
HttpOnly=true
SameSite=Lax
Path=/
Domain omitted
Secure=false only for local HTTP development
Secure=true outside local HTTP development
```

Production configuration should use a `__Host-` prefixed cookie name when HTTPS
is available. The raw session token is never returned in JSON and is never
stored in browser `localStorage` or `sessionStorage`.

TrackSea does not use JWT bearer tokens for browser sessions. Session meaning
and authorization state remain on the server so expiry, revocation, inactive
users, and future authorization changes can be enforced immediately.

### CSRF and origin protection

Cookie-authenticated unsafe requests use a signed double-submit CSRF pattern
plus trusted-origin validation. A bootstrap endpoint creates a random,
time-limited, HMAC-signed token, sets it in a readable cookie, and returns the
same value in a response body. The frontend sends that value in the
`X-CSRF-Token` header.

The backend compares the cookie and header in constant time, validates the
signature and expiry, and binds authenticated tokens to the current TrackSea
session without exposing the session token or its persisted digest. It also
requires the request `Origin`, or a strictly validated `Referer` fallback, to
match the configured frontend origin. Registration, password login, Google
sign-in, logout, account linking, and profile changes are protected. `SameSite`
is defense in depth and is not the only CSRF control.

The preferred deployment is a same-origin frontend and API, including a local
Vite proxy. If cross-origin development or deployment is required, CORS must
allow only explicitly configured origins, enable credentials deliberately, and
never combine credentialed requests with a wildcard origin.

### Login throttling

Failed password login attempts are throttled through PostgreSQL without Redis.
The service tracks configurable windows for both normalized-email-derived and
direct-client-IP-derived keys. Keys are protected with HMAC before persistence;
raw email and IP combinations are not stored in throttle rows.

Initial defaults are five account-key failures and 20 IP-key failures per
15-minute window, followed by a 15-minute block. Responses remain generic and
use `Retry-After` where practical. Forwarded client-address headers are not
trusted unless a future deployment explicitly configures trusted proxies.

### Google Identity Services

Google Identity Services is the only external identity provider in Sprint 2.
The React application renders Google's official button and uses the JavaScript
credential callback flow. It immediately sends the short-lived Google ID token
to the TrackSea backend without persisting it.

The backend verifies the token through Google's maintained verification library,
including signature, issuer, audience, expiry, subject, email, and email
verification requirements. The Google `sub` claim is the stable external
identity identifier; email is not used as the provider identity key.

This flow requires a Google web client ID but no Google client secret. TrackSea
does not request Google API scopes and does not store Google ID tokens, access
tokens, or refresh tokens. Successful Google authentication creates the same
opaque TrackSea server-side session used by password authentication. Google does
not own TrackSea authorization.

### Explicit account linking

Account linking follows these rules:

- An existing `(provider=google, subject=sub)` identity signs in its linked
  TrackSea user.
- A new Google identity with a verified, unused normalized email creates a new
  Google-only TrackSea user and external identity.
- A new Google identity whose normalized email matches an existing TrackSea
  account is not linked automatically and returns `account_link_required`.
- An authenticated password user may explicitly link a verified Google identity
  with a matching normalized email through a CSRF-protected action.
- An identity linked to another TrackSea user cannot be transferred or merged.

Unlinking the only authentication method, merging users, adding a password to a
Google-only account, and changing the account email are outside Sprint 2.

### Deferred capabilities

Password reset, email-verification delivery, password changes, email changes,
multi-factor authentication, WebAuthn, additional providers, account deletion,
global logout, and session-management UI are deferred. Production TLS and
reverse-proxy deployment are also separate work, although secure cookies are
mandatory outside local HTTP development.

## Consequences

### Positive

- TrackSea has one authentication and authorization model regardless of sign-in
  method.
- Server-side sessions can be revoked immediately and do not place authorization
  claims in browser-controlled storage.
- Only digests of high-entropy session tokens are persisted.
- Explicit linking prevents an email match alone from taking over an existing
  account.
- PostgreSQL provides durable, multi-process throttling without new
  infrastructure.
- The design fits the existing FastAPI modular monolith and Docker Compose stack.

### Negative and security trade-offs

- Protected requests require a PostgreSQL session lookup, so database
  availability affects authentication availability.
- Custom authentication code requires careful security review, migration tests,
  cookie inspection, CSRF tests, rate-limit tests, and ongoing dependency updates.
- Cookie sessions require correct TLS, proxy, origin, and cookie configuration;
  local HTTP is intentionally less protected because `Secure` must be disabled.
- HttpOnly protects token confidentiality from direct JavaScript access but does
  not prevent malicious script already running in the origin from issuing
  authenticated requests.
- CSRF token rotation and session binding add frontend and backend lifecycle
  complexity.
- Account-key throttling can be abused to temporarily block a known account, so
  account and IP limits must be balanced and observable.
- Google sign-in depends on Google's browser service and public-key verification
  availability. Password authentication remains independent of Google.
- Deferred password recovery means a password user who loses access cannot
  recover it during Sprint 2.

## Alternatives considered

### Browser JWT bearer sessions

JWT bearer tokens could avoid a database lookup for some requests and are common
for distributed APIs. They were not selected because TrackSea is a modular
monolith, immediate revocation and inactive-user enforcement are valuable, and
browser token storage creates avoidable exposure. JWT expiry and revocation
would also reintroduce server-side state or leave an unacceptable validity
window. TrackSea may still use purpose-specific signed tokens in future flows,
but not as its browser session architecture.

### Managed identity platforms such as Auth0

Auth0 and similar managed providers can reduce implementation effort and offer
advanced identity features. They were not selected for the MVP because they add
an external operational dependency, recurring cost, provider coupling, and a
second authorization boundary before TrackSea needs those capabilities. The
MVP's password and single-provider requirements fit the existing monolith and
PostgreSQL deployment. This decision should be revisited if compliance,
enterprise federation, support burden, or provider breadth materially changes.

### Stateless signed cookie sessions

Keeping all session state in a signed or encrypted cookie would avoid a session
table. It was not selected because immediate revocation, server-owned session
state, and minimal browser exposure are more important than avoiding one indexed
database lookup.

### Redis-backed throttling

Redis could provide efficient counters and expiry. It was not selected because
PostgreSQL is already required, expected MVP authentication volume is modest,
and adding infrastructure would contradict the project's simplicity principle
without demonstrated need.

## Operational prerequisite and unresolved risk

Database and migration steps require Docker Desktop to be running with WSL
integration and Docker socket access. This environment was temporarily
unavailable during Sprint 2 planning and worked after Docker Desktop was started.
Its availability must be reverified before database-backed steps; verification
must not be skipped or weakened when it is unavailable.

## Review triggers

Revisit this decision when:

- production scale makes indexed PostgreSQL session or throttle lookups a
  measured bottleneck;
- compliance or enterprise requirements favor a managed identity platform;
- multiple first-party clients require a separate API-token architecture;
- additional identity providers, MFA, WebAuthn, or account recovery are approved;
- deployment topology requires cross-site cookies or materially different CORS
  behavior;
- Google changes or deprecates the selected Identity Services flow; or
- verified security evidence shows that a selected control or dependency is no
  longer appropriate.
