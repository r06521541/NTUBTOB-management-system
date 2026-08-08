# Shared Library

This is a shared library for NTUBTOB-management-system.

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
