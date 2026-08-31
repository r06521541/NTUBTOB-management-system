# TASK-172：Repository Quality and Canonical Text Hardening

## Task metadata

- type: `delivery`
- delivery_group: `task-172-repository-quality-hardening`
- acceptance_level: `L2`（CI／workflow／artifact verification）
- base: `3d26d2fee54dd60cf489f2e61fbb10aa94c4235f`
- branch: `codex/task-172-repository-quality-hardening`
- report_to: `main-work`
- owner_approved: 2026-08-31

## Scope and decisions

1. Replace the fragile broad Windows `black .` path with one repository-owned Python quality runner that checks or formats explicit Python files one at a time, enforces a bounded timeout and never silently skips a selected file.
2. Hosted CI derives Python quality coverage from the exact changed paths. New `.py` files are covered without adding them to a handwritten workflow list; docs-only changes retain the quick gate without formatter installation.
3. Pin the repository quality tool versions and centralize Black／isort configuration for Python 3.10. The runner must distinguish missing tools, timeout, required formatting, unsafe paths and subprocess failure without echoing file contents.
4. Add a canonical text digest helper with LF／CRLF equivalence and bounded checksum-manifest parsing. New checksum workflows use it; existing checksum-locked production launchers, manifests and historical artifacts remain byte-for-byte unchanged in this task.
5. Extend Git line-ending attributes only for checksum manifests and repository-owned checksum text classes. Do not renormalize unrelated source files.

## Claims

### Tooling writer

- actor_id: `/root/task170_play_evidence_writer`
- role: `codex-writer`
- claim_id: `task-172-repository-quality-writer-20260831`
- lease_version: 1
- scope: quality runner, digest helper, CI integration, focused tests and developer usage documentation
- owned_paths:
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

### CI／Tooling reviewer

- actor_id: `/root/task170_release_security_review`
- role: `advisor`
- claim_id: `task-172-ci-tooling-reviewer-20260831`
- lease_version: 1
- scope: read-only immutable-SHA review of path selection, subprocess bounds, no-skip behavior, checksum canonicalization and CI fail-safe selection
- owned_paths: none
- report_to: `main-work`

Every assignment must first acknowledge `received/executing`; report a blocker immediately; send a heartbeat after 10–15 minutes; and proactively notify Main on completion with task, branch, exact SHA or dirty paths, tests, findings, remaining limits and external mutations. The writer self-reviews and self-tests but is not the sole acceptor. The reviewer is read-only and must return `ACCEPT` or `REQUEST_CHANGES` against immutable Git blobs.

## Required outcomes

1. Changed Python files selected by CI cannot escape Black／isort merely because a workflow list was not updated.
2. One stuck file is terminated within the configured timeout and reported by path; other files are not reformatted as an accidental side effect of check mode.
3. LF and CRLF forms of the same text have one SHA-256; binary hashing remains raw bytes and is not inferred from extension.
4. Docs-only and approved quick-only changes still avoid application/database/formatter installation; unknown quality or workflow paths continue to select full CI.
5. Existing production checksum artifacts and launchers have zero content changes.

## Verification budget

- Writer: focused quality/digest/classifier/workflow tests, safe one-file Black／isort probes, compile and diff checks.
- Main: scope audit proving zero old manifest／launcher diff and complete CI job contract.
- One independent CI／Tooling targeted review on an immutable integrated SHA.
- One ready PR and one change-selected hosted full gate; merge only if green and conflict-free.

## Stop conditions

- The solution requires rewriting existing checksum manifests or production launchers.
- Changed-path selection can be ambiguous, skip an explicit Python file, execute repository content as a command, or disclose file content.
- Docs-only quick classification would begin installing quality/application dependencies.
- The runner requires network access, global tool installation or modification outside the repository.

## Non-goals

No product behavior, schema, database, provider, Secret, cloud, deployment, production operation or archive migration. Temporary off-repository Owner interaction helpers and coordination archival are handled separately by the next governance delivery.
