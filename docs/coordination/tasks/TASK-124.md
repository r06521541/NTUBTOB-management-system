# TASK-124: Mobile staging acceptance evidence contract

- Task type: planning plus serial observability producers
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: producer packages 1-4 accepted; ready for hosted CI
- Owner gate: none for repository planning

## Goal

Define the smallest privacy-safe evidence contract required before the staging
acceptance harness automates Basic, Officer, attendance mutation, offline cache,
and logout/cache-purge claims. The contract must distinguish authoritative
server state from local presentation and prevent runtime work from inventing
diagnostics after a scenario has already started.

## Scope and ownership

Main Work is the only writer for the planning package. Producer package 1 has
one Flutter writer and owns `clients/flutter_app/lib/basic_app.dart`, its direct
widget tests, and the single TASK-124 Flutter report. Reviewers are read-only
and review only authorization, privacy, provenance, and unchanged release and
navigation guards. Backend, launcher, database, runtime, cloud, Secret, and
fixture mutation remain out of scope for this package.

## Invariants

- Every acceptance claim names one authoritative producer, an exact bounded
  state vocabulary, freshness requirements, and fail-closed ambiguity rules.
- UI selection or absence alone cannot prove server mutation, durable cache
  deletion, session identity, or authorization.
- Evidence contains no token, provider subject, person ID, display name,
  endpoint, response body, raw UI hierarchy, logcat, storage key, or Secret.
- Debug-only client evidence is hard-disabled in release builds. Aggregate
  operator evidence remains candidate/identity gated and read-only.
- A scenario cannot run past a claim whose required producer is marked
  `gap`; it returns a stable blocked classification instead.
- Evidence reuse is bound to exact source SHA, command/suite, runtime or DB
  matrix, and relevant artifact fingerprint.

## Acceptance

1. The contract covers principal/capability, Officer report, attendance reply,
   offline cache, and logout/cache purge.
2. Each claim records existing evidence, missing evidence, and the minimal
   follow-up implementation boundary.
3. Owner-only and DEC-098 agent-operated boundaries are explicit.
4. TASK-123 launch actions and future A/B/C work can cite the contract without
   copying it into task reports or handoffs.

## Verification budget

- Main writer: one source/test inventory and one documentation consistency
  check.
- Domain review: one targeted privacy and claim-sufficiency review.
- Main risk review: one delta-only correction review if needed.
- Hosted CI: documentation gate only when bundled into a substantive delivery.

## Five-line execution checkpoint

1. Goal: define authoritative, privacy-safe evidence before more runtime automation.
2. Files: this task and one mobile operations evidence contract.
3. Invariants: bounded states, authoritative provenance, no sensitive output, gaps block scenarios.
4. Tests: link each claim to existing direct tests or explicitly mark the missing producer.
5. Blockers: none for planning; implementation gaps become separate one-writer packages.
