# Mobile API

Independent Flask/Cloud Run deployment unit for the Basic-only native API.
The canonical machine-readable contract is `openapi.json`.

The runtime is fail closed unless PostgreSQL reports exact revision
`0005_mobile_auth_api_foundation` and all signing, refresh-response encryption,
audience and LINE public-key configuration is present. These values are runtime
configuration only; this directory contains no credential and no deploy target.

Package the current `shared_lib-0.0.1.tar.gz` under `dist/` before an authorized
build. This task does not build, deploy, bind Secret Manager, change IAM or
connect to production.
