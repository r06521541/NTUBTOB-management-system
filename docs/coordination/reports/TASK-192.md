# TASK-192 writer report

Writer `/root/csr_writer`, claim `task-192-writer-20260910` lease1.
Base/HEAD `2a5cd24889b0505a78c95defa7e3729068992611`;
branch `codex/task-192-cms-predicate-diagnostics`. Dirty handoff, no commit/push.

## Result / invariants

Added 25 fixed CMS predicate keys to the existing local `--diagnose-input`
result as `cms_predicates`, with only PASS/REJECTED/NOT_CHECKED values. Existing
`checks.cms` retains the first rejection stage. Same bounded `_preflight` parser
and ordered predicates serve production fail-fast and diagnostic collection;
no alternate parser, payload patch/retry, native call or trust relaxation.
Digest cardinality blocks only digest-set element rules; unsupported SID blocks
only signer binding. Attribute value prerequisites and certificate prerequisites
are explicit; independent later attributes, certificates and DER checks continue.
Unknown predicate exceptions produce fixed rejection evidence and never overwrite
an already recorded first-stage failure. Intake validates the helper's complete
fixed schema and rebuilds fixed output keys; unexpected results become UNKNOWN
with the predicate matrix NOT_CHECKED.

Repeated rules aggregate evaluated instances: any failure wins; PASS means all
evaluated instances passed, not that prerequisite-excluded children were checked.
No applicable/evaluable instance means NOT_CHECKED (including absent optional
signing time). Certificate uniqueness/binding require the complete eligible set.
Invalid ASN.1 signing-time types fail bounded schema materialization before the
datetime predicate; this is not an additional permissive date parser.
All existing trust/signature/profile/sign/upload/release flags remain false.
Default/execute, same-handle custody, native code, dependencies and workflows unchanged.

## Evidence

- Tests-first: the two combined-failure/prerequisite tests initially failed because
  the new diagnostic API did not exist; both now pass.
- `py -3.10 -m unittest tools.tests.test_ios_profile_cms_verification
  tools.tests.test_ios_profile_intake -q`: 35 run, 34 PASS, 1 native macOS skip.
  Initial sandbox run hit the existing fictional Windows fixture ACL setup
  rejection. Same unchanged command passed with scoped escalation for disposable
  fictional fixture ACLs; no actual Owner directory or input was accessed.
- Coverage: each reachable predicate rejection, valid matrix, optional signing
  time, malformed time schema, combined algorithm/attributes/binding/canonical
  failures, specific prerequisite NOT_CHECKED, downstream unexpected exceptions,
  safe helper-output allowlisting, sentinels and no native/network/file output.
- One-time frozen-base differential: read the public CMS module using `git show`
  at the exact base above; compiled it into a separate in-memory module, without
  writing a historical source copy. Compared 52 fictional inputs (3 valid subset
  fixtures, 24 predicate mutations, 25 existing malformed corpus cases). All
  acceptance, exception args/stage, and successful parsed return data matched.
  Persistent tests use fictional fixtures, not historical Git availability.
- Owned Python formatting/check and `git diff --check` pass.

## Limits / handoff

Software preparation only. No real profile read, Owner diagnostic execution,
network/API, lock/output file, native verification or external mutation occurred.
Fictional tests alone do not explain the Owner's actual rejected algorithm or
establish CMS authenticity. Independent acceptance and hosted CI remain Main's
gates before a new exact-SHA Owner confirmation and the single approved diagnostic
run. If that run is insufficient, stop inconclusive; no third iteration/retry.

Owned changes are the CMS/intake Python modules, their two test modules and this
report only. Main's task/HANDOFF/PROJECT_STATE/runbook/carry-forward records were
preserved and not edited by writer.
