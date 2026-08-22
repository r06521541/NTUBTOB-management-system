# Mobile API

Independent Flask/Cloud Run deployment unit for the native API. Basic access
remains isolated; Officer/Admin receive only explicitly projected bounded reads.
The canonical machine-readable contract is `openapi.json`.

The runtime fails closed unless PostgreSQL reports the exact revision
`0008_mobile_notification_delivery`, and all
signing, refresh-response encryption, audience configuration is present. The
readiness check remains read-only and does not inspect the broker journal or
notification tables. These values are runtime configuration only; this directory
contains no credential and no deploy target.

Officer publishing uses the exact `notifications:publish` capability. Preview
recipient expansion and confirmation remain server-owned; confirmation writes
the immutable notification, recipients, append-only audit, in-app success and
retryable push outbox result in one transaction. Device registration accepts
only explicit `fake` provider tokens in this delivery. The only delivery adapter
is deterministic and rejecting; no LINE, Discord, APNs or FCM provider is
configured or invoked.

Package the current `shared_lib-0.0.1.tar.gz` under `dist/` before an authorized
build. This task does not build, deploy, bind Secret Manager, change IAM or
connect to production.

The staging operator package is documented in
`docs/operations/mobile/MOBILE_STAGING.md`. It defaults to dry-run, rejects the
production project and database identity, and does not authorize deployment.
