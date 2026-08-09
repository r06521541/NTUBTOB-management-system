# TASK-086 Cloud Run Secret reference schema correction

## Confirmed production evidence

The merged metadata fallback passed its runtime/artifact/git guard but stopped at `gcloud_metadata`. Under the Owner-approved shape-only probe, Work confirmed the exact production projection without emitting env names or values:

- the outer envelope matches `spec.template.spec.containers[0].env`;
- entries are either `{name,value}` or `{name,valueFrom}`;
- Cloud Run Secret references use `valueFrom.secretKeyRef.{key,name}`, not the parser's assumed `{secret,version}`.

## Scope

Make the smallest repository-only correction: accept the exact Cloud Run `{key,name}` Secret reference schema for unrelated entries, continue to reject unknown or extra fields, and continue to require `WEB_PORTAL_ADMIN_MEMBER_IDS` to be one unique plain `{name,value}` entry. Do not resolve, print, persist or otherwise expose either Secret reference field.

Add regressions for the confirmed schema and rejection of the obsolete assumption, mixed/extra fields and a secret-backed allowlist. Preserve all existing no-DML/no-DDL/no-launcher and cleanup boundaries.

## Delivery

After Work review, create one ready PR, require hosted CI and squash merge, then execute the fixed eight-field production read-only diagnostic once. This correction does not authorize a second bootstrap or 56-Person activation.

Base commit: `d82ac7ee728303cae34d57fcca92e6ccf1f5eac6`.
