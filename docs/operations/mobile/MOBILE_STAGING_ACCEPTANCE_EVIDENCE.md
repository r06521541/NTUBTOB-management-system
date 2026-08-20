# Mobile staging acceptance evidence contract

This document defines what may support a staging acceptance claim. It is a
contract for future launch and scenario tooling, not an instruction to perform
runtime actions. A scenario must stop when its required producer is unavailable
or ambiguous.

## Common envelope

Every retained observation is de-identified and binds:

- claim and bounded state;
- accepted full source SHA and installed artifact SHA-256 when a client is used;
- runtime revision or an opaque lowercase SHA-256 database identity fingerprint
  when a server/operator is authoritative;
- observation time and freshness class (`fresh_server`, `cold_reconstructed`,
  `offline_cache`, or `terminal_local`);
- operator (`agent` or `owner`), authorization (`DEC-098`, `owner_explicit`, or
  `read_only`), result classification, and a non-personal task ID as retention
  owner.

Allowed classifications are `PASS`, `OWNER_ACTION_REQUIRED`, `DRIFT`,
`TIMEOUT`, `FAILED`, and `EVIDENCE_GAP`. Raw child output is never evidence.
An older observation is reusable only when the relevant source, dependency,
runtime/database contract, and artifact fingerprint are unchanged.
The envelope never contains an endpoint, account or operator identity, provider
subject, person/session ID, display name, token, credential-derived identifier,
response body, raw UI/log output, storage key, file path, Secret payload, or
Secret reference name/version.

## Claim matrix

| Claim | Exact acceptable evidence | Current producer | Gap / stop rule |
| --- | --- | --- | --- |
| Logged out | Exact one enabled portal `LINE 登入` action; no principal projection | TASK-123 foreground-gated accessibility status | This proves presentation only. Session/cache purge additionally requires the logout claim below. |
| Basic authorization | Exact debug projection `basic + report disabled + fresh_server`; guarded report entry absent | TASK-122 currently projects role/grant but not provenance | Until a fresh authenticated `/me` provenance state is projected safely, automated authorization is `EVIDENCE_GAP`. Missing/duplicate/coexisting projection is `DRIFT`. |
| Officer authorization | Exact debug projection `officer + report enabled + fresh_server`; guarded report entry present | TASK-122 currently projects role/grant but not provenance | Until server provenance exists, automated authorization and every dependent report scenario are `EVIDENCE_GAP`. |
| Officer report read | Fresh server-proven Officer authorization plus one canonical `ready`, `empty`, or `offline_cached_readonly` report state; no write controls | Existing Flutter report states and direct tests lack governed semantics | Automated claim is `EVIDENCE_GAP` until both principal provenance and allowlisted report semantic producers exist. |
| Attendance reply | Canonical reply classification from a fresh server GET, or from a successful mutation response whose returned `ownReply` is explicitly marked authoritative | Client repository/model behavior; cold reconstruction was used during TASK-115 | Local selected chip is never evidence. The chosen missing producer is a privacy-safe client authoritative-reply/provenance projection; automated mutation scenarios stop with `EVIDENCE_GAP`. |
| Basic offline cache | Launcher-proven network isolation plus `offline_basic_readonly`; cached list visible; zero enabled mutation controls | Existing offline UI/tests lack a governed producer and restore receipt | Automated claim is `EVIDENCE_GAP` until allowlisted state/counts and a `finally` network-restore receipt exist. |
| Officer offline report cache | Fresh server-proven Officer authorization before isolation, then `offline_report_readonly`; zero write controls | Existing report cache behavior/tests lack a governed producer | Automated claim is `EVIDENCE_GAP` until principal provenance, report semantics, cache ownership, and restore receipt are all observable. Offline state never grants capability. |
| Downgrade cache purge | Fresh `basic + report disabled`, report route absent, and debug-only aggregate showing Officer report cache absent for the current installation | Existing source policy clears on downgrade | Physical absence is not currently projected safely; UI absence alone is insufficient. Automated downgrade scenarios stop with `EVIDENCE_GAP`. |
| Logout/session purge | Exact logout completion followed by one cold start showing logged-out state, plus debug-only aggregate `session absent`, `basic cache absent`, `officer cache absent`, `pending intent absent` | Logged-out presentation exists; source tests cover cleanup | Physical aggregate producer is missing. Do not infer deletion solely from hidden UI; automated terminal purge claim is `EVIDENCE_GAP`. |

