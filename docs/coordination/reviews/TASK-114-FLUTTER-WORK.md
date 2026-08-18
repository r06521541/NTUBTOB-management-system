# TASK-114 Flutter Work review

status: accepted
reviewed_implementation: 4db42e05de0fe8202cd29c742defbdb9413179c8
reviewed_by: Flutter Domain Work

## Scope and contract

- The implementation changes only `clients/flutter_app/**` and the single
  `TASK-114-FLUTTER-CODEX.md` report.
- The wire adapter matches accepted artifact
  `9ed270d3c573885c096335140415b004ef867d22`: exact
  `attendance:report:read`, read-only attendance-report route, bounded query
  values, DTO fields and canonical error envelope behavior.
- Basic remains fail closed. Real report discovery requires both an
  Officer/Admin access level and the exact server capability; no Officer/Admin
  mutation, notification, push or fictional authority enters real mode.

## Review rounds

1. Changes requested: require access-level plus capability, retain all three
   report cohorts and unanswered-person metrics, settle canonical 404/422 and
   malformed errors, and replace page-local memory cache with durable isolated
   offline read-only storage.
2. Changes requested: purge cache on every ordered access-level downgrade and
   enforce a real serialized-size bound instead of report-count-only bounding.
3. Accepted: identity/grant/access downgrade and terminal-session/logout paths
   purge data; cache is installation/principal/game isolated, versioned,
   limited to 20 reports/200 people and 65,536 UTF-8 bytes, validates bounded
   fields, fails closed on corruption/version/oversize and preserves the prior
   blob when a replacement write cannot be committed.

## Verification and residual risk

- Implementer evidence: Dart format passed; `flutter analyze` passed; all 97
  Flutter tests passed; writer-scope, secret/endpoint/write-method scans and
  `git diff --check` passed.
- Domain review independently confirmed branch/origin SHA equality, clean
  status, exact writer scope, diff correctness and Dart formatting (9 files,
  zero changes). A focused Flutter test invocation stalled before producing
  output and was boundedly terminated; it is not counted as pass or failure.
- Android APK packaging remains unverified locally because the C drive lacks
  space. No APK/checksum is claimed. Hosted/fresh-disk Flutter CI must close
  analyze/test/debug-build evidence before merge. iOS runtime, device smoke,
  real LINE/API/staging and release signing remain deferred.
- External effects were limited to the task branch push and local Flutter/pub/
  Gradle caches. There was no backend/schema/Secret/service/deploy/message/PR or
  merge side effect.
