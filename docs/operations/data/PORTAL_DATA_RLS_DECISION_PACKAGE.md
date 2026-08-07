# Portal Data RLS decision package

## Purpose

TASK-049 confirmed that all ten existing `ntubtob` legacy tables have RLS enabled, but it did not
identify policies, runtime database roles, table owners, grants, or whether `ntubtob` is exposed by
Supabase APIs. The new portal-data tables must not be promoted to production until these facts and
the intended access path are approved.

## Recommended fail-closed direction

- Treat all new Person, identity, qualification, attendance and audit tables as service-private.
- Do not expose them through Supabase client APIs during Phase A.
- Enable RLS before any possible API exposure and create no public/anonymous policies.
- Do not assume that RLS alone protects traffic: PostgreSQL table owners and roles with bypass
  privileges can bypass RLS. Review the actual runtime role and table owner relationship first.
- Keep Phase A schema-only. No Web Portal, webhook, scheduled service or backfill should read or
  write the new tables until a separate Phase B/C approval.

DEC-065 records the Owner's Phase A choice: enable RLS on exactly the 13 new portal-data tables
without `FORCE ROW LEVEL SECURITY`. Phase A creates zero policies and adds no grants or revokes.
Application access remains none. The deterministic reviewed artifact is the only executable
expression of that choice; this document does not authorize running it.

## Owner decisions recorded for Phase A

1. `ntubtob` was not listed as an exposed schema during the reviewed baseline.
2. The future one-time executor is described only as the migration owner; its actual role name must
   not be recorded in repository evidence.
3. Application runtime access during Phase A is none.
4. Every new table has RLS enabled before Phase A commits; no table has forced RLS.
5. Phase A creates zero policies and changes no grants. Audit-specific and runtime policies are a
   separate Phase C decision.
6. Repository evidence remains sanitized yes/no results only.

## Table data classes

| Class | Tables | Sensitivity | Phase A access recommendation |
| --- | --- | --- | --- |
| Identity/access | `people`, `auth_identities`, `person_qualifications` | High | Migration verification only |
| Audit | `access_audit`, `event_audit` | High | No application access |
| Event operations | `events`, `activities`, eligibility/invitee/manager tables | Medium to high | No application access |
| Attendance | event/activity attendance tables | High | No application access |

## Stop conditions

- Supabase API exposure, runtime role, table owner or bypass privilege is unknown.
- The approved RLS state differs from the reviewed SQL artifact.
- Any public, anonymous or unexpectedly broad policy/grant is discovered.
- Phase A requires application access or a backfill to succeed.

Any required RLS DDL must be reviewed as a new artifact and receive separate Owner approval; do not
append ad-hoc statements during execution.
