# Mobile API

TASK203 additionally supplies optional receipt-only `/account-erasure/receipt/challenge`
and `/account-erasure/receipt/verify`. A requested receipt binds the job/target
generation; a separate nonce-bound provider proof resolves one exact current owned
identity inside the locked transaction. Pending and blocked linked accounts need
no business session. Multiple owned identities are not selected by client IDs.
This proof has separate key/AAD/purpose from intent and cancellation; no provider
I/O occurs under DB locks. Explicit confirmation is required, unknown commit means
reconcile rather than retry. Disabled by default and not complete erasure.

Independent Flask/Cloud Run deployment unit for the native API. Basic access
remains isolated; Officer/Admin receive only explicitly projected bounded reads.
The canonical machine-readable contract is `openapi.json`.

The runtime core accepts only the explicit revisions in `revision_readiness.py`:
`0008` through `0014`, plus `0019` through candidate `0023`, using their full migration identifiers.
Unlisted intermediate revisions are not implied to be compatible. This permits deploying
the compatible runtime before the Apple lifecycle migration; unknown, malformed,
and unlisted future revisions fail closed. Apple exchange and notifications use
the independent allowlist in `MobileRepository.apple_lifecycle_ready` (currently
`0010` through `0014`, plus `0019` through candidate `0023`), not an exact-0010-only gate. Both require exactly
one known revision; an empty or multi-head version table fails closed. The
additive `0013_account_deletion_requests` receipt table preserves `0012`
authority checks, Apple admin-recovery handling and event notification fields;
it does not enable account-deletion requests in the default runtime. These are
code compatibility contracts, not evidence that any environment has been migrated.
`PORTAL_DATA_ERASURE_CHECKS_ENABLED` is missing/`false` by default. Exact `true`
passes account-erasure guards to both runtime repositories and their nested
repositories; invalid values stop construction before credential/service wiring.
Mobile does not require Web's Phase C flag. This guard setting does not inject the
optional account-erasure service or enable its UI, provider effects or execution.
The separate `MOBILE_API_ERASURE_INTAKE_ENABLED` is also missing/`false` by default;
only exact `true` injects `Dependencies.account_erasure` in the actual bootstrap.
Other values reject startup before normal service construction. Off does not read
the new erasure keys or instantiate erasure services. On requires the guard flag,
the complete valid Apple lifecycle group, the existing exact LINE/Apple audiences,
and `MOBILE_API_ERASURE_GOOGLE_AUDIENCE` as one exact member of the existing Google
allowlist. This dedicated Google verifier uses only that audience and a mandatory
fresh nonce; ordinary Google login is not deletion proof.
`MOBILE_API_ERASURE_RECEIPT_KEY` and `MOBILE_API_ERASURE_PROOF_KEY` are runtime-injected
canonical padded URL-safe base64 with at least 32 decoded bytes. They must differ
from each other and the existing access-signing, refresh-replay and Apple provider
encryption key material. Invalid enabled configuration fails with the fixed ASCII
message `invalid erasure intake configuration`, without values or provider I/O.
The five proof purposes retain separate cryptographic domains and the fixed local
proof audience `ntubtob-mobile-account-erasure`.
This assembly uses `ErasureIntakeRepository` and the approved
`ErasurePlanPolicy.initial_request` policy: request-time intake needs no human
review, while later scope review/materialization remains separately authorized.
It supplies request, receipt, fresh verification, cancellation and recovery, not
an executor, sealed-plan store, materializer, provider logout, scheduler or cleanup.
The example remains off. This source composition is **not standalone rollout
approval**: full operator/custody/guard/preflight readiness is still required;
neither a verified request nor session revocation means erasure is complete.
All signing, refresh-response encryption, and
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

TASK-203 adds a source-only `allow_first_login=False` Apple auth constructor
option. Normal bootstrap does not enable it. In isolated tests with the option
enabled, a verified assertion first creates a pending identity/review thread,
then the single-use code is exchanged; credential completion rechecks the exact
pending identity. Provider failure can leave an assertion-verified pending row,
not an active Person or proof of credential acquisition. Unexpected completion
failure after provider success returns `service_unavailable`, `retryable=false`,
and fixed app-completion provenance; never replay the consumed authorization code.
This is not a complete onboarding/deletion rollout. Earlier unknown-subject
revocation receipt correlation, deletion fulfillment and deployment gates remain.

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

