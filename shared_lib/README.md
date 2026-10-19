# Shared Library

This is a shared library for NTUBTOB-management-system.

TASK203 candidate0020 additionally supports explicit `intake_enabled=True` in
`build_erasure_components` (default false). Intent receipt precedes human review;
dedicated fresh proof blocks access, then internal `materialize` atomically freezes
the existing execution job/plan after trusted review. UUID, receipt and original
policy deadlines are preserved. Materialization is not provider dispatch or runtime
activation; normal bootstrap still injects no erasure service. Existing jobs keep
their original path. Any acknowledged intake prevents downgrade to older writers.

`PORTAL_DATA_ERASURE_CHECKS_ENABLED` controls account-erasure access guards only.
Missing or exact `false` disables them; exact `true` enables them. Any other value
rejects configuration. Web/LINE/cron require Phase C when checks are enabled;
the independent Mobile API uses the same parser without that Phase C dependency.
Nested repositories retain the same policy. This does not enable account-erasure
routes, approve a job, configure custody, or authorize a deployment. A coordinated
rollout must cover every account-data writer before any real verification/erasure.

Phase C runtime flag parsing and cross-service rollout classification live in
`shared_module/portal_data/runtime.py`. Build and copy the same current
`shared_lib-0.0.1.tar.gz` source contract to Web Portal, LINE webhook and notify
cron, then run `python -m tools.phase_c_rollout_preflight` with the explicit
planned flags before any separately approved deployment.

The same runtime owns the exact `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED` parser and
cross-service transition classifier. Mixed Phase C is safe only while every
rollout service is frozen. `tools.phase_c_transition_controller` encodes the one
offline forward/rollback order and has no shell, cloud, database or network
mutation capability.
