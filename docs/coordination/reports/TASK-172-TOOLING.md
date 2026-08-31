# TASK-172 Repository Quality writer report

- actor: `/root/task170_play_evidence_writer`
- claim: `task-172-repository-quality-writer-20260831` / lease 1
- branch: `codex/task-172-repository-quality-hardening`
- base/head at assignment: `41db11b71e943e4689d5fd1aa0c3d49f46c4af2c`
- state: ready for Main integration review; not committed

## Delivered

1. `tools.repository_quality` selects explicit, tracked, or exact-Git-range Python paths. Git selection is NUL-delimited,
   no-renames, excludes deleted paths, requires exact nonzero SHAs, and rejects missing, non-`.py`, absolute, traversal, control-character
   and repository-escaping explicit paths. File count, Git output and Git execution are bounded.
2. Pinned isort 5.13.2 and Black 24.4.2 run through isolated Python `-I -m` argv with `shell=False`, captured output and a bounded
   per-file timeout. Check mode never writes. Every selected file reaches both tools even after another file/tool fails; reports contain
   only fixed failure classes and safe repository paths, never formatter diffs or file content.
3. `requirements-quality.txt` and `pyproject.toml` centralize the Python 3.10 quality toolchain. `make quality` and `make format` now use
   the per-file runner instead of broad `isort .` / `black .` invocations.
4. CI adds a changed-Python quality job using the classifier's resolved base/head SHAs, with PR merge-base parity and a last-commit
   manual-dispatch fallback. It installs only pinned quality dependencies. Docs-only and approved quick-only changes skip the job and
   install no formatter; all other classifications require its success in the final gate. The old handwritten portal-data Black list
   was removed, so added `.py` files cannot escape by omission from a workflow list.
5. `tools.artifact_digest` provides explicit canonical-text versus raw-binary SHA-256. Text streaming handles CRLF split across chunk
   boundaries; binary bytes are unchanged and mode is never inferred from extension. The bounded ASCII manifest parser requires
   lowercase SHA-256, two-space separators, safe normalized relative names, unique case-insensitive names, and bounded size/count.
6. Git attributes now fix `*.sha256`, checksum-owned SQL, production launcher and portal-data operator text classes to LF. No
   renormalization or content change was made to existing checksum-locked launchers, manifests, SQL, binary APK or gcloud artifacts.

## Verification

- `py -3.10 -m unittest tools.tests.test_repository_quality tools.tests.test_artifact_digest tools.tests.test_ci_change_classifier
  tools.tests.test_ci_workflow_contract -v`: PASS, 45 tests run / 44 passed / 1 environment skip. The skipped test executes the final
  Bash aggregate script; installed Git Bash could not create its signal pipe on this Windows host. Static workflow/final-gate contracts
  passed, and hosted Linux remains the executable YAML/Bash authority.
- `py -3.10 -m py_compile ...`: PASS for all seven changed Python modules/tests.
- Same-version isort API then Black API applied to the seven changed Python files; final checks: `ISORT_API_OK`, `BLACK_API_OK`.
- Safe real runner probe, `... repository_quality check --paths tools/artifact_digest.py --timeout-seconds 2`: expected fail-closed
  `timeout: black`, exit 1, with no formatter/source output and `NO_PYTHON_PROCESSES` afterward. The Windows Black CLI hang did not
  prevent deterministic API formatting evidence; hosted Linux must prove the real successful subprocess path.
- Artifact CLI: canonical text and explicit binary digest commands succeeded; the existing nine-entry TASK-164 manifest parsed
  successfully. Unit tests prove LF/CRLF equivalence, raw-binary inequality, cross-chunk CRLF, and malformed/unsafe/oversized rejection.
- `git check-attr text eol -- ...`: representative manifest, SQL and launcher all resolve to `text set` / `eol lf`.
- `git diff --name-only HEAD -- <all existing checksum manifests and locked text classes>`: empty. Existing locked artifacts are
  byte-for-byte unchanged.
- `git diff --check`: PASS; Windows LF-to-CRLF working-copy notices only.

## Self-review findings

- Tool subprocesses use fixed installed module names and isolated Python, never a selected repository path as executable or shell text.
- Changed-path selection filters deletion in Git itself, but still fails if any selected `.py` is missing by execution time. Renames are
  represented as delete/add, so the destination is checked and the deleted source is excluded.
- A formatter timeout or nonzero result does not expose captured stdout/stderr and does not stop checks for later selected files.
- Quality-related workflow, classifier, config and unknown paths remain fail-safe `full`; no general tooling path was added to the
  quick allowlist.
- The helper is intentionally not wired into the 32 existing manifests or duplicated production verifiers in this task. New checksum
  workflows can adopt it without changing previously approved bytes or confusing raw binary hashes with canonical text hashes.

## Remaining limits

- Local PyYAML/actionlint was unavailable, and Git Bash could not start; workflow syntax/executable shell behavior requires hosted CI.
- The local Black CLI reproducibly timed out even for one file. Timeout termination and sanitized reporting were observed, while a
  successful real CLI path remains hosted evidence; formatter API checks passed locally with the exact pinned versions.
- No network, global install, application dependency install, provider, Secret, cloud, database, runtime, production, deployment,
  artifact rewrite, commit, push or PR operation occurred.

## Exact changed paths

- `.gitattributes`
- `.github/workflows/python-tests.yml`
- `makes/dev.mk`
- `pyproject.toml`
- `requirements-quality.txt`
- `tools/repository_quality.py`
- `tools/artifact_digest.py`
- `tools/ci_change_classifier.py`
- `tools/tests/test_repository_quality.py`
- `tools/tests/test_artifact_digest.py`
- `tools/tests/test_ci_change_classifier.py`
- `tools/tests/test_ci_workflow_contract.py`
- `docs/development/AGENT_ENVIRONMENT.md`
- `docs/coordination/reports/TASK-172-TOOLING.md`
