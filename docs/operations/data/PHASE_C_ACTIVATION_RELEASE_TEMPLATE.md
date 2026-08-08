# Phase C activation release work package template

Status: prepared, local-only template. Filling this template or running the
local controller does not authorize deployment, flag mutation, traffic change,
Scheduler action, endpoint invocation, database access or notification.

## Required fresh evidence

Record only non-secret metadata obtained by an explicitly approved operator.
Do not paste environment payloads, Secret values, tokens, database URLs, full
cloud responses, or member/identity data.

| Item | Web Portal | LINE webhook | Notify cron |
| --- | --- | --- | --- |
| Exact reviewed source commit | `<SHA>` | `<SHA>` | `<SHA>` |
| Shared artifact source fingerprint | `<SHA256>` | `<SHA256>` | `<SHA256>` |
| Current revision/source identity | `<REVISION>` | `<GEN2_SOURCE_IDENTITY>` | `<REVISION>` |
| Approved rollback identity | `<REVISION>` | `<GEN2_SOURCE_IDENTITY>` | `<REVISION>` |
| Current traffic / readiness | `<READ_ONLY_VALUE>` | `<READ_ONLY_VALUE>` | `<READ_ONLY_VALUE>` |
| Phase C flag | `false` | `false` | `false` |
| Freeze flag | `false` | `false` | `false` |
| Maintenance flag | `false` | n/a | n/a |

Before any Stage B action, independently verify the public/private IAM boundary,
runtime identity, Secret *binding names and versions* (never values), and the
relevant Scheduler target metadata. Any missing, unknown or non-exact flag,
revision, source commit or fingerprint blocks the release.

## Required controller path

Use `tools.phase_c_transition_controller` and
`tools.phase_c_release_manifest.build_manifest` locally with complete current
and target vectors. The only normal-traffic path is:

1. all features off and unfrozen;
2. freeze Portal, webhook and notify;
3. enable Phase C Portal, notify, then webhook while all remain frozen;
4. unfreeze Portal, webhook and notify; then observe all-on/maintenance-off;
5. only later, separately approve Web Portal maintenance.

Rollback re-enters freeze before reversing Phase C in the opposite order. Do
not accept a mixed/unfrozen vector, and do not promote a scheduled Cloud Run
revision until image digest, Ready state, private boundary, approved SHA and
runtime contract have all been verified.

## Observation and stop authority

Name an operator and observer, use 15 minutes after every approved mutation and
30 minutes for all-on/maintenance-off. Stop immediately for revision/flag drift,
readiness or private-boundary failure, unexpected attendance/identity effect,
or notification error. Scheduler pause/resume and any smoke that writes or
notifies require separate Owner approval.
