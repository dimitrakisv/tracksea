# Domain Model

## Purpose

This document defines TrackSea's core business concepts independently from database tables, API payloads, or UI components.

## User

A person with an account who can create observations, propose identifications, agree with identifications, and receive verified discoveries in their Marine Life list.

A public display name is separate from private account data such as email.

## Observation

An observation records that an organism was encountered at a particular place and time.

An observation may include:

- observer
- observation date and time
- exact coordinates
- public coordinates
- coordinate uncertainty
- description
- habitat
- depth
- quantity
- photos
- visibility and privacy settings
- whether identification help is requested

An observation does not contain an unquestionable final species.

## Identification

An identification is a user's proposal that an observation belongs to a particular taxon.

An identification includes:

- observation
- proposed taxon
- identifying user
- source, such as observer or community
- confidence
- optional explanation
- creation time
- withdrawal state

The observer's own taxon selection is stored as an identification.

## Agreement

An agreement records that a user supports an existing identification.

A user cannot agree with the same identification more than once and should not agree with their own identification.

## Verification

A verification is a reviewed decision by an authorized expert or trusted role.

Possible outcomes include:

- confirmed
- rejected
- insufficient evidence
- needs further review

Verification is separate from community agreement.

## Taxon

A taxon is a named group in the biological classification hierarchy.

TrackSea must support ranks above species, including genus and family, so users can express partial knowledge without guessing.

A taxon maintains:

- stable internal identifier
- scientific name
- rank
- parent taxon
- accepted taxon relationship
- external source and identifier
- taxonomic status

Common names are stored separately by language and region.

## Media

Media provides evidence for an observation.

Uploaded images must be validated, sanitized, processed, and associated with ownership and licensing information.

## Marine Life entry

A Marine Life entry represents a taxon that has been sufficiently confirmed from one of the user's observations.

It records the first qualifying observation and confirmation time. It is a personal journal feature derived from scientific-quality events rather than manual collection editing.

## Identification status

An observation may move between states such as:

- unidentified
- needs review
- community identified
- disputed
- expert verified
- cannot identify

Status should be derived from identification and verification history where practical.

## Invariants

- An observation always has an observer.
- An identification always has an identifying user and taxon.
- Unknown observations do not require a taxon.
- Historical identifications are withdrawn or superseded, not silently deleted.
- Private coordinates are never exposed through public responses.
- Marine Life entries are created only from qualifying confirmed observations.
