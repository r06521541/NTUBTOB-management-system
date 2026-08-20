# TASK-130: Mobile API broker-journal revision compatibility

- Task type: repository compatibility bridge
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: assigned for implementation
- Operator: agent under DEC-098
- Owner gate: none for repository work; staging rollout remains separately gated

## Goal

Allow the existing Mobile API to remain ready across the additive TASK-128
broker-journal migration from `0005_mobile_auth_api_foundation` to
`0006_staging_broker_operation_journal`, without accepting arbitrary revisions
or coupling the API to broker behavior.

## Scope and ownership

One writer owns only:

- `apps/mobile_api/revision_readiness.py`;
- its direct tests;
- the Mobile API README and one TASK-130 report.

The TASK-128 migration/service, staging operators, launcher, Flutter, cloud
deployment and global coordination are read-only dependencies.

## Invariants

- The accepted set is exactly revision 0005 and the additive broker-journal
  revision 0006; empty, malformed, unknown, older or future revisions fail
  closed without logging the observed value.
- Readiness remains read-only and does not inspect, initialize or depend on the
  broker journal table. Existing safe database-error categorization is unchanged.
- Repository acceptance does not claim the staging database or API is migrated.
  External rollout order is API compatibility image first, then journal
  migration/broker deployment, with independent health and rollback evidence.
- No production, database, Secret, IAM, Cloud Run or migration operation occurs.

## Acceptance and verification budget

1. Direct tests prove exact 0005 and 0006 readiness and unknown revision
   fail-closed/no-value logging.
2. Existing revision error/no-disclosure tests remain green.
3. Writer runs the affected Mobile API revision suite, compile/format/diff
   checks once; Main performs targeted diff review; hosted CI is the final gate.

## Five-line execution checkpoint

1. Goal: preserve Mobile API readiness across the additive broker journal revision.
2. Files: revision readiness, direct tests, Mobile API README and one report.
3. Invariants: exact two-revision allowlist, read-only, unknown fail closed.
4. Tests: direct readiness/no-disclosure suite plus compile/format/diff.
5. Blocker: any non-additive schema or API behavior dependency returns to Main.
