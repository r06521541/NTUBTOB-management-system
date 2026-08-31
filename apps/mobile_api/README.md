# Mobile API

Independent Flask/Cloud Run deployment unit for the native API. Basic access
remains isolated; Officer/Admin receive only explicitly projected bounded reads.
The canonical machine-readable contract is `openapi.json`.

The runtime fails closed unless PostgreSQL reports the exact revision
`0008_mobile_notification_delivery`, and all
signing, refresh-response encryption, and existing provider audience
configuration is present. The
LINE audience and bounded `MOBILE_API_GOOGLE_AUDIENCES` allowlist are separate
plain runtime values. `MOBILE_API_APPLE_AUDIENCE` is optional for this repository
slice: a missing or blank value disables only Apple authentication, while LINE
and Google remain available. A configured value must be one exact audience;
Apple ID tokens are nonce-bound and verified with a bounded, thread-safe cache
of Apple's public RSA signing keys. Database, signing, and replay keys remain
Secret-backed.
The readiness check remains read-only and does not inspect the broker journal or
notification tables. These values are runtime configuration only; this directory
contains no credential and no deploy target.

This slice receives an Apple ID token and raw nonce only. It does not receive an
authorization code, obtain an Apple refresh token, or handle provider
revocation. Those capabilities remain future public-provider/runtime gates, so
this repository slice does not claim a complete Apple provider-session
lifecycle. Its access and refresh tokens are existing server-owned application
sessions, not Apple provider sessions.

Officer publishing uses the exact `notifications:publish` capability. Preview
recipient expansion and confirmation remain server-owned; confirmation writes
the immutable notification, recipients, append-only audit, in-app success and
retryable push outbox result in one transaction. Device registration is locked
to the current active Person/session/installation and accepts only uniquely
owned, explicit `fake` provider tokens in this delivery. The only delivery adapter
is deterministic and rejecting; no LINE, Discord, APNs or FCM provider is
configured or invoked.

Package the current `shared_lib-0.0.1.tar.gz` under `dist/` before an authorized
build. This task does not build, deploy, bind Secret Manager, change IAM or
connect to production.

The staging operator package is documented in
`docs/operations/mobile/MOBILE_STAGING.md`. It defaults to dry-run, rejects the
production project and database identity, and does not authorize deployment.
