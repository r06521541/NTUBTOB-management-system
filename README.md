# NTUBTOB-management-system

NTUBTOB management system

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
