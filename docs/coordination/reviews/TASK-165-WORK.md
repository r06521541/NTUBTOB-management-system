# TASK-165 Main Work review

## Verdict

`accepted_pending_hosted_ci`

## Accepted boundary

- Production Event management uses the canonical request principal and `MANAGE_EVENTS`; raw persisted Person roles are not production authority.
- The PostgreSQL adapter independently requires an active Person linked to an exact allowlisted legacy Member. Persisted Officer／Admin fallback is available only when local fictional preview explicitly enables it.
- Global navigation, the management hub and all ten `/manage/events` routes use the same capability direction. Session Person／identity consistency remains fail closed.

## Review evidence

- Auth／Identity review first rejected the global-navigation persisted-role leak and the mocked-service gap, then accepted the corrected Web and repository composition.
- Data／Auth review accepted every managed Event operation retaining the repository guard and corrected the local evidence count to 20 passed／23 PostgreSQL skipped.
- Writer Web evidence: focused 6／6 plus one adjacent unauthenticated case, admin-security 128／128, complete Web Portal 227／227, compile, formatter API and `git diff --check` passed.
- Main reran the supported root discovery for admin-security: 128／128 passed. An earlier package-qualified invocation failed during import setup before running tests and was not treated as product evidence.
- Four new PostgreSQL authorization cases require hosted evidence before merge.

No database, runtime, cloud, Secret, IAM, provider, notification or production mutation occurred during review.
