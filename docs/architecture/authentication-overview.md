# Authentication Overview

This document explains how the accepted authentication design in
[ADR-003](../decisions/ADR-003-authentication-and-sessions.md) works in the
current TrackSea implementation. The ADR records why the design was selected;
this overview describes its practical boundaries and flows.

## Authority and components

TrackSea owns its users, authentication sessions, and authorization decisions.
Google may provide verified identity evidence, but it does not grant TrackSea
permissions. The FastAPI backend resolves the current user and remains the
authority for every protected operation. React authentication state is a user
interface concern, not an authorization boundary.

```text
Browser at localhost:5173
  -> relative /api/v1 request with cookies
  -> Vite /api proxy
  -> FastAPI auth and users modules
  -> PostgreSQL users, identities, sessions, and throttle buckets
```

The browser client sends requests with `credentials: "include"`. It does not
use bearer tokens, a browser JWT session, or authentication tokens in
`localStorage` or `sessionStorage`.

## Browser session model

Each successful registration or authentication event creates a new TrackSea
session from 32 cryptographically random bytes. The raw opaque token exists only
in transient server memory and the browser's HttpOnly session cookie.
PostgreSQL stores the token's 32-byte SHA-256 digest, the owning user, absolute
expiry, last-seen time, and revocation time.

```text
HttpOnly cookie containing raw opaque token
  -> SHA-256 digest lookup
  -> active, unexpired PostgreSQL Session
  -> active TrackSea User
  -> backend authorization decision
```

Incoming or pre-authentication session tokens are never adopted. Registration,
password login, and Google sign-in each mint a new session. Multiple sessions
for one user may coexist. Logout revokes only the current session and retains
its row with `revoked_at` set; it also clears the browser session cookie.
Profile edits and explicit Google linking do not rotate the current session.

The default absolute session lifetime is 2,592,000 seconds (30 days). The
default last-seen write interval is 300 seconds. Sprint 2 does not use sliding
session expiry.

## Cookie contract

The local session cookie defaults to `tracksea_session` and contains only the
opaque TrackSea session identifier. It has these properties:

- `HttpOnly`
- `SameSite=Lax`
- `Path=/`
- no `Domain` attribute
- `Secure=false` for local plain HTTP only

Outside local development, `Secure=true` is required. When no explicit cookie
name is configured, secure mode selects `__Host-tracksea_session`. A custom
`SESSION_COOKIE_NAME` remains supported; therefore, secure mode does not
override every explicitly configured name with a `__Host-` name.

The readable CSRF cookie follows the same path, SameSite, Domain, and Secure
policy. It defaults to `tracksea_csrf` locally and is intentionally not
HttpOnly because the signed double-submit design requires the frontend to send
the value in a header. With secure mode and no explicit name, it becomes
`__Host-tracksea_csrf`; an explicit `CSRF_COOKIE_NAME` is preserved.

## Authentication methods

### Email registration

```text
Browser
  -> GET /api/v1/auth/csrf
  -> POST /api/v1/auth/register
  -> normalize email and display name
  -> validate and Argon2id-hash password
  -> commit User + Session in one transaction
  -> set HttpOnly session and fresh session-bound CSRF cookies
  -> authenticated browser
```

Password-created accounts start unverified because email-verification delivery
is deferred.

### Password login

```text
Browser
  -> CSRF bootstrap
  -> POST /api/v1/auth/login
  -> normalize email
  -> check PostgreSQL throttle buckets
  -> real or dummy Argon2id verification
  -> create and commit a new TrackSea Session
  -> set session and fresh CSRF cookies
  -> authenticated browser
```

Unknown accounts and users without passwords still perform dummy Argon2id
verification. Unknown account, wrong password, inactive user, and
Google-only/passwordless account failures all return the same
`invalid_credentials` result.

### Password policy

The backend is authoritative for password policy:

- 15 to 128 Unicode characters after NFC normalization
- spaces are allowed and are not trimmed
- no uppercase, lowercase, number, or symbol composition requirements
- candidates in the bundled local common-password blocklist are rejected
- Argon2id uses the maintained password library's recommended parameters

Plaintext passwords are never persisted. Passwords exist transiently in the
browser and backend only long enough to submit and process an operation.

### Google sign-in

```text
Google Identity Services credential callback
  -> POST /api/v1/auth/google
  -> backend verifies signature, issuer, audience, expiry, and claims
  -> lookup by provider="google" + Google sub
  -> existing linked user or new Google-only user
  -> create TrackSea Session
  -> authenticated browser
```

Google is an identity provider only. TrackSea uses the Google `sub` claim as
the stable external identifier. The GIS credential is submitted immediately
and is not persisted. TrackSea stores no Google ID credential, access token, or
refresh token and requests no Google API scopes. The selected credential
callback flow uses a Web client ID and no client secret.

