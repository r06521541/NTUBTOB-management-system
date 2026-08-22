# Mobile API

Independent Flask/Cloud Run deployment unit for the native API. Basic access
remains isolated; Officer/Admin receive only explicitly projected bounded reads.
The canonical machine-readable contract is `openapi.json`.

The runtime is fail closed unless PostgreSQL reports one of the exact accepted
revisions `0005_mobile_auth_api_foundation` or
`0006_staging_broker_operation_journal` or `0007_mobile_notifications`, and all
signing, refresh-response encryption, audience configuration is present. The
readiness check remains read-only and does not inspect the broker journal or
notification tables. These values are runtime configuration only; this directory
contains no credential and no deploy target.

Package the current `shared_lib-0.0.1.tar.gz` under `dist/` before an authorized
build. This task does not build, deploy, bind Secret Manager, change IAM or
connect to production.

The staging operator package is documented in
`docs/operations/mobile/MOBILE_STAGING.md`. It defaults to dry-run, rejects the
production project and database identity, and does not authorize deployment.
