# TASK-137 Codex report - broker client Windows PowerShell compatibility

## Result

- Replaced the unsupported Windows PowerShell 5.1 `FileInfo.Parent` lookup in
  the approved `gcloud.cmd` provenance walk with an exact full-path parent
  lookup that returns the next `FileSystemInfo` item.
- Added a direct Windows PowerShell regression using a real `FileInfo`; the
  parent remains a `DirectoryInfo` and the existing reparse-point checks still
  run on every traversed item.
- Token, HTTP, service metadata, IAM, lock, redaction and broker operation
  behavior are unchanged.

## Evidence

- Targeted regression: 1/1 passed.
- Complete broker-client suite: 26/26 passed.
- No broker request, Secret access, fixture mutation, deployment or IAM change
  was performed by this source correction.

## Runtime context

- The issue was discovered by the first provisioned read-only broker `status`
  dogfood on Windows PowerShell 5.1. Cloud broker deployment and private IAM
  had already passed independent control-plane checks; the client stopped in
  config loading before token acquisition or broker HTTP.
- After integration and hosted CI, Main Work should rerun exactly one read-only
  broker `status`. Business operations remain separately gated.