For a new Google subject with an unused verified email, TrackSea creates a
Google-only user with `password_hash` set to `NULL` and marks its email verified.
An existing `(provider="google", subject)` identity authenticates its linked
TrackSea user; the subject match is authoritative.

### Google email collision and explicit linking

TrackSea never links accounts silently from an email match.

```text
Unlinked Google subject
  + verified email matching an existing TrackSea user
  -> 409 account_link_required
  -> authenticate the existing password account
  -> obtain a fresh, second Google credential
  -> POST /api/v1/auth/google/link
```

Explicit linking requires an authenticated, active password user, valid CSRF
evidence, a verified Google email whose normalized value matches the TrackSea
account, and a Google subject not owned by another user. Success adds one
`ExternalIdentity`; it creates neither a new `User` nor a new `Session`.
Google-only users cannot use this Sprint 2 endpoint to collect additional
Google identities. Unlinking and account merging are deferred.

## CSRF architecture

Because browsers automatically attach cookies, unsafe cookie-authenticated
requests need protection from cross-site submission. TrackSea combines a
signed double-submit token with exact trusted `Origin` or validated `Referer`
checking. `SameSite=Lax` is defense in depth, not the only control.

`GET /api/v1/auth/csrf` returns a signed, expiring token and sets the same value
in the readable CSRF cookie. The frontend retains the token only in memory and
sends it in `X-CSRF-Token`. The backend compares cookie and header in constant
time, validates the signature and expiry, and binds authenticated tokens to the
current TrackSea session context. CSRF evidence is not authentication and does
not grant authorization.

These endpoints require CSRF and trusted-origin validation:

```text
POST  /api/v1/auth/register
POST  /api/v1/auth/login
POST  /api/v1/auth/logout
POST  /api/v1/auth/google
POST  /api/v1/auth/google/link
PATCH /api/v1/users/me
```

`GET /api/v1/auth/me` does not require CSRF, but it does require a valid
TrackSea session.

Successful registration, password login, Google sign-in, and logout change the
session or CSRF context, so the frontend invalidates its in-memory CSRF token.
Profile updates and explicit Google linking retain the current session and may
reuse its CSRF context.

## API boundary

| Method and path | Purpose | Success |
| --- | --- | --- |
| `GET /api/v1/auth/csrf` | Bootstrap CSRF evidence | `200` |
| `POST /api/v1/auth/register` | Create password user and session | `201` |
| `POST /api/v1/auth/login` | Authenticate by password | `200` |
| `POST /api/v1/auth/google` | Authenticate or create by Google identity | `200` or `201` |
| `POST /api/v1/auth/google/link` | Explicitly link Google | `200` |
| `POST /api/v1/auth/logout` | Revoke current session | `204` |
| `GET /api/v1/auth/me` | Read current safe user | `200` or `401` |
| `PATCH /api/v1/users/me` | Update current display name | `200` |

The safe `UserResponse` contains only:

```text
id
email
email_verified
display_name
authentication_methods
```

Public authentication error codes are `authentication_required`,
`invalid_credentials`, `account_conflict`, `account_link_required`,
`csrf_failed`, and `rate_limited`. A throttled request returns `429` and may
include `Retry-After`. Error boundaries intentionally avoid exposing account
existence, authentication method, credentials, or internal exceptions.

## Login throttling and client address

Password login failures update PostgreSQL-backed account and IP buckets. The
persisted keys are domain-separated HMAC-SHA-256 digests, not raw normalized
emails or IP addresses. Defaults are five account failures, 20 IP failures, a
900-second window, and a 900-second block.

The failure that reaches a threshold still returns the generic `401` and
activates the block. A subsequent blocked attempt returns generic `429`.
Successful password login removes the account bucket while preserving IP
history. This is durable multi-process throttling through PostgreSQL, not a
promise of global rate limiting beyond that database.

Uvicorn currently starts with `--no-proxy-headers`; the IP key therefore uses
the directly connected peer. `X-Forwarded-For` is not trusted. Behind a reverse
proxy, the peer will be the proxy until a reviewed trusted-proxy design is
configured. Production TLS and reverse-proxy configuration remain deferred.

## Privacy and deferred work

TrackSea does not intentionally persist or expose plaintext passwords, raw
session tokens, Google credentials, Google access or refresh tokens, the CSRF
secret, or the throttle HMAC secret. PostgreSQL stores Argon2id password hashes,
SHA-256 session digests, and Google provider/subject plus the safe identity
metadata needed by the implementation. Frontend authentication state contains
only `UserResponse`.

Sprint 2 defers password reset, email-verification delivery, password and email
changes, MFA/WebAuthn, other identity providers, account deletion, Google
unlinking, account merging, session-management UI, logout-all, advanced
security monitoring, and production TLS/trusted-proxy deployment.

See [Authentication Development](../development/authentication.md) for local
configuration, Google setup, testing, and troubleshooting.
