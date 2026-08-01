# TrackSea Engineering Philosophy

## Purpose

This document explains how TrackSea should be designed, implemented, reviewed, and evolved by human contributors and AI coding agents.

## Principles

### 1. Domain first, framework second

Business concepts such as Observation, Identification, Verification, Taxon, and Marine Life should remain understandable without reference to FastAPI, React, SQLAlchemy, or PostgreSQL.

Frameworks implement the domain. They do not define it.

### 2. Prefer the simplest complete solution

Choose the least complex design that fully satisfies the requirement and preserves future evolution.

Do not introduce microservices, event buses, generic plugin systems, or distributed infrastructure without a demonstrated need.

### 3. Make boundaries explicit

Keep responsibilities separated:

- route handlers coordinate HTTP concerns;
- domain services implement business rules;
- repositories handle persistence;
- frontend components handle presentation and interaction;
- adapters handle external standards and providers.

### 4. Treat privacy and auditability as domain requirements

Private coordinates, identification history, verification authority, and user attribution are not implementation details.

They must be reflected in models, authorization rules, tests, and review checklists.

### 5. Tests describe behavior

Tests should focus on externally meaningful behavior and domain invariants rather than internal implementation structure.

High-value tests include:

- authorization boundaries;
- coordinate privacy;
- identification history;
- consensus state changes;
- Marine Life qualification; and
- Darwin Core export safety.

### 6. Documentation changes with behavior

A behavior change is incomplete when the relevant documentation, API contract, or ADR remains outdated.

Code and knowledge must evolve together.

### 7. Small changes are easier to trust

Prefer focused issues, branches, commits, and pull requests.

A change should be understandable, testable, and reversible without requiring unrelated modifications.

### 8. Humans own architectural decisions

AI agents may propose options and implement approved specifications, but they must not silently redefine product scope, domain rules, architecture, security posture, or data governance.

Significant decisions require review and, where appropriate, an Architecture Decision Record.

### 9. AI output is reviewed like human output

AI-generated code must meet the same standards for correctness, security, clarity, testing, documentation, and maintainability.

Generated code is not accepted merely because it compiles or passes a narrow test.

### 10. Optimize after evidence

Measure before optimizing. Prefer clear PostgreSQL queries, straightforward APIs, and simple deployment until real usage identifies a bottleneck.

### 11. Portability matters

Use Docker, open standards, and provider-neutral application boundaries where practical.

AWS may host the initial system, but core application behavior should not depend unnecessarily on one cloud provider.

### 12. Failure should be visible

Errors must be logged with useful context, surfaced through consistent API responses, and monitored without leaking secrets or private data.

Silent failure is unacceptable for uploads, exports, migrations, identification changes, and privacy-sensitive operations.

## Definition of a good change

A good change:

- solves one clear problem;
- follows the Constitution and MVP scope;
- preserves domain boundaries;
- includes appropriate tests;
- protects privacy and auditability;
- updates documentation;
- avoids unrelated refactoring; and
- leaves the repository easier to understand.
