# TASK-170 Play Closed Testing evidence writer report

## 2026-09-02 Play application checkpoint

Owner has created the Play application as `NTUBTOB`, package `tw.org.ntubtob.portal`, zh-TW, application/free. No artifact was uploaded
and no track/open/production/tester notification action occurred. `ANDROID_CLOSED_TESTING_PLAY_ANSWERS.md` now records bounded
Basic-only Data Safety/tester-answer principles and leaves current Console questions plus public privacy/support/deletion URLs as
explicit Owner-visible verification gates rather than guessed values.

- actor: `/root/task170_play_evidence_writer`
- claim: `task-170-play-closed-evidence-writer-20260831` / lease 1
- scope: repository-only, deidentified external evidence contract
- state: ready for Main integration review; not committed

## Delivered

1. `ANDROID_CLOSED_TESTING_CHECKLIST.md` defines the exact operator boundary and completion checklist for
   `tw.org.ntubtob.portal`, `android-closed`, `staging:real`, Basic-only. It separates repository validation from external
   truth and forbids login, network, key creation, build/sign/upload, Console/store/cloud/device/production operations by the tool.
2. `android_closed_testing.py` accepts one bounded UTF-8 JSON file with exact fields only. It fail-closes on duplicate/unknown/missing
   fields, sensitive-shaped values, package/version/artifact drift, non-monotonic version code, signer mismatch, non-isolated or
   production runtime, expanded product scope, incomplete or reference-aliased Data Safety/privacy/support/deletion/tester notes,
   incomplete Android 15 device results, non-closed/public/notified track state, or any remaining blocker.
3. Exact artifact SHA is shared by artifact/device/track evidence. Track package/version must match the inspected artifact. Only LINE
   and Google login may be marked `unavailable`; tester notes must list the same unavailable scenarios exactly. All core flows must pass.
4. Successful CLI output is sanitized: it retains the immutable commit/package/version/artifact binding and boolean signer comparison,
   but omits signer fingerprints and all external evidence refs. `external_truth_attested: false` prevents repository validation from
   being represented as Console/device/runtime proof.
5. The mobile release matrix now routes TASK-170 exact candidate evidence to the dedicated checklist without placing the candidate
   record in the cross-channel matrix.

## Verification

- `py -3.10 -m unittest tools.tests.test_android_closed_testing -v`: PASS, 16/16.
- `py -3.10 -m py_compile tools/android_closed_testing.py tools/tests/test_android_closed_testing.py`: PASS.
- Documentation template extraction + `validate_evidence(json.loads(sample))`: PASS, returned `validated`.
- `rg -n --pcre2 '.{89}' tools/android_closed_testing.py tools/tests/test_android_closed_testing.py`: PASS, no overlong code lines.
- `git diff --check`: PASS; Windows LF→CRLF warnings only.
- `python -m black --check ...`: not run because Black is not installed in the active Windows Python.

## Self-review findings

- Initial review found that a merely positive version code did not establish monotonicity; the final schema requires
  `version_code > previous_version_code` and has a regression case.
- Initial review found that printing a raw `OSError` could disclose the caller-supplied input path; the CLI now returns only the fixed
  `BLOCKED: unable to read evidence input` message.
- Static regression asserts that the tool imports no network, subprocess, browser automation, `gcloud`, `keytool`, or `jarsigner`
  clients. The implementation only parses and validates local evidence input.
- Reviewer correction proved that one `EV-SAME` reference could previously satisfy all five compliance gates. The validator now
  requires Data Safety/privacy/support/deletion/tester-notes references to be pairwise distinct; the regression first failed on the
  old behavior and passes after the focused fix. Sanitized output and `external_truth_attested: false` are unchanged.

## Remaining limits

- The tool does not prove that supplied `EV-*` references or signer fingerprints are truthful. Main/Release review must inspect the
  external controlled evidence against the exact accepted AAB.
- No real signer, endpoint, provider/account, Secret, Console session, device identifier or production data was accessed or recorded.
- No AAB was built/signed/inspected by this lane; no Play Console track, Data Safety form, privacy/support/deletion route, staging
  runtime, real device, upload, processing state or tester availability was externally observed.
- Repository Main still owns integrated review, full affected gates, immutable acceptance, hosted CI and all later Owner-gated
  external phases. A `validated` fictional/local record is not release authorization.

## Exact changed paths

- `docs/releases/ANDROID_CLOSED_TESTING_CHECKLIST.md`
- `docs/releases/MOBILE_RELEASE_MATRIX.md`
- `tools/android_closed_testing.py`
- `tools/tests/test_android_closed_testing.py`
- `docs/coordination/reports/TASK-170-PLAY-CLOSED.md`
