# TrackSea Project Constitution

## Purpose

TrackSea is a personal marine journal that powers open marine science.

The project exists to help people document marine life they encounter, learn what they have seen, and contribute trustworthy, reusable biodiversity observations.

## Core principles

### 1. Dual value

Every meaningful feature should provide value to both:

- the individual user; and
- the scientific or conservation community.

Features that serve only one side should be reconsidered or redesigned.

### 2. Observation is not identification

An observation records that an organism was encountered at a place and time.

An identification records a user's proposal about what that organism is.

These are separate concepts and must remain separate in the data model, API, and user interface.

### 3. Uncertainty is valid

Users must be able to submit an observation without knowing the species. They may identify only a broader taxonomic group or request help from the community.

TrackSea must never force a user to guess.

### 4. Scientific history is auditable

Identifications, agreements, withdrawals, disputes, and verifications must be attributable and historically traceable.

Scientific history must not be silently overwritten.

### 5. Privacy by design

Exact coordinates may reveal personal movement, fishing locations, sensitive habitats, or vulnerable species.

Private coordinates and public coordinates must be handled separately, and authorization must be enforced by the backend.

### 6. Standards behind the scenes

Users should not need to understand Darwin Core or biodiversity data standards.

TrackSea should use a simple domain model and maintain a documented adapter that maps it to Darwin Core-compatible exports.

### 7. Community before gamification

The MVP should reward users through discovery, learning, and a personal Marine Life list.

XP, levels, leaderboards, and competitive mechanics are later enhancements and must never define scientific authority.

### 8. Simplicity before scale

The MVP is a modular monolith. New services, infrastructure, or abstractions require a demonstrated need.

The project should optimize first for clarity, correctness, testability, and low operating cost.

### 9. Open, responsible collaboration

TrackSea should be understandable and maintainable by human contributors and coding agents.

Important decisions must be documented, reviewed, and version controlled.

### 10. Evidence over confidence

Photos, descriptions, location, time, habitat, and explanations improve identification quality.

The system should preserve evidence and confidence levels rather than presenting unsupported certainty.

## The TrackSea test

Before accepting a significant feature, ask:

1. Does it improve the user's experience?
2. Does it improve the quality, coverage, transparency, or usefulness of the biodiversity dataset?
3. Does it protect user privacy and scientific integrity?
4. Can it be implemented without unnecessary complexity?

A strong TrackSea feature should satisfy all four questions.
