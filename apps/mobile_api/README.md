# Mobile API

Independent Flask/Cloud Run deployment unit for the native API. Basic access
remains isolated; Officer/Admin receive only explicitly projected bounded reads.
The canonical machine-readable contract is `openapi.json`.

The runtime core accepts only the rollout-compatible revisions
`0008_mobile_notification_delivery`, `0009_event_management_writes`, and
`0010_apple_provider_lifecycle`. This permits deploying the compatible runtime
before migrating to `0010`; unknown, malformed, and future revisions fail
closed. Apple exchange and notifications remain independently unavailable until
the schema is exactly `0010`. All signing, refresh-response encryption, and
existing provider audience configuration must also be present. The
LINE audience and bounded `MOBILE_API_GOOGLE_AUDIENCES` allowlist are separate
plain runtime values. Apple lifecycle configuration is optional as one
indivisible group: exact client audience, runtime-injected client secret,
independent provider-credential encryption key, and exact notification audience.
The provider-credential key must differ from the mobile refresh replay key. A
missing or blank value, reused key material, or pre-`0010` lifecycle schema disables Apple
authentication and notifications only; LINE and Google remain available. Apple
ID tokens and server notifications use a bounded, thread-safe cache of Apple's
public RSA signing keys. Database, signing, replay, client-secret, and
provider-encryption keys remain Secret-backed. Readiness checks are read-only;
this directory contains no credential and no deploy target.

Apple login accepts an exact nonce-bound ID token plus a single-use
authorization code. The server verifies the assertion before reserving the code,
exchanges it once with a bounded HTTPS client, correlates the returned subject,
and persists only an independently encrypted provider refresh credential plus
hashes. Timeout or unknown exchange outcomes are terminal and never retried.
The public notification route accepts exactly one bounded Apple-signed JWS;
revocation/deletion events atomically disable the Apple identity, its app
sessions, and provider credential, while email-forwarding events are receipt
only. Provider configuration, endpoint registration, active token revocation,
credential-state inspection, deployment, and provider smoke remain future
Owner gates. App access/refresh tokens remain server-owned application sessions,
not Apple provider sessions.

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
