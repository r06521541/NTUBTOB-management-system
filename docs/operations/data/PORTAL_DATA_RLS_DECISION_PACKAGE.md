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

This recommendation is not executable SQL and is not an approved production policy.

## Owner decisions required before Phase A

1. Is the `ntubtob` schema exposed through REST, GraphQL, or another Supabase client API?
2. Which generic access class owns the existing and new tables: migration owner, runtime service,
   or another role? Do not record the actual role name in repository evidence.
3. Does the application runtime need direct access during Phase A? Recommended answer: no.
4. Must the reviewed artifact be amended to enable RLS on every new table before execution?
   Recommended answer: yes when API exposure cannot be conclusively excluded.
5. Should audit tables use stricter insert/select policies than operational tables when Phase C is
   designed? Recommended answer: yes; their append-only triggers do not replace authorization.
6. Who is authorized to verify grants and policies, and where will sensitive evidence be retained?
   Repository evidence should contain only yes/no results.

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
