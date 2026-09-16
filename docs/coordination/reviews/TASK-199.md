# TASK-199 review record

Final verdict: PENDING immutable source acceptance and hosted PostgreSQL evidence.
Base: d83bd4b1e64bad119f780344fbde6d57c378f308.

## Architecture

`/root/native_upload_review`, task-199-account-review lease1: ACCEPT bounded
request/status contract before backend implementation. Explicit injection only,
constant-command dedup per Person, fresh transactional current-principal checks,
no actual deletion or bootstrap enablement. Main accepted and released writer.

## Pre-commit session findings

Same independent actor, lease2: REQUEST_CHANGES. Main accepted both findings and
assigned correction to a different writer; no final acceptance implied.

- R1/P1: generation cancellation could skip required queued local cleanup,
  leave prior account cache/intents and then delete the pending marker. The
  existing provider-logout race test asserted no purge rather than old-data absence.
  Require an uncancellable publication barrier/debt, old-data removal before new
  credentials, new-data preservation, and fail-closed cleanup failure/restart.
- R2/P2: exceptional network exits bypassed generation checks. Old requests could
  surface as current-account network/uncertain failure. Fence exceptions too,
  while retaining same-generation error classification.

Reviewer independently ran12 race tests PASS (showing the missing cases), not
the requested new RED cases. Source LF fingerprints at that rejected checkpoint:
integration.dart49dfcc340135c20edd64ea98bc653f78f7fe1aaa0e6b6d5d3199ac8e451f3430;
session_race_test.dart3ef1eb6b433ac9ee1031d39f948e524315b9dcefc55906c28a855bf2173ecde9.

## Current independent passes

- task-199-account-review lease3: backend/API/migration/revision consumers/tests,
  ACCEPT frozen source (25LF fingerprints); independently101PASS/33PGSKIP,
  quality24Python PASS and scoped diffcheck PASS. PostgreSQL limits retained.
- `/root/privacy_foundation`, task-199-client-review lease1: Main-authored optional
  Flutter request client/UI/demo/tests only, not their own privacy/compatibility
  work; lease1 found uncertainty lost after GET failure and missing immediate
  settled receipt invalidation. Main accepted both and reproduced3RED cases;
  corrected state/listeners now42focusedPASS, lease2 rereview in progress.
  Main owns privacy draft acceptance as a draft only.

No reviewer author accepts their own implementation. All source snapshots must
bind to the final immutable commit before final acceptance; no runtime/provider/
device/store/data-deletion claim follows from these reviews.
