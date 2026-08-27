# TASK-160 Codex report

## Implementation delta

- `mode=browser` resolves the safe local return path, clears the existing Portal session, and then creates a fresh signed state/nonce transaction. Normal LINE in-app login does not clear an authenticated session.
- Production Dashboard now supplies its reply forms with the session CSRF token. The existing POST guard, repository write and notification behavior are unchanged.
- Dashboard groups every game on the first upcoming local calendar day under `下一個比賽日`; only later dates appear under `近期賽程`, with independent links, reply state and forms.
- People management retains the existing active-only default and explicit `show_inactive=1` switch, now with a visible current-filter explanation; search and pagination preserve that switch.
- Pending identity forms project only active/inactive People with a positive Member link into the chooser. They include a placeholder, inactive activation warning and empty state; disabled/blocked/unlinked targets are omitted and forged approval/remap targets fail closed before mutation. A disabled fieldset consistently freezes all mutation controls while identity maintenance is off.

## Verification

- Focused TASK-160 regressions: 7 passed.
- Independent-review correction regressions (Member approval form separation, empty chooser, remap and maintenance freeze): 4 passed.
- `py -3.10 -m unittest discover -s apps/web_portal/tests -v`: 212 passed, 2 skipped because Windows lacks `make`/`sh` for executable deployment-wrapper coverage.
- `py -3.10 -m py_compile apps/web_portal/app.py apps/web_portal/tests/test_admin_security.py apps/web_portal/tests/test_brand_ui.py`: passed.
- Black 24.4.2 formatter API comparison for the three Python files: passed. The multi-file Black CLI hung in the known Windows environment failure mode and was terminated; it made only the intended test-file formatting change before termination.
- isort check reports the same pre-existing import-order failure on `app.py` and `test_admin_security.py` at merged HEAD; this task adds no imports.
- `git diff --check`: passed (Windows LF-to-CRLF checkout warnings only).

## Limits

- No browser/provider, production data, cloud, runtime, Secret, schema, notification or deployment action was performed.
- Identity maintenance remains disabled by default and requires its separate Owner-gated production rollout.
- Repository tests do not prove that production has been deployed or manually accepted.
