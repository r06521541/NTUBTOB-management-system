# Multi-agent workflow improvement proposal

Status: accepted planning rationale; non-authoritative.

This document proposes a leaner collaboration flow. It does not replace
`docs/coordination/COLLABORATION.md`. After dogfood and Owner review, only the
smallest stable rules should be promoted there; this proposal should remain
explanatory rather than become a second policy source.

## 原則

1. **One writer, distinct reviewers.** Each work package has exactly one
   implementation writer. Every additional agent is read-only and must have a
   named, non-overlapping review boundary. Main Work, Domain Work and advisory
   agents do not redo the writer's general implementation analysis. An agent
   without a distinct responsibility is not added. If a writer is replaced,
   Main Work first withdraws the old assignment, updates HANDOFF and the branch
   head, then names the replacement; two writers never overlap on one package.
   Parallel packages declare owned paths in their checkpoints. An unavoidable
   path overlap is handled by one writer or a serial handoff.
2. **Review before expensive verification.** Once the first complete diff and
   writer self-review are ready, architecture, authorization and security
   boundaries are reviewed before PostgreSQL matrices, Flutter builds,
   emulator runs or hosted CI. The writer checks task invariants before this
   review so inexpensive design defects are not deferred to Work.
3. **Layered evidence, not repeated proof.** The writer runs the affected full
   suite; a Domain reviewer runs only targeted tests for its assigned risks;
   Main Work samples critical regressions and integration boundaries; hosted
   CI is the final gate. A suite is not repeated when its relevant diff is
   unchanged. Reused evidence is keyed by exact full HEAD, exact command/suite,
   runtime or database matrix and directly relevant artifact fingerprint. It
   remains reusable only while the relevant diff, dependencies and environment
   contract are unchanged. Any repeat states the new risk or evidence it
   addresses.
4. **Delta-only communication.** Cross-session handoff contains only base/head,
   changed files, new behavior, exact test results, remaining limits and next
   actor/action. Background rules are referenced by active task or
   authoritative document path and section, not pasted again. Safety-critical
   context that does not yet exist in an authoritative document remains
   explicit in the handoff rather than being omitted for brevity.
5. **One fact, one document role.** Task defines requirements, scope,
   invariants and acceptance. Report records delivered deltas and new evidence.
   Review records findings, decision and remaining work. HANDOFF carries state,
   SHAs, next action and real blockers. PROJECT_STATE contains current facts.
   The same prose is not maintained in parallel. Each document uses a concise
   information budget; insufficient space is escalated instead of silently
   creating duplicate artifacts.

## 流程

1. Main Work creates the active task with role ownership, review boundaries,
   path ownership, expensive-test ordering and a verification budget. Main
   checks path intersections before dispatch. A typical budget is one writer
   affected-full verification, one Domain targeted review, one Main risk review
   and one final hosted CI run.
2. The sole writer leaves the execution checkpoint, implements tests-first,
   completes the diff and performs an invariant self-review. Cheap parser,
   compile, targeted and diff checks may run throughout.
3. Assigned reviewers complete a whole risk-layer review and return one batched
   `changes_requested` list. Corrections are reviewed as a delta plus adjacent
   affected invariants, not as a full replay. A new finding is added only when
   correction code creates a new risk or previously unavailable evidence makes
   it observable.
4. After source review acceptance, the writer runs the affected complete suite
   once. Main Work performs bounded integration checks, then hosted CI provides
   the single final environment/matrix decision.
5. Runtime or deployment evidence runs only after repository evidence is
   accepted. Mock verification and external runtime acceptance are separate
   stages with separate claims; they are not alternated repeatedly.
6. Every handoff uses this compact shape:

   ```text
   base/head:
   changed_files:
   behavior_delta:
   tests_exact:
   remaining_limits:
   next_actor/action:
   ```

7. Main Work alone maintains global coordination and the singleton HANDOFF.
   Domain lanes report only their own decision delta. New tasks prefer clean
   sessions that read the active task, HANDOFF, PROJECT_STATE, active decisions
   and directly related code/tests; archives are loaded only on demand. Thick
   historical sessions remain advisers and inactive agents are not repeatedly
   awakened.

TASK-123 is the reference example: Shared/Web Codex is the only writer; Flutter
review covers AVD/ADB, signer, session-preserving install and runtime-stop
boundaries; Main Work checks cross-domain invariants and final integration;
the advisory lane proposes architecture/process improvements but is not part of
formal acceptance. Repository-only work is accepted before one controlled
dogfood, rather than mixing mock and emulator evidence across review rounds.

## 例外

- The verification budget is a throttle, not permission to omit necessary
  safety evidence. A high-risk correction, schema/migration change, auth or
  authorization change, credential boundary, production action or newly
  discovered external ambiguity may reset only the affected budget slice.
- Main Work records why an extra review or suite run is needed. "再保險一次"
  without a named risk is not sufficient.
- Retrying the same SHA after an identified runner, network or platform
  infrastructure failure does not consume another product-verification round,
  but the infrastructure reason is recorded. A source, configuration,
  lockfile or artifact change resets only the affected budget slice.
- A reviewer may widen its boundary only after reporting the newly discovered
  cross-domain risk; it does not silently become a second implementation
  reviewer.
- Urgent security or data-integrity defects may stop the staged ordering, but
  ownership, evidence provenance and fail-closed behavior remain required.
- Owner-only credential, consent, paid/public privilege, production and
  irreversible actions remain Owner gates even when routine staging work is
  agent-operated.

## 可觀察指標

Track only a short summary in task closeout; do not create a separate ledger or
perform token accounting:

- correction rounds before acceptance;
- number of times the same suite was run by different roles, with reason when
  greater than one;
- Owner manual operations during repository and runtime phases;
- coarse active elapsed time plus waiting reason (`Owner gate`, `external CI`,
  or `agent execution`) from assignment to source acceptance and final gate;
- coordination-only commits and PRs;
- whether report/review/handoff repeated prose that could have been a link;
- expensive verification runs discarded because an earlier design review later
  found a blocker.

The objective is a downward trend in repetition and Owner intervention without
reducing defect detection or final-gate coverage.

## 導入方式

1. Keep this proposal non-authoritative during TASK-123 dogfood. Record only
   concrete friction: repeated context, repeated suites, manual Owner steps,
   unclear evidence or unnecessary coordination artifacts.
2. Apply the proposed roles, batched review and verification budget to the next
   two suitable work packages. Compare the lightweight closeout metrics with
   recent TASK-113 through TASK-123 experience.
3. After Owner review, promote only short, stable, enforceable rules into
   `COLLABORATION.md`. Link from there to this planning rationale if useful; do
   not copy the same detailed prose into both locations.
4. Archive or revise this proposal when its remaining recommendations become
   implemented tasks. Do not open a coordination-only PR; include accepted
   planning or policy changes in the next appropriate substantive delivery
   unless an immediate safety boundary requires otherwise.
