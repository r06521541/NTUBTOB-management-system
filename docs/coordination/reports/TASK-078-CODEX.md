# TASK-078 Codex report

## Status

- Branch: `codex/phase-c-feature-off-deployment`
- Planning HEAD: `228861c99f929c9ff8c3defa39c80ef185aaad3e`
- Approved application source: `1838ec6fc77a74e23700f9cd29b8ea910c0a29fb`
- Result: awaiting Owner approval; no deployment authorization is implied.

## Completed local work package

- Rebuilt `shared_lib-0.0.1.tar.gz` and copied the identical artifact into the
  Web Portal, LINE webhook and notify cron local deployment contexts.
- Locked shared source fingerprint:
  `bd3d932b5c5dc55695d73a203ffe9efbe24405fffd356993bcf7fc53a33a2298`.
- Locked all four local artifact byte hashes:
  `b1018a678c1ff0b44c9b0eadc89651d1d6947467c9f697534866a002b6eb8ab1`.
- Verified that `1838ec6..228861c` contains no `shared_lib` source change.
- Added the non-executable Owner work package at
  `docs/operations/deployments/PHASE_C_FEATURE_OFF_1838EC6.md`. It contains
  artifact evidence, fail-closed missing-inventory status, read-only inventory
  commands, the exact feature-off vector, prepared deployment commands and
  rollback boundaries.
- Work-requested correction: the LINE webhook is now explicitly modelled as a
  Gen2 immutable-GCS-source rollback, following
  `docs/operations/GEN2_FUNCTION_ROLLBACK.md`. The package inventories
  `buildConfig.source.storageSource`, records bucket/object/generation as
  Owner approval fields, and provides the narrow official Functions v2 PATCH
  request shape with `updateMask=buildConfig.source` plus pre/post-checks.

## Production inventory result

- The current Windows shell does not have `gcloud` or `gcloud.cmd` available.
  `where gcloud` and standard Google Cloud SDK locations produced no executable.
- No GCP command was run. Therefore current/rollback revisions, traffic,
  image digests, ingress/auth, runtime identity, non-secret flag values and
  Scheduler metadata are all explicitly **unverified**.
- Historical deployment records were not used as current state or rollback
  targets. The work package blocks execution until an authorized operator runs
  the listed read-only commands and Owner locks their results.
- In particular, the LINE webhook source bucket, object and generation remain
  unverified; the prepared PATCH request deliberately contains placeholders
  rather than a guessed production source identity.

## Verification

- `python -m unittest tools.tests.test_deploy_phase_c_rollout
  tools.tests.test_deploy_phase_c_runtime
  tools.tests.test_deploy_phase_c_transition_controller
  tools.tests.test_deploy_web_portal
  tools.tests.test_deploy_scheduled_service -v`: 67 passed.
- Offline all-off preflight: passed, `mode=legacy_unfrozen`.
- Offline transition controller: passed, all-off/unfrozen to itself,
  `status=valid`, `step_count=0`, using the planning checkout commit lock.
- `git diff --check`: passed.
- After the Gen2 rollback documentation correction, the same 67 deployment
  tooling tests and `git diff --check` were re-run and passed.
- Black CLI was not run under bundled Windows Python. Black formatter API
  version `24.4.2` was used for a non-mutating comparison: the existing
  `tools/phase_c_rollout_preflight.py` and
  `tools/phase_c_transition_controller.py` were unchanged; the existing
  `tools/deploy_web_portal.py` and `tools/deploy_scheduled_service.py` would be
  reformatted. They were deliberately left untouched because TASK-078 changes
  no Python source and must not add unrelated formatting diff.

## Owner decision required

Do not execute the prepared commands until the Owner has approved all of the
following from fresh, non-secret, read-only production inventory:

- active account, project and region;
- each target's current Ready/traffic revision and exact rollback target;
- image digest, runtime identity and ingress/auth boundary;
- exact feature-off flag vector (`false` for every named flag);
- relevant Scheduler metadata without invoking or modifying any job; and
- existing resource:version Secret references for the Web Portal wrapper,
  without revealing Secret values.

No Cloud Build, image build/push, deploy, revision/traffic/environment mutation,
endpoint invocation, Scheduler, Secret, IAM, database operation or notification
was performed.
