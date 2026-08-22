# TASK-146 Main Work review

- Result: source accepted; hosted Flutter gate pending
- Base: `b91bef967277eee7bfb2987d5b138f08290605e7`
- Accepted HEAD: `ba52e21caa181ba456cdb72bc729c981e7b9c3af`
- Writer: `01a028ae-041c-7313-b917-417a0932e12d`
- Flutter Domain reviewer: `01a01212-72dc-7132-b2d7-dfaa2f97f184`

## Decision

Main Work reviewed the actual cumulative diff and accepted the bounded Flutter
composition. The home entry is capability-gated, notification requests and
mutations are single-flight, offline cache gaps are non-authoritative, and
terminal session errors propagate to the root lifecycle. Notification 403
removes only notification access; unauthenticated/session-expired terminates
the root session.

The single batched lifecycle review found stale in-memory/cache restoration,
missing root terminal propagation and an offline evidence-gap presentation.
Corrections added epoch invalidation, serialized final cache purge, root
lifecycle invalidation and direct terminal/forbidden regressions. Main rejected
two incomplete correction attempts by inspecting the correction diff; final
HEAD closes the original findings without expanding scope.

## Evidence

- Initial focused Flutter tests: 88 passed.
- Lifecycle correction tests: notification/basic 82 passed.
- Final notification authorization regressions: 14 passed.
- Affected Flutter analyze and Dart formatter checks: passed.
- `git diff --check`: passed.
- Domain review was read-only and delta-only; no suite replay.

Hosted CI is the sole full Flutter gate. No backend, PostgreSQL, emulator,
staging, provider, Secret/IAM, deployment, signing, store or real-data action
was used.
