# Authentication Development

This guide covers local authentication configuration, user workflows, Google
Identity Services, tests, and troubleshooting. Start with the general
[Local Development](local-development.md) guide. For design boundaries, see the
[Authentication Overview](../architecture/authentication-overview.md) and
[ADR-003](../decisions/ADR-003-authentication-and-sessions.md).

## Start the local stack

From the repository root:

```bash
cp .env.example .env
docker compose --env-file .env up --build -d
docker compose --env-file .env ps
```

Open `http://localhost:5173`. The browser uses relative `/api/v1/...` requests,
and Vite proxies `/api` to FastAPI. Inside Compose, Vite receives
`DEV_API_PROXY_TARGET=http://backend:8000`; that Docker hostname is never sent
to or used by browser authentication code.

From the browser's perspective, frontend and API traffic are same-origin, so
the local stack does not require permissive credentialed CORS.
`FRONTEND_ORIGIN=http://localhost:5173` is the trusted local CSRF origin.

The current Compose backend service forwards its container `DATABASE_URL` and
`GOOGLE_CLIENT_ID`. Other authentication settings use the application's local
defaults in the container. The root `.env` values for those settings are read
when the backend is run directly from the host. Changing Compose forwarding is
outside this documentation step; do not assume a host `.env` override for an
unmapped setting reaches the current backend container.

## Environment variables

`.env.example` contains local development placeholders only. Keep real local
values in the ignored `.env` file and use deployment-managed secrets outside
local development.

### Database and sessions

| Variable | Local example/default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local `tracksea` PostgreSQL URL | SQLAlchemy and Alembic connection |
| `SESSION_LIFETIME_SECONDS` | `2592000` | Absolute session lifetime, 30 days |
| `SESSION_LAST_SEEN_INTERVAL_SECONDS` | `300` | Minimum interval between last-seen writes |
| `SESSION_COOKIE_NAME` | `tracksea_session` | Explicit local session cookie name |
| `SESSION_COOKIE_SECURE` | `false` | Allows the cookie over local plain HTTP only |

Outside local development, `SESSION_COOKIE_SECURE=true` is required. With
secure cookies and no explicit name, TrackSea selects
`__Host-tracksea_session`. If `SESSION_COOKIE_NAME` is explicitly set,
TrackSea preserves that configured name.

### Origin and CSRF

| Variable | Local example/default | Purpose |
| --- | --- | --- |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Exact trusted Origin/Referer |
| `CSRF_SECRET` | development placeholder | HMAC secret for signed CSRF tokens |
| `CSRF_COOKIE_NAME` | `tracksea_csrf` | Explicit local readable cookie name |
| `CSRF_HEADER_NAME` | `X-CSRF-Token` | Required unsafe-request header |
| `CSRF_TOKEN_TTL_SECONDS` | `3600` | Signed token lifetime |

The CSRF cookie is intentionally not HttpOnly. It has `SameSite=Lax`, `Path=/`,
no Domain, and is non-Secure only for local HTTP. In secure mode with no
explicit name, TrackSea selects `__Host-tracksea_csrf`; an explicit
`CSRF_COOKIE_NAME` remains unchanged.

Generate independent local replacements for `CSRF_SECRET` and
`AUTH_THROTTLE_SECRET` from `backend/`:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Run the command separately for each secret. Never reuse the development
placeholders outside local development, and never commit generated values.

### Password-login throttling

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUTH_THROTTLE_SECRET` | development placeholder | HMAC secret for account/IP keys |
| `AUTH_ACCOUNT_FAILURE_LIMIT` | `5` | Account-key failures before blocking |
| `AUTH_IP_FAILURE_LIMIT` | `20` | IP-key failures before blocking |
| `AUTH_THROTTLE_WINDOW_SECONDS` | `900` | Failure counting window |
| `AUTH_BLOCK_SECONDS` | `900` | Block duration |

The threshold-reaching failure returns the normal generic `401` and activates
the block. Subsequent blocked requests return generic `429 rate_limited`, with
`Retry-After` when available. A successful password login clears the account
bucket but preserves IP history. PostgreSQL stores HMAC-derived keys rather
than raw normalized emails or IP strings.

### Google

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_GOOGLE_CLIENT_ID` | empty | Browser GIS initialization |
| `GOOGLE_CLIENT_ID` | empty | Backend ID-token audience verification |

