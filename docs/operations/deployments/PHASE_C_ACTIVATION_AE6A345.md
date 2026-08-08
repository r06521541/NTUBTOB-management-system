# Phase C production activation work package

Status: awaiting Owner approval. This document is not proof of execution.

## Locked material artifacts

- Reviewed merged source commit: `ae6a345879f864e9826a17e4a725f6177c8eb6dc`
- Shared source fingerprint: `bd3d932b5c5dc55695d73a203ffe9efbe24405fffd356993bcf7fc53a33a2298`
- Production schema assumption: `0004_phase_c_identity_lifecycle`; no database operation is authorized.
- Offline all-off preflight: `legacy_unfrozen`, passed.
- Release manifest: `phase-c-release-manifest-v1`, canonical nine-step path validated.

## Fresh starting inventory

Collected read-only on 2026-08-08 Asia/Taipei. Every item must be re-read immediately before its first mutation; drift stops the operation.

| Unit | Current／rollback identity | Traffic／state | Runtime contract |
| --- | --- | --- | --- |
| Web Portal | `web-portal-00042-r69`; digest `sha256:a94e49b9b43a3e41a7a442f6b81eb104cea8e00ef9cff66999848dc96dbd6cc8` | Ready, exact 100%; public invoker; ingress all | Phase C false; freeze false; maintenance false |
| LINE webhook | underlying revision `line-webhook-handler-00009-fiv`; immutable source `gcf-v2-sources-556891917512-asia-east1` / `line-webhook-handler/function-source.zip` / generation `1786191169828670` | Function ACTIVE; underlying exact 100%; public invoker; ingress allow-all; Python 3.10 | Phase C false; freeze false |
| Notify cron | `notify-cronjob-service-00013-ddr`; digest `sha256:8841e04c0a9e1ed286694f0a30c1cc1a5b5e0a2380423f919c34ca7f55e68636` | Ready, exact 100%; no public invoker; ingress all | Phase C false; freeze false |

Runtime identities remain the existing configured service accounts. No IAM member list is recorded.

### Secret binding metadata only

- Web Portal: DB password `latest`; LINE Login channel secret `1`; Flask session secret `1`.
- LINE webhook: channel access token `2`; channel secret `2`; DB password `latest`; Web Portal URL `latest`.
- Notify cron: channel access token `2`; DB password `latest`.

No Secret value was read or recorded. Every deployment must preserve exactly these binding names and versions unless this work package explicitly lists otherwise; no Secret creation, rotation or version change is authorized.

### Scheduler boundary

- `GameAttendanceCount`: enabled, `0 10 * * 0,2,4`, Asia/Taipei, authenticated notify attendance endpoint.
- `WeeklyGameNotify`: enabled, `0 10 * * 3`, Asia/Taipei, authenticated future-game endpoint.
- No pause, resume, invoke, schedule or target mutation is authorized.
- Execute only while the remaining window is sufficient to finish before 09:30 Asia/Taipei on the next scheduled day. If not, stop in the last verified safe state and reschedule.

## Approved operation requested: B1 feature-off deployment

Execute one unit at a time from a clean checkout at the exact reviewed commit. Rebuild and verify the three shared artifacts before the first build.

1. Deploy Web Portal with Phase C false, freeze false, maintenance false; preserve the three exact Secret bindings. Use `web-portal-00042-r69` as the pre-deploy rollback revision. Verify image tag／digest, Ready, 100% traffic, public IAM, flags, homepage 200 and production demo 404. Observe 15 minutes.
2. Deploy LINE webhook with Phase C false and freeze false; preserve the exact four Secret bindings. Lock the current immutable source triple above as rollback. Verify Function ACTIVE, runtime Python 3.10, new immutable source, underlying Ready／100%, public IAM and flags. Do not send a fabricated LINE event. Observe 15 minutes.
3. Deploy notify cron with Phase C false and freeze false through the no-traffic wrapper; use `notify-cronjob-service-00013-ddr` as rollback. Promote only after exact SHA, digest, Ready and private IAM checks. Allow one authenticated `GET /healthz` only; do not invoke notification routes. Observe 15 minutes.
4. Observe the three-unit feature-off set together for 30 minutes before activation.

If a B1 unit fails, roll back only that unit to its locked pre-deploy revision／source, verify the original all-off state, and stop. Do not proceed to B2.

## Approved operation requested: B2 coordinated activation

At every step: re-read exact current state, ask the offline controller for the next step, mutate only the named flag on the named unit, then verify revision/source, readiness, traffic, IAM and complete flag vector. Observe 15 minutes after each mutation.

1. Web Portal freeze: `false → true`.
2. LINE webhook freeze: `false → true`.
3. Notify cron freeze: `false → true`.
4. Web Portal Phase C: `false → true` while all frozen.
5. Notify cron Phase C: `false → true` while all frozen.
6. LINE webhook Phase C: `false → true` while all frozen.
7. Web Portal freeze: `true → false`.
8. LINE webhook freeze: `true → false`.
9. Notify cron freeze: `true → false`.
10. Observe all-on／all-unfrozen／maintenance-off for 30 minutes.

The Web Portal and LINE webhook may naturally return their fixed transition response to real users during freeze. Existing Scheduler jobs may remain enabled and follow their natural schedule, but this package authorizes no artificial invocation or notification.

## Conditional rollback authority requested

Stop immediately for source／revision／flag drift, missing exact Secret binding, readiness or IAM regression, mixed-unfrozen state, startup/import error, unexpected DB access from health checks, increased 5xx, principal-resolution failure, attendance projection disagreement, duplicate audit／attendance effects, notification error, or sensitive data in logs.

First-layer rollback:

1. If maintenance is unexpectedly on, turn it off.
2. Re-enter all-frozen in the controller's reverse-safe order.
3. Turn Phase C off: LINE webhook → notify cron → Web Portal.
4. Verify all-off／all-frozen, then remove freeze in controller-approved reverse order.

Second-layer rollback, only after all-off is proven:

- Web Portal traffic to `web-portal-00042-r69=100`.
- Notify traffic to `notify-cronjob-service-00013-ddr=100`.
- LINE function source to the locked bucket／object／generation above using the existing Gen2 rollback runbook.

Rollback retains schema 0004 and all committed Person／identity／attendance／audit data. It does not authorize database downgrade, delete, repair, restore, Secret/IAM/Scheduler mutation or notification.

## Observation evidence

Record only build IDs, source identities, revisions, image digests, fixed flag classifications, readiness／traffic／IAM classification, aggregate error counts and timestamps. Do not record full env, Secret values, DB URLs, identities, Member／Person data or complete cloud responses.

## Approval boundary

Approval of this exact package authorizes B1, B2, the listed no-side-effect GET checks, natural Scheduler behavior and conditional rollback within the stated targets and stop criteria. It does not authorize maintenance enablement, database writes performed solely for testing, artificial attendance／identity／webhook／notification POSTs, Secret/IAM/Scheduler changes or other services.
