# TASK-136: Mobile API rollout boundary correction

- Task type: corrective work package
- Delivery group: `mobile-staging-acceptance-automation`
- Status: in progress
- Operator: agent under DEC-098
- Owner gate: none for repository correction; runtime remains separately gated

## Goal and scope

Correct two contracts exposed by the TASK-135 controlled staging dogfood:
Mobile API update deployment must preserve the service's existing IAM policy,
and traffic convergence must tolerate only the approved counterpart revision at
zero percent. Scope is the staging operator, direct tests, this task/report and
the existing mobile staging runbook.

## Invariants

- Bootstrap remains explicitly private; update omits all IAM-changing flags.
- Candidate readiness keeps the approved rollback revision at 100% and may
  retain only the approved candidate at 0%.
- Promotion/rollback requires the selected revision at 100%; only the opposite
  approved revision may remain at 0%.
- Unknown, duplicate, malformed or nonzero extra traffic entries fail closed.
- Tagged URLs, latest-revision aliases and unknown traffic fields fail closed.
- No image build, deployment, traffic, IAM, Secret, database or broker action is
  part of this repository correction.

## Verification budget

- Writer: affected direct tests plus compile/isort/diff.
- Domain: one targeted IAM/traffic-contract review.
- Hosted CI: one final gate.
