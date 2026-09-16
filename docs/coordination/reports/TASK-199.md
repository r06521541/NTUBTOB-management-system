# TASK-199 account-foundation delivery report

Status: source accepted; normal PR/hosted integration pending. No runtime rollout.
Accepted source: fae9f094cca00864ee541e158f0c7d5b6c8745a5.
Base: d83bd4b1e64bad119f780344fbde6d57c378f308; branch codex/task-199-account-foundation.

## Behavior and boundaries

- Optional current-principal deletion request/status API and durable one-row-per-
  Person receipt. Constant command, canonical UUID request key, exact bounded
  confirmation and no arbitrary target. Transaction rechecks identity, Person,
  session, epoch and expiry under the existing lock order. No fulfillment,
  Person/Member/session deletion, notification or provider revocation.
- Additive0013 source migration enables RLS and retains receipts on downgrade.
  Explicit0012/0013 consumer compatibility preserves admin authority, Apple
  last-admin recovery and Event notification projection. Unknown/multiple heads
  fail closed. No production inventory/operator contract widened.
- Flutter request page uses onsite confirmation, current-generation client,
  offline rejection and manual GET reconciliation after uncertain POST. Only
  fictional demo injects it; normal real bootstrap/API remain disabled. Strict
  receipt parsing never accepts completed-deletion claims or extra private fields.
- Main reproduced five original session-generation races. Independent review
  caught missing cleanup-barrier and exceptional-network cases; corrections now
  cover27 deterministic races, fixed durable cleanup debt and full installation-
  scoped personal-data purge before credential publication. Network waits are not
  serialized. Readonly generation notifications immediately invalidate request UI.
- Wrong basketball-school title corrected to the existing native App title.
  No redesign, first-release freeze, dependency or store-policy answer invented.
- MOBILE_PRIVACY_DRAFT separates first-party source, vendor claims and unknown
  native archive/runtime evidence. Google SDK IP/User-ID processing is not
  erased by the App reading only ID tokens. The draft is not a published policy.
- HANDOFF reduced to current singleton; PROJECT_STATE reconciles real TestFlight
  success with remaining gates instead of retaining contradictory pre-signing
  entries. TASK198 post-merge evidence preserved in its task/report; historical
  upload sidefile uncertainty remains explicit, not converted to cleanup PASS.

## Read-only staging result

On2026-09-16, exact-target `gcloud run services describe` for the isolated staging
service returned the previously recorded revision at100% traffic. Explicit
`spec.template.spec.containers[0].env[].name` projection listed only the five
existing audience/Google/session/database keys; all four Apple lifecycle key
names are absent. The first nested projection returned no env field, which was
not treated as absence; the corrected names-only projection supplies this result.
No value, Secret payload, database contents or user information read.

Next Apple prerequisites: current isolated schema readiness, reviewed four-key
configuration/custody and backend rollout, then true device provider acceptance.
This package authorizes none of those writes. Do not ask Owner to test an unready
Apple backend or recreate existing signing/upload credentials.

## Evidence so far

- Shared sdist rebuilt after both backend writers completed; offline installed
  into ignored `.cache/task199-shared-final` with no dependency download. Import
  path confirmed that snapshot for service suites.
- Mobile API89PASS; shared73PASS; Web Portal251PASS; game broadcast28PASS;
  notify cron11PASS; LINE webhook26PASS; schedule update5PASS. Negative-path
  log lines are expected test fixtures, not live service requests.
- Portal data370 tests:197PASS/173PostgreSQL SKIP. Docker daemon unavailable;
  this is not PostgreSQL runtime proof. Hosted15/16 matrix still required.
- Client account/support/demo42PASS after state corrections. Added real-
  JSON-decoded impossible-date cases RED then GREEN; initial dynamic-map fixtures
  had rejected on map type rather than field value and were corrected.
- CI/workflow/store-readiness50 tests:49PASS/1Windows-bash SKIP.
- Python quality24paths PASS. Phase C migration/evidence/readiness artifacts
  verify PASS; original controlled SQL/checksums unchanged.
- Main full `flutter test --no-pub --reporter expanded`:395PASS; full
  `flutter analyze --no-pub`:no issues. Independent final source ACCEPT, with
  27race/42client independent tests and backend fingerprints bound to exactSHA.
  Hosted CI pending. Source documentation33local links valid, no missing targets.

## Remaining product and rollout decisions

Formal deletion intake/fulfillment, pending/restricted identities, historical
Person/Member/attendance retention, time limits, confirmation and provider
revocation remain future scope. Legal/service identity, public support contact,
privacy/support/deletion URLs and final store disclosures are not guessed.

A future0013 rollout needs a compatibility-ready rollback build first; the old
0012-only runtime may reject0013. Rollback must retain receipts; blind schema
downgrade/re-upgrade is unsupported. Test-only cleanup is constrained to the
isolated localhost named database. No migration/backfill/production write ran.

External mutations: none so far. Local build/cache artifacts only; no signing,
upload, deployment, provider/Secret/store changes or device requests. No additional
paid service and no reset of the existing USD20 cap. Git/PR/CI integration remains
pending hosted integration; final source readiness and independent review passed.
GitHub metadata confirms public repository/default main and unchanged base.
Existing CI uses standard hosted runners, no signing/release environment or new
service. [GitHub billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
checked2026-09-16 states standard hosted runner usage in public repositories is
free; no paid runner/service is selected and aggregateUSD20 is not reset.
