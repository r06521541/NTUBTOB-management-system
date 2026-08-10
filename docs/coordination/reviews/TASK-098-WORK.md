# TASK-098 Work Review

status: changes_requested
reviewer: work
reviewed_at: 2026-08-10T11:30:19+08:00
branch: codex/phase-d-schema-neutral-game-command-center
implementation_commit: 3bb2b6b69ad2bd33dfaa5a258dc5ee38bb6c7d53

## Review result

Changes requested. The delivered Game command center and lineup lab remain within the schema-neutral and read-only
boundary, but the authorization change regresses the existing TASK-097 local-preview contract and the new bounded route
does not preserve the established Phase C session-to-principal binding.

## Blocking findings

1. `load_phase_c_web_principal` removed the existing local-preview mapping from persisted `basic`／`officer`／`admin` to
   the preview portal roles. TASK-098 requires the existing production principal resolver and non-Game management routes
   to remain unchanged; TASK-097 also established production-shaped admin preview. The new bounded Game bridge can limit
   Officer access without taking existing preview Admin access away from other read-only management pages.
2. `_game_management_context` resolves only `session["user_id"]` and accepts that result without checking that the fresh
   principal's Person and Identity IDs still equal `session["person_id"]` and `session["auth_identity_id"]`. The existing
   Phase C loader clears and rejects that mismatch. New Game management routes must preserve the same binding and fail
   closed before any Game／attendance read.

## Required correction

- Restore the pre-TASK-098 local-preview behavior in `load_phase_c_web_principal`; do not alter production allowlist
  semantics or grant production Person Officer/Admin global management access.
- Make the bounded Game context validate `user_id`, `person_id`, and `auth_identity_id` against one freshly resolved
  lifecycle principal. On mismatch, fail closed consistently with the existing Phase C session lifecycle and perform no
  Game or attendance read.
- Add regression tests proving preview Admin retains the existing read-only management surface, production Officer stays
  bounded to the new Game routes, and mismatched Person／Identity session data is denied before read callers.
- Re-run the targeted authorization/static tests, the full Web Portal suite, compile/formatter checks and
  `git diff --check`. Keep schema, Game data, preview POST and all external-operation boundaries unchanged.

## Evidence reviewed

- Branch and origin both point to handoff commit `21c3173ed34b273b670aef3a0090e462c8e1c2f4`; worktree was clean.
- The implementation diff contains no schema, migration, model, controlled SQL or export-contract changes.
- The pre-task base at `6b43ab1c39639117ec0c0e555eca3668199bb321` confirms the removed local-preview role mapping.
- Codex reported 154 Web Portal tests passing with 2 skipped, desktop localhost QA, and all compile/format/static checks
  passing. These do not cover the two regressions above.

No deployment, production data, Secret, IAM, Scheduler, notification or external service operation was performed.
