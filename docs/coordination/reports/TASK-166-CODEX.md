# TASK-166 Codex report

## Delivery delta

- Desktop `mode=browser` first creates a distinct-salt, two-minute signed initiation envelope containing only exact purpose, validated local return path and a random nonce, then redirects to a bootstrap route on the fixed callback origin; the initiating host does not determine that origin.
- The canonical bootstrap validates the envelope, host and bounded same-browser consumed-digest history before clearing the prior canonical Portal session. It then stores a fresh random OAuth nonce and validated local return path and redirects to a one-shot canonical authorize route. Unsigned, tampered, expired, wrong-purpose, malformed, wrong-host or same-browser replayed inputs fail before session clearing, OAuth-state creation or LINE redirect; the initiation envelope is not accepted as callback state.
- The authorize route requires the canonical origin and exact session bootstrap, consumes the pending marker／return path, retains the nonce for callback comparison, and only then redirects to LINE with `disable_auto_login=true`.
- Invalid bootstrap, authorize or callback transactions clear temporary OAuth state as appropriate and return the existing generic response. Diagnostics use only `state_invalid_or_expired`, `session_nonce_missing`, `session_nonce_mismatch` or `browser_bootstrap_invalid`; logger failure cannot change authorization behavior and no supplied value is logged.
- Normal LINE in-app login, signed-state TTL/signature, callback nonce comparison, safe return-path validation and identity matching are unchanged.

## Verification

- Regression-first focused run: 4 tests produced 5 expected failures before implementation.
- Initial continuity correction desktop bootstrap／canonical-host／callback／rejection focused tests: 14 passed across two bounded runs.
- Lease 2 signed-initiation regression-first run: 4 tests failed as expected before implementation; corrected initiation/replay and adjacent flow run: 7 passed.
- `py -3.10 -m unittest tests.test_admin_security -q`: 138 passed.
- `py -3.10 -m unittest discover -s tests -q`: 237 passed.
- Python compile, same-version Black formatter API, `git diff --check` and exact-scope review passed.
- Independent Auth/Security lease 2 rereview: `ACCEPT`; 18 focused tests and `git diff --check` passed.
- Main critical regression sample: 5 passed. Two earlier Main collection commands ran zero tests because their module paths omitted the repository import boundary; the corrected Windows command supplied the exact repository root through `PYTHONPATH`.

## Remaining gates

- Independent Auth/Security review, hosted CI, PR, production deployment and one Owner desktop acceptance remain Main／Owner gates.
- No LINE provider, callback registration, Secret, cookie policy, runtime, cloud, database, identity or notification mutation was performed.
