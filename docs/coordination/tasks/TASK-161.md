# TASK-161 Web Portal production-safe deployment contract

## Classification

- task_type: delivery
- risk: L3 deployment tooling / production boundary
- delivery_group: `web-portal-reliability-202608`
- authority_branch: `codex/task-161-web-portal-disabled-identity-deploy`
- repository_authority: `70d9df4f4479561a9a8da59efd10a56dce1e4105`
- production_execution: separate Owner exact gate

## Active writer claim

- role: `codex-writer`
- claim_id: `task-161-web-portal-disabled-identity-deploy-writer-20260827`
- lease_version: 1
- actor_id: `codex-writer:task161-web-portal-deploy-contract`
- state: `completed`
- scope: add an explicit fail-closed identity-link disabled deployment mode
- owned paths:
  - `tools/deploy_web_portal.py`
  - `tools/tests/test_deploy_web_portal.py`
  - `apps/web_portal/cloudbuild.yaml`
  - `apps/web_portal/tests/test_deployment_contract.py`
  - `makes/deploy_apps.mk`
  - `apps/web_portal/README.md`
  - `docs/operations/DEPLOYMENT_RUNBOOK.md`
  - `docs/coordination/tasks/TASK-161.md`
- write: exact task branch and owned paths only; commit/push handoff authorized; Main owns acceptance, PR, merge and production gate
- report_to: `main-work`
- stop_conditions: unexpected dirty overlap, provider/Secret/IAM mutation, weakened enabled-mode validation, inability to prove disabled keys absent, production execution before exact Owner gate

## Required behavior

1. Deployment accepts an explicit `enabled|disabled` identity-link mode; the existing enabled mode remains strict and requires the complete approved provider configuration.
2. Disabled mode rejects every identity-link client, callback and Secret input, omits all six identity-link runtime keys, and verifies those keys are absent from the Ready revision.
3. Disabled mode verifies `/identity-recovery` remains unavailable; enabled mode preserves its existing success check.
4. Existing Phase C, rollout-freeze, identity-maintenance, public ingress, runtime identity, image digest, Secret reference and rollback checks remain fail closed.
5. Repository correction, CI and merge do not authorize provider, Secret, IAM, runtime or production mutation. Production execution requires an exact target/artifact/config/rollback packet and Owner approval under DEC-078.

## Verification budget

- Writer runs deployment-tool complete tests and Web Portal deployment-contract tests, plus `git diff --check` and scope review.
- One independent Auth/Security reviewer checks enabled-mode non-regression, disabled-mode absence enforcement, no-disclosure and rollback/post-check behavior.
- Main performs diff and focused risk review; final PR uses one hosted change-selected gate.

## Acceptance status

- writer evidence: deployment wrapper 37/37 passed; deployment contract 8/8 passed; py_compile, Black formatter API and `git diff --check` passed
- independent Auth/Security review: ACCEPT after closing two P1 path-consistency/Secret-filter findings and one runbook contradiction
- Main targeted evidence: three wrapper security regressions passed; deployment contract 8/8 passed; one earlier package-qualified Web test command failed only at the existing `config` import harness and was replaced by the supported discover invocation
- explicit mode: enabled preserves the six-input identity contract; disabled rejects all six inputs
- disabled runtime proof: filtered env, Cloud Build removal, Ready revision absence, and HTTP 404 post-check
- canonical entry: Make delegates to the complete Python wrapper and has no direct Cloud Build or temporary-env path
- external mutation: none; no provider, Secret, IAM, runtime or production operation was performed
