# TASK-168 Codex report

## Delivery delta

- Added one shared Event attendance boundary for Event and ordinary Activity three-state replies (`attending`, `not_attending`, `maybe`), low-sensitive aggregate counts, and atomic Event apply-all that excludes every Activity linked to a Game.
- PostgreSQL and in-memory writes revalidate the active Person, immutable included invitee, published status and non-ended Event inside the mutation boundary. Linked Game Activities reject the three-state mutation and continue through the existing five-state Game attendance path.
- Added canonical Mobile PUT routes and OpenAPI projection. Mobile idempotency uses the existing durable server ledger; Flutter retains one installation-scoped intent key across ambiguous delivery, reconciles only from an authoritative Event GET, and never reports uncertain delivery as success.
- Added Web CSRF-protected POST/Redirect/GET flows and the existing site-native confirmation behavior. Event and ordinary Activity controls expose only three states; a linked Game renders the existing five states and returns to its Event detail after the existing Game mutation.
- Added regression coverage across shared projection/service/repository contracts, Mobile route/OpenAPI, Web CSRF/PRG/linked-Game behavior, and Flutter contract/UI/durable-uncertainty behavior.
- Lease-3 reviewer correction gives both fictional production-demo Persons `events:read` and supplies an entirely in-memory Event read/mutation adapter. Its ordinary Activities share the three-state model and apply-all behavior, the linked Game has no duplicate Event attendance and mutates only the existing five-state Game adapter, and explicit failure/uncertain fixture overrides remain fail closed without touching transport.
- Main performance correction removes the per-published-Event repository/Session loop from `scoped_events()`. The existing lifecycle Session now performs one set-based included-invitee read, one joined Event-reply read and at most one joined non-linked-Activity-reply read for the whole visible Event set; detail remains routed through the same fixed-query batch and does not add attendance round trips as other Events grow.

## Verification

- `py -3.10 -m unittest discover -s shared_lib/tests -v`: 63 passed.
- `py -3.10 -m unittest discover -s apps/mobile_api/tests -v`: 48 passed.
- `$env:PYTHONPATH='.'; py -3.10 -m unittest discover -s apps/web_portal/tests -v`: 239 passed.
- `py -3.10 -m unittest tests.portal_data.test_repository_contract.InMemoryRepositoryContractTests -v`: 22 passed.
- `tools/Invoke-FlutterToolchain.ps1 flutter test --no-pub test/basic_app_test.dart test/integration_test.dart`: 156 passed after the regression exposed and the implementation corrected an optional Event-mutation `activity_id` parse failure.
- Lease-3 `flutter test --no-pub test/production_demo_test.dart`: 19 passed. The first two correction runs exposed three adjacent tests whose lazy home-list assumptions no longer held once the required Event entry became visible; the direct tests now reveal their target rows explicitly and the complete file passes.
- Lease-3 combined `flutter test --no-pub test/basic_app_test.dart test/integration_test.dart test/production_demo_test.dart`: 175 passed.
- Lease-3 affected six-file `flutter analyze --no-pub`: no issues.
- Performance correction direct batch contract plus in-memory repository contracts: 23 passed. The batch regression projects two Events in exactly three attendance queries and proves that linked Game attendance remains `null`.
- Post-correction shared 63, Mobile 48 and Web 239 tests passed; Python compile and `git diff --check` passed.
- Affected `flutter analyze --no-pub`: no issues; canonical Dart format and same-version Black formatter API completed.
- Python compile, OpenAPI JSON parse and `git diff --check`: passed; diff check emitted only expected Windows LF-to-CRLF checkout warnings.
- One intermediate shared-suite rerun hit the pre-existing probabilistic last-base64-character tamper assertion in `IdentityLinkProofCodecTest`; its isolated rerun and the subsequent complete 63-test suite both passed without a code change.

## Remaining gates

- Independent Data／Authorization rereview accepted immutable implementation commit `d7d1fbc9755e1aa66d26b47ff46ea475368ae063` with no actionable findings.
- PR #217 passed every selected hosted gate, including Flutter and PostgreSQL 15／16, and merged as `cabdbcd039c9d526adb21fd8b11e145cd48f2574`.
- Deployment remains a separate Owner-gated delivery and was not performed by TASK-168.
- No schema/migration, notification behavior for Event/ordinary Activity, provider, Secret, IAM, cloud resource, production database or production runtime was changed.

## Ready handoff

- Main rereview accepted the fixed-query attendance batch, linked Game exclusion and transaction-time active/open revalidation; its targeted regression sample passed 3/3 and `git diff --check` was clean.
- Writer self-review confirmed the complete diff was limited to TASK-168 lease-3 owned implementation, direct tests and this single report. The writer claim is complete and repository coordination has returned to Main Work.
