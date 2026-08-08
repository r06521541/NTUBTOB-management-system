# Shared Library

This is a shared library for NTUBTOB-management-system.

Phase C runtime flag parsing and cross-service rollout classification live in
`shared_module/portal_data/runtime.py`. Build and copy the same current
`shared_lib-0.0.1.tar.gz` source contract to Web Portal, LINE webhook and notify
cron, then run `python -m tools.phase_c_rollout_preflight` with the explicit
planned flags before any separately approved deployment.
