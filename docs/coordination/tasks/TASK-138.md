# TASK-138: Wire the private broker into staging acceptance

- Task type: implementation work package
- Delivery group: `mobile-staging-acceptance-automation`
- Operator: agent under DEC-098
- Owner gate: LINE login/consent only

## Goal

Replace TASK-129's mocked broker seam with the provisioned TASK-134 client while
preserving the harness's resumable, no-blind-retry mutation contract.

## Scope

One writer owns the acceptance harness, its direct tests, this task, one report
and the existing mobile staging runbook. The broker client/core, launcher,
Flutter source, cloud resources, Secrets, fixture schema and production are
read-only dependencies.

## Invariants

- Broker status and operations run through the accepted client as isolated,
  bounded child processes with exactly one governed JSON result.
- Opaque operation IDs are generated once and retained only in a task-private
  atomic sidecar. They never enter the public checkpoint, governed output,
  report or repository.
- The private sidecar is durable before the intent checkpoint. A mutation is
  issued at most once. Intent/result resume performs only same-ID `reconcile`;
  missing, malformed or conflicting state fails closed.
- Broker provisioning remains an explicit Owner gate. Drift, timeout, unknown
  result and malformed child output stop without mutation retry.
- Basic acceptance and all previously accepted launcher, accessibility,
  checkpoint, redaction and session-preservation behavior remain unchanged.

## Acceptance and budget

- Direct tests cover status, grant/restore, same-ID crash reconciliation,
  sidecar binding/atomicity, malformed child output and no disclosure.
- Writer runs one affected complete harness suite plus parser/diff/format.
- Domain review is targeted to broker/sidecar/no-retry boundaries; hosted CI is
  the final repository gate. Controlled staging dogfood is separate.

