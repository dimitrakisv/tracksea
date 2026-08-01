# MVP Scope

## Goal

Deliver a web-first product where a person can record a marine observation, request or provide an identification, and build a personal Marine Life list from confirmed observations.

## In scope

### Accounts
- Register, sign in, sign out, and recover access.
- Public display name separate from private email.
- Attribute every observation, identification, agreement, and verification to a user.

### Observations
- Create an observation with date, time, location, description, and optional photos.
- Store exact and public coordinates separately.
- Allow unknown taxa and higher-rank identifications.
- View observations in list and map views.

### Taxonomy and identification
- Search common and scientific names.
- Support English and Greek common names initially.
- Store observer taxon choices as identifications.
- Allow community suggestions, agreements, alternative identifications, confidence, explanations, withdrawals, and history.
- Keep expert verification distinct from community agreement.

### Personal Marine Life
- Show observation count, confirmed unique taxa, and visited locations.
- Add a taxon after the user's first sufficiently confirmed observation.
- Celebrate first confirmed discoveries without XP or competitive mechanics.

### Interoperability
- Maintain documented Darwin Core mappings.
- Provide CSV and GeoJSON exports after core workflows are stable.

### Operations
- Local development through Docker Compose.
- Initial low-cost deployment using Docker on AWS Lightsail and S3-compatible storage.
- Automated tests and CI before production deployment.

## Out of scope

- Native mobile applications
- Offline synchronization
- AI species identification
- Forums and direct messages
- XP, levels, badges, streaks, leaderboards, and challenges
- Complex reputation weighting
- Organization dashboards
- Microservices
- Large-scale research analytics

## MVP success criteria

- A new user can publish an unknown or identified observation without assistance.
- No user is forced to guess a species.
- Public APIs never expose unauthorized exact coordinates.
- Identification history remains attributable and auditable.
- A confirmed first observation appears in the observer's Marine Life list.
- The application can be run locally from documented instructions.
