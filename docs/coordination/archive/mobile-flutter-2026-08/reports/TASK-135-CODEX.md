# TASK-135 Codex report

Status: ready for targeted review.

Implemented a deterministic, task-owned rollout packager. It requires the
packager and exact clean full SHA to come from the same source root, copies only
the fixed git-tracked broker context, preserves the approved input bytes except
for the existing CRLF-to-LF normalization, validates the final context artifact
with the shared approval contract, and computes all three hashes with the
existing broker runtime algorithm.

Direct evidence:

- `python -m unittest tools.tests.test_mobile_staging_broker_rollout -v`:
  the four-finding correction suite completed 13 cases (12 passed, 1 skipped);
  the skipped case requires Windows symlink-creation permission that this host
  denied. The residual CLI source-alias regression then passed 1/1 without
  replaying the accepted cases.
- `python -m py_compile` for the packager and direct test: passed.
- `python -m isort --check-only` for the two Python files: passed after one
  mechanical import-order correction.
- `git diff --check`: passed; the checkout only reported its existing LF/CRLF
  warning for the runbook.
- Black 24.4.2 multi-file CLI, single-file CLI and formatter API checks each
  reached their bounded timeout without output on this Windows host. This is
  the repository's documented Windows formatter limitation; hosted CI remains
  the final formatting gate and no local formatter result is claimed.

The direct suite covers deterministic repeated hashes, exact private
replacement, dirty/wrong-SHA rejection, approval drift, existing output,
symlink rejection where supported, partial cleanup and one bounded JSON failure
without private sentinels. Correction regressions also cover original path
component reparse, opened-file replacement identity, hardlinks, exact database
fingerprint, cleanup failure and the real broker hash exception type. The
CLI regression separately proves the original source argument is checked before
resolution and cannot alias the accepted tool root through a reparse point. The
retained state contains only the source SHA,
packager contract, project/region, opaque database identity hash, normalized
artifact hashes and private lifecycle marker.

This report records only TASK-135 rollout-packaging evidence. Cloud
provisioning, Secret access, migration, deployment and broker dogfood are not
part of this repository slice and have not run.

## Controlled packaging dogfood correction

After PR #157 merged as `5177611832fd8b67af8ccf5ca573eb558ec6346b`,
the first exact packaging invocation stopped safely at `ARCHIVE_UNAVAILABLE`
before approval substitution, build or cloud access. Read-only source inventory
showed the fixed archive allowlist contained `tools/__init__.py`, which does not
exist in the tracked namespace-package layout. The correction removes only that
nonexistent path and adds a direct regression requiring every allowlisted file
or directory to resolve to tracked bytes. No manual context was created and the
packager was not bypassed.
