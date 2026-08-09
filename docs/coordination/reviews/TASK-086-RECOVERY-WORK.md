# TASK-086 production bootstrap recovery Work review

## First review（2026-08-10）

- Reviewed branch `codex/phase-c-bootstrap-recovery`, implementation `41aee61ac9bdf10544e001b4965253bb969b783b`, handoff HEAD `1c10d8dc41eb6fd2089b0d9249842364ade5671d`; checkout was clean.
- The launcher correctly replaces the failing repeated-list projection with the reviewed strict in-memory env metadata parser and preserves the exact five-stage sequence and no-disclosure boundaries.
- Work reran the combined 43-test launcher/operator/diagnostic suite. 41 passed, but two artifact-lock tests failed before any external access because the committed checksum is the raw CRLF hash `dd45f3e...`, while `_sha256()` intentionally canonicalizes CRLF to LF and computes `3db2253...`.
- This makes the production launcher fail closed on the documented Windows checkout and is a blocking release defect. No gcloud, private env, production connection or mutation occurred.

Conclusion: `changes_requested`. Regenerate the checksum with the launcher's canonical LF algorithm (not raw `Get-FileHash`), add or retain a regression that proves `verify_artifacts()` on the documented Windows checkout, rerun the 43-test combined suite, and update report/HANDOFF. Do not change launcher behavior or perform external operations.

## Second review（2026-08-10）

- Fix commit `2bebcb43494c93d6e1a84e83fe49f4d161175b03` changes only the launcher checksum from the raw CRLF digest to the runtime-canonical LF digest `3db2253f...`; launcher behavior is unchanged.
- Work directly ran `verify_artifacts()` on the documented Windows checkout: passed.
- Work reran the combined launcher/operator/diagnostic suite: 43/43 passed; `git diff --check` passed.
- No external or production operation occurred during review.

Conclusion: `accepted`; proceed to the single ready PR, hosted CI and the Owner-approved exact production recovery sequence after squash merge.
