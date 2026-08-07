# Portal Data Phase A production closeout

## Outcome

Production Phase A atomic schema expand completed successfully on 2026-08-07 (Asia/Taipei). The strict combined
pre/post evidence validator passed after the CRLF-safe read-only post-check was merged. This closeout authorizes neither
Phase B backfill nor Phase C application rollout.

## Approved source and evidence

- Migration source commit: `871abd2bae8fefbe13f8ebc6cbd2f28baca1e56c`
- Migration SQL SHA-256: `81fa1ba1a2d2d856d4b4393cbdfbc663d6c19759f758f36b08e76e39a964636a`
- Pre-check SHA-256: `51ce7d88463f96bcf1a9cd12d0c3e1eeb5c17f5f0bdf19d466e7a0e296e6cd33`
- Final CRLF-safe post-check merge: `9e12e672c0e6f4eaf252563597c9e69d6b3fcec2`
- Final post-check SHA-256: `8ee0b812813c4c3a6ab0bdacca084dd3aa0a54d715b2dbfad4a9f7ca0526a8a7`
- Retained logical archive passed the approved Docker-backed read-only verification immediately before the window.
- Raw pre/post CSVs remain outside the repository and were not copied or committed.

## Verified final state

- Alembic revision is exactly `0003_legacy_bigint_activity_game`.
- The expected 13 portal-data tables, 97 columns, 75 constraints, three indexes, append-only function and two triggers
  match the reviewed fingerprints.
- `members.person_id` is nullable bigint with the expected unique/FK protection and no non-null values.
- New portal-data application tables contain zero rows.
- All 13 new tables have RLS enabled, not forced, with zero policies.
- Portal PUBLIC and non-owner direct grants and non-owner default table ACL counts are zero.
- Legacy table/column/PK-FK fingerprints, ownership/grant boundary and aggregate counts match the execution-time
  pre-check.
- Existing services remain on legacy paths; no deployment, notification, Secret/IAM/Scheduler or runtime opt-in occurred.

## Post-check incident

The first post-check failed only the raw `pg_proc.prosrc` MD5 because SQL Editor preserved Windows CRLF line endings.
Work reproduced the same false negative locally. TASK-064 changed only the read-only fingerprint expression to normalize
CRLF to LF; LF and CRLF exact bodies pass while substantive body mutation remains fail closed. The migration and
production function were not rerun or modified. The final combined validator then passed.

## Recovery and next gate

The expand-only schema is retained. Do not downgrade or drop it. The verified logical archive remains the disaster
recovery boundary, but no restore is indicated. Phase B requires a separate idempotent Member/Person/identity backfill
design, fresh evidence and explicit Owner approval. Phase C runtime roles, grants, RLS policies and service integration
remain prohibited until separately reviewed.