Google authentication is disabled when these values are empty. For normal
local Google testing, both variables must contain the same OAuth 2.0 Web
application client ID. A browser-visible client ID is public configuration,
not a secret, but real IDs should remain out of source files. No Google client
secret setting exists or is required for this flow.

## Create a local password account

1. Start the stack and open `http://localhost:5173/register`.
2. Enter a display name, email, and a password containing at least 15
   characters.
3. Submit and confirm the application redirects to the authenticated `/` page.
4. Open `/profile`, update the display name, and confirm the returned value.
5. Sign out and confirm the sign-in screen appears.

Use a unique local test password rather than a reusable personal password.
Password-created accounts remain unverified because verification delivery is
not part of Sprint 2.

The backend accepts passwords from 15 through 128 Unicode characters after NFC
normalization. Spaces are allowed and preserved. There are no upper/lowercase,
number, or symbol composition rules. A bundled local common-password blocklist
rejects known weak candidates.

## CSRF request flow

Cookie-authenticated browsers automatically attach the TrackSea session cookie,
so every unsafe authentication/profile request also requires CSRF and trusted
origin evidence:

```text
GET /api/v1/auth/csrf
  -> JSON csrf_token + readable tracksea_csrf cookie
  -> send same value in X-CSRF-Token
  -> backend verifies cookie/header, signature, expiry, session binding, origin
```

Protected unsafe endpoints are:

```text
POST  /api/v1/auth/register
POST  /api/v1/auth/login
POST  /api/v1/auth/logout
POST  /api/v1/auth/google
POST  /api/v1/auth/google/link
PATCH /api/v1/users/me
```

`GET /api/v1/auth/me` requires authentication but not CSRF. Registration,
password login, Google sign-in, and logout change the session/CSRF context, so
the frontend discards its in-memory CSRF token. Profile edits and explicit
Google linking do not rotate the session and can retain the current CSRF
context. CSRF is not authentication.

## Configure Google Cloud

1. Create or select a Google Cloud project.
2. Configure the OAuth consent screen as required by Google.
3. Create OAuth 2.0 credentials of type **Web application**.
4. Add `http://localhost:5173` as an authorized JavaScript origin.
5. Set the same Web client ID in the untracked local `.env`:

   ```dotenv
   GOOGLE_CLIENT_ID=<same-web-client-id>
   VITE_GOOGLE_CLIENT_ID=<same-web-client-id>
   ```

6. Restart both application services:

   ```bash
   docker compose --env-file .env up --build -d backend frontend
   ```

`VITE_GOOGLE_CLIENT_ID` initializes GIS in the browser.
`GOOGLE_CLIENT_ID` is the backend verification audience. The selected GIS ID
credential callback requests no Google API scopes and stores no access or
refresh tokens. No client secret is required. Do not invent or commit a
production origin or real client ID.

### Manual Google test

With a valid local Web client ID:

1. Open `/register` or `/sign-in` and confirm Google's official rendered button
   appears.
2. Complete Google sign-in and confirm TrackSea reaches the authenticated shell.
3. Refresh and confirm the TrackSea session remains authenticated.
4. Confirm no Google credential appears in localStorage or sessionStorage.
5. Sign out and confirm the TrackSea session is revoked.

For the collision flow, first create a password account. Sign in with a new
Google subject whose verified email matches that account. TrackSea returns
`account_link_required`; authenticate the password account, obtain a fresh
second Google credential through the rendered button, and explicitly link it.
Never retain or reuse the first Google credential.

## Account-linking rules

- An existing Google provider/subject signs in its linked TrackSea user.
- A new subject with an unused verified email creates a Google-only user.
- A new subject whose verified normalized email is already used returns
  `409 account_link_required`; no silent email linking occurs.
- `POST /api/v1/auth/google/link` requires an authenticated password user,
  valid CSRF, matching verified normalized email, and an unowned Google subject.
- Successful explicit linking adds an `ExternalIdentity` without creating a
  user or rotating/creating a TrackSea session.
- Google-only users cannot collect additional Google identities through this
  Sprint 2 endpoint.

Google unlinking and account merging are deferred.

## Public authentication errors

