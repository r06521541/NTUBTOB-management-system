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