The source-only `0013_account_deletion_requests` migration is additive and the
optional request service is not injected in normal bootstrap. A future rollout
must first establish a compatibility-ready rollback build that accepts 0013;
the earlier 0012-only build may fail its revision guard after migration. Roll
back only to that compatible application, never erase acknowledged receipts.
Its downgrade
retains the table; a schema downgrade followed by a blind re-upgrade is not a
supported rollback/retry procedure. Retained-schema reconciliation needs an
explicit reviewed plan; only guarded local fictional test harnesses remove it.

The staging operator package is documented in
`docs/operations/mobile/MOBILE_STAGING.md`. It defaults to dry-run, rejects the
production project and database identity, and does not authorize deployment.

TASK-203's `MobileRepository(erasure_checks_enabled=True)` remains default off;
bootstrap propagates the explicit guard environment flag described above. It
checks the attached erasure ledger for exchange, access-token
resolution, refresh (including saved-successor replay), and identity linking;
logout cleanup remains available. It does not make all Portal/LINE/notification or
business mutations erasure-safe. Candidate0015 acceptance in the private guard is
not general runtime revision readiness. The separate verification coordinator
requires a trusted, local fresh-proof verifier; no client boolean or ordinary login
token is deletion authorization.
Do not enable real verification/fulfillment until every entry point is covered.

The optional `Dependencies.account_erasure` composition is default `None` and is
wired only by the explicit intake opt-in above. It exposes request, receipt-bound
challenge and verification endpoints documented in OpenAPI. The encrypted challenge
binds a server nonce and current target generations; existing provider verifiers run
outside the mutation transaction. Local proof validation and locked generation checks
precede committed session revocation. `verified` is neither complete access blocking
nor deletion completion. Intake uses the fixed initial policy and separate proof
purposes; restricted requests use the same durable intake repository. The older
reviewed-plan component factory remains available for explicitly composed internal
workflows. Cancellation uses a separate proof service and the existing coordinator.
Runtime activation, fulfillment and native SDK wiring are not implied.

The default-off POST `/api/v1/account-erasure/status` reads a minimal receipt state
without an app session, including after verification revokes sessions. It accepts
only job UUID plus confidential receipt secret in bounded JSON; never a query string.
Unknown/invalid/expired receipts reject uniformly, responses are no-store, and the
reader cannot mutate state or call providers. Receipt readback does not authorize
retry or cancellation, and a stored status alone is not full fulfillment evidence.

The default-off cancellation challenge accepts job/receipt/provider, without an
ordinary session. One nonce-bound provider interaction supplies the subject;
the transaction resolves its current exact identity and target generation, checks
receipt/proof expiry and the irreversible fence, then cancels/detaches and records
evidence atomically. Explicit confirmation is required. It never reactivates
sessions, identities or permissions. Uncertain commit returns nonretryable error;
use receipt status reconciliation rather than automatically resending. Candidate
0016 retains cancellation/fence evidence on downgrade; an old revision marker is
not compatibility permission, and legacy uncertain jobs require reconciliation.

Default-off `/api/v1/account-erasure/request/challenge` and `/request` accept no
application session or client-selected identity. A fresh nonce-bound provider proof
creates only a requested intent for an existing exact identity, including restricted
or pending accounts. The immutable opaque attempt binding survives cancellation;
replaying it cannot create a replacement job. Provider verification occurs before
the repository transaction. No account is created and no job is verified or erased.
Receipt secrets stay in bounded no-store JSON; uncertain outcomes are nonretryable.

Pending-identity applicants can then use `/api/v1/account-erasure/pending/challenge`
with only their job/receipt. The stored job selects its exact current identity;
no normal session, client identity ID or provider selector is accepted. It issues
the separate fresh verification challenge, not deletion authority. `/verify` still
requires nonce-bound provider proof and locked generation checks. Person-scoped
jobs do not use this pending entry; all erasure routes remain default-off.