| Code | Meaning |
| --- | --- |
| `authentication_required` | Session is absent, expired, revoked, or otherwise invalid |
| `invalid_credentials` | Generic authentication failure without account disclosure |
| `account_conflict` | Registration or explicit-link conflict without identity details |
| `account_link_required` | Authenticate an existing account before explicit Google linking |
| `csrf_failed` | CSRF or trusted-origin evidence was rejected |
| `rate_limited` | Password login is currently blocked; respect `Retry-After` |

Password login deliberately returns `invalid_credentials` for an unknown
account, wrong password, inactive user, or Google-only/passwordless account.
The response cannot be used to infer whether the email or authentication method
exists.

## Database migrations

The current authentication migration head is `011d8d16c6cf`. With PostgreSQL
running, execute Alembic from `backend/`:

```bash
uv run alembic current
uv run alembic upgrade head
uv run alembic check
```

`uv run alembic downgrade base` is useful only for disposable migration
validation. It drops the Sprint 2 authentication tables and deletes their data;
do not run it casually against a populated development database.

## Automated tests

The normal backend suite creates a uniquely named temporary PostgreSQL database
matching `tracksea_test_<uuid>`, upgrades it to head, and drops it after the
test session:

```bash
cd backend
uv run pytest
```

The configured local PostgreSQL user must have database create/drop privileges.
The harness rejects non-PostgreSQL, non-local, and PostgreSQL system-database
targets.

Frontend tests use Vitest, React Testing Library, jsdom, and fake GIS at the
Google boundary:

```bash
cd frontend
npm test
npm run build
```

Backend Google tests use an injected fake verifier. Automated Google tests need
no real Google credentials, Google network calls, or client secret. Step 24
wires the completed authentication integration checks into CI.

The Step 22 full-stack smoke lives outside normal backend `testpaths`. With the
local stack running, execute it explicitly from `backend/`:

```bash
uv run pytest -q integration_tests/test_auth_frontend_proxy.py
```

It sends every HTTP request through `http://localhost:5173`, exercising the
Vite proxy, FastAPI, PostgreSQL, cookie persistence, registration, `/auth/me`,
and logout. It creates one uniquely named test account and removes it afterward.
It is not an automatic CI check until Step 24.

## Privacy and credential handling

TrackSea does not intentionally persist or expose plaintext passwords, raw
TrackSea session tokens, Google ID credentials, Google access/refresh tokens,
the CSRF secret, or the throttle HMAC secret. PostgreSQL stores Argon2id hashes
and SHA-256 session-token digests. Frontend authentication state contains only
the safe `UserResponse`.

Passwords and Google credentials necessarily exist transiently in browser
memory while an operation is submitted, but are not persisted as authentication
state. Authentication/session/Google credentials are not stored in
localStorage or sessionStorage, and browser code does not read the HttpOnly
session token.

## Troubleshooting

### `403 csrf_failed`

Use the frontend origin and relative `/api` proxy, confirm
`FRONTEND_ORIGIN=http://localhost:5173`, bootstrap CSRF again, and restart the
services after environment changes. Do not disable CSRF or origin checks.

### `401 authentication_required`

The session is absent, expired, revoked, or invalid. Sign in again.

### `401 invalid_credentials`

This response is intentionally generic. It does not establish whether an
account, email, or authentication method exists.

### `429 rate_limited`

Wait for `Retry-After` when present or for the configured block period. Do not
reset database state to bypass the control.

### Google button reports that Google is not configured

Set both Google client ID variables, verify the authorized JavaScript origin,
and restart frontend and backend. Confirm both values describe the same Web
client.

### Google backend verification fails

Confirm the backend and frontend client IDs match and that the credential was
issued for the configured Web client. Do not add a client secret.

### Client IP behind a proxy

The backend starts Uvicorn with `--no-proxy-headers` and intentionally ignores
`X-Forwarded-For`. Login throttling therefore sees the directly connected peer,
which is the proxy in a proxied deployment. Do not enable forwarded headers
blindly; trusted-proxy and production TLS/reverse-proxy configuration require a
separate reviewed design.

## Deferred capabilities

Sprint 2 does not provide password reset, email-verification delivery, password
or email changes, MFA/WebAuthn, other identity providers, account deletion,
Google unlinking, account merging, session-management UI, logout-all/global
logout, advanced security monitoring, or production trusted-proxy/TLS/reverse-
proxy deployment.