## Producer rules

Client diagnostics must be hard-gated by `kDebugMode` and may expose only the
bounded states above. Injection may disable diagnostics but cannot enable them
in release. The evidence key includes a direct contract test proving
`debugBuild=false + injectedFlag=true` remains disabled and a release-artifact
negative scan proving the semantic identifiers are absent. Accessibility
inspection is allowed only for the exact foreground portal package and returns
allowlisted state/counts, never raw hierarchy.

Database/operator diagnostics must use the candidate approval bound to the
exact full commit, candidate revision, immutable image digest, fixed staging
project/service, and exact Secret reference name/version. These reference values
are compared in memory only and are never retained. Evidence may retain only an
opaque SHA-256 approval fingerprint derived from the approved non-secret
metadata. A changed candidate or Secret reference requires a new Owner approval;
a read-only observation of the unchanged approved candidate does not. The
expected database fingerprint comes only from that approval. The operator
derives the same normalized target
identity from the private DSN in memory, emits only the opaque SHA-256 or an
exact-match boolean, uses a read-only transaction and exact fictional fixture,
and never emits the DSN or its components. Diagnostics return only bounded
canonical state and aggregate ownership; they do not select or output identity
subjects, session IDs, tokens, payloads, names, or unrelated principal data.

## Authorization boundary

DEC-098 permits agents to run routine launcher actions, app lifecycle,
fictional reversible staging mutations, read-only reconciliation, offline/cache
checks, and bounded evidence capture. Owner action remains required for LINE
credentials/QR/login consent, Secret payload delivery until the no-disclosure
broker exists, new paid/public IAM or cloud resources, production, real
notifications, irreversible deletion, and release signing/store actions.

## Follow-up implementation slices

Implement gaps as these ordered one-writer packages. Packages that share Flutter
paths are serial handoffs to the same writer; they never run concurrently:

1. Principal freshness producer — owned paths:
   `clients/flutter_app/lib/basic_app.dart` and its direct widget tests. Add only
   bounded `fresh_server` versus non-authoritative provenance.
2. Report-state producer — owned paths:
   `clients/flutter_app/lib/officer_prereview.dart` and
   `clients/flutter_app/test/officer_prereview_test.dart`. Add only canonical
   online/offline report states and write-control count.
3. Attendance producer — owned paths: the game-detail portion of
   `clients/flutter_app/lib/basic_app.dart` and its direct tests, after package
   1 completes. The chosen authority is client-observed server reply/readback;
   there is no parallel database implementation.
4. Cache/session aggregate producer — owned paths:
   `clients/flutter_app/lib/integration.dart`,
   `clients/flutter_app/lib/basic_app.dart`,
   `clients/flutter_app/lib/officer_prereview.dart`, and their exact direct test
   counterparts under `clients/flutter_app/test/`. It runs serially after
   packages 1–3. Expose booleans/counts only, never keys or principal identity.
5. Launcher observation consumers — serial slices. Slice 5a consumes only the
   accepted package-1 principal provenance vocabulary in:
   `tools/Invoke-MobileStaging.ps1`,
   `tools/tests/test_mobile_staging_launcher.py`, and
   `docs/operations/mobile/MOBILE_STAGING.md`. Later slices consume report,
   reply, and cache/session vocabulary only after their producers are accepted.
   The combined consumer ownership remains:
   `tools/Invoke-MobileStaging.ps1`,
   `tools/tests/test_mobile_staging_launcher.py`, and
   `docs/operations/mobile/MOBILE_STAGING.md`. It is implemented only after the
   corresponding client vocabulary is accepted.

The Staging Acceptance Harness must not be implemented until every claim used
by its first named scenario has a non-gap producer and direct fail-closed tests.
