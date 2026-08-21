# TASK-135: Staging broker rollout artifact packaging

- Task type: work package
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: ready for targeted review
- Operator: agent under DEC-098 for repository work
- Owner gate: cloud provisioning only after repository acceptance

## Goal

Prepare an immutable task-owned broker build context containing the validated
real staging candidate approval without modifying the tracked fictional
fixture or exposing approval contents. This closes the artifact boundary before
any Cloud Run, IAM, Secret, migration or broker operation.

## Scope

- one deterministic Python rollout packager and direct tests;
- the broker deployment contract and mobile staging runbook;
- this task and one report.

Cloud resources, Secret payloads, provider subject, database access, deployment
and broker execution remain outside this repository slice.

## Invariants

- Require an exact clean full source commit and copy only a fixed git-tracked
  build allowlist through `git archive`. The executable packager must come from
  that same source root, so the runtime hash algorithm cannot drift from the
  archived commit.
- Read the existing private approval once with a fixed byte cap, preserve its
  approved bytes except for the established CRLF-to-LF normalization, validate
  those final bytes with the shared contract, and require exact candidate/
  staging project/region/mobile API service values.
- Bind the approval to the independently accepted staging database identity
  fingerprint; the approval cannot define its own expected fingerprint.
- Substitute the canonical approval only inside a new task-owned E-drive build
  context. Never modify or commit it to the repository.
- Reject reparse/symlink inputs, dirty or wrong source, existing/partial output,
  archive links and malformed paths. Validate original path components before
  resolution and bind approval checks to the opened file identity. Clean
  partial output in `finally`; cleanup failure is a fixed terminal state.
- Persist and emit only source/artifact hashes, opaque database identity hash,
  project/region and bounded lifecycle metadata; no
  approval fields, Secret references, endpoint, provider subject or path.

## Acceptance and verification budget

- Writer: one direct suite plus pycompile/isort/diff.
- Domain: one targeted artifact/no-disclosure review.
- Main: one integration-shape review.
- Hosted CI: one final gate after integration.
- No build, gcloud, Secret, database, IAM or runtime operation in this slice.
