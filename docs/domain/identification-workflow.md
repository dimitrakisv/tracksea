# Identification Workflow

## Purpose

This document defines how TrackSea moves from an observation to a community or expert-supported taxonomic conclusion without hiding uncertainty or overwriting history.

## 1. Observation submission

The observer chooses one of four paths:

1. I know the taxon.
2. I think it may be this taxon.
3. I only know a broader group.
4. I do not know and want community help.

The observer may select a species, genus, family, or other supported rank. They are never forced to guess.

If the observer selects a taxon, TrackSea creates an `Identification` attributed to that observer. The observation itself does not store the selection as unquestionable truth.

## 2. Requesting identification help

An observation can be marked as needing identification or confirmation.

This places it in a community identification queue that can later be filtered by region, taxonomic group, photo availability, and review status.

## 3. Community identification

A community member may:

- suggest a taxon;
- choose a confidence level;
- explain the visible or contextual evidence;
- agree with an existing identification; or
- propose an alternative identification.

Confidence levels for the MVP:

- possible
- likely
- very confident

Confidence describes the contributor's certainty. It does not create verification authority.

## 4. Agreements

An agreement records support for an existing identification.

Rules:

- a user may agree only once with a particular identification;
- a user should not agree with their own identification;
- an agreement can be withdrawn;
- agreement history remains attributable;
- raw vote count must not be presented as expert verification.

## 5. Community status

The first MVP may use a simple configurable rule, for example:

- at least three independent users support the same taxon; and
- no conflicting identification has comparable support.

This rule produces `community identified`, not `expert verified`.

The implementation should keep consensus logic in a dedicated domain service so the rule can evolve without rewriting API or persistence layers.

## 6. Disagreement

When credible competing identifications exist, the observation becomes disputed.

TrackSea must display:

- each active proposed taxon;
- who proposed it;
- confidence and explanation;
- supporting agreements;
- withdrawn or superseded history where appropriate.

Disagreement is valid scientific information and must not be hidden.

## 7. Withdrawal and correction

Users correct an identification by withdrawing it and creating a new one, or through an auditable revision mechanism.

The system must never silently replace the old scientific history.

## 8. Expert verification

An authorized expert may review an identification and record one of these decisions:

- confirmed;
- rejected;
- insufficient evidence; or
- needs further review.

A verification includes the reviewing user, identification, decision, explanation, and timestamp.

Experts may verify only within permissions and scopes defined by future governance rules.

## 9. Observation identification states

Supported states may include:

- unidentified;
- needs review;
- community identified;
- disputed;
- expert verified; and
- cannot identify.

These states should be derived from active identifications, agreements, and verifications where practical.

## 10. Marine Life integration

A user's Marine Life list is updated only when one of their observations reaches a qualifying confirmation state.

The threshold must be configurable. The MVP may initially accept community-identified or expert-verified observations, with the exact rule documented in code and tests.

## Required auditability

For every identification-related event, TrackSea must preserve:

- acting user;
- observation;
- taxon;
- action type;
- confidence or decision;
- explanation where supplied;
- timestamp; and
- withdrawal or supersession state.
