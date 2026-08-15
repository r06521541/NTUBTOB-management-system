# NTUBTOB-management-system

NTUBTOB management system

專案現況、協作文件、產品規劃與部署紀錄的入口見
[`docs/README.md`](docs/README.md)。目前任務與下一位角色以
[`docs/coordination/HANDOFF.yaml`](docs/coordination/HANDOFF.yaml) 為唯一真實來源。

## Setup Instructions

Before you start developing locally, make sure to complete the following steps:

1. **Install Required Python Packages**:

   ```sh
   pip3 install -r requirements.txt
   ```

2. **Build and Install the Shared Library**:

   ```sh
   make build-and-install-shared-lib
   ```

## Development Notes

- **Shared Library Changes**:
  If you make any changes to the shared library, remember to rebuild it and reinstall the dependencies by running:

  ```sh
  make build-and-install-shared-lib
  ```

- **Cloud Function Deployment**:
  After adding a new cloud function, add a corresponding deployment script in `makes/deploy.mk`.

- **Code Formatting**:
  Run the following command to format your code before committing:

  ```sh
  make format
  ```

## Local Person and Event persistence

The opt-in Person/access/qualification/Event data foundation runs against an
isolated Docker PostgreSQL database. It is not connected to the Web Portal
request path and rejects non-local database URLs. Setup, migration rehearsal,
tests, and cleanup are documented in
[`docs/development/LOCAL_PORTAL_DATA.md`](docs/development/LOCAL_PORTAL_DATA.md).

## Web Portal deployment preflight

The cross-platform Web Portal wrapper defaults to repository-local preflight.
It does not call `gcloud`, make an HTTP request, or deploy anything:

```sh
python tools/deploy_web_portal.py
```

On Windows, when `python` is not an alias for Python 3.10, use:

```powershell
py -3.10 tools/deploy_web_portal.py
```

The production execution path is fail closed and requires all of the following:
an exact approved 40-character commit, an exact `web-portal-*` rollback
revision, and the three approved LINE Login, session, and weather Secret
`resource:version` references, plus the exact approved Phase C, rollout-freeze,
and identity-maintenance boolean vector. Its
existence does not authorize a deployment. Do not use `--execute` without the
Owner's exact deployment work package and the checks in
`docs/operations/DEPLOYMENT_RUNBOOK.md`.

## Scheduled service deployment preflight

The two private scheduled services use Git commit SHAs as immutable image tags.
The cross-platform deployment helper is safe by default: without `--execute` it
only checks the local repository and does not invoke `gcloud`.

Windows (Python Launcher):

```powershell
py -3.10 tools/deploy_scheduled_service.py game-broadcast-service
py -3.10 tools/deploy_scheduled_service.py notify-cronjob-service
```

Unix-like systems:

```sh
python3 tools/deploy_scheduled_service.py game-broadcast-service
python3 tools/deploy_scheduled_service.py notify-cronjob-service
```

Production execution is intentionally not a general developer command. It must
follow `docs/operations/DEPLOYMENT_RUNBOOK.md` and requires Owner approval of an
exact 40-character commit, target service, and rollback revision. Do not add
`--execute` merely to make preflight pass.
