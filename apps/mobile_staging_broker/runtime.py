"""Lazy privileged runtime wiring after immutable artifact attestation."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from .artifacts import load_attested_approval
from .broker import Broker, BrokerFailure, BrokerManifest

ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_ENV = {
    "candidate_approval_sha256": "BROKER_CANDIDATE_APPROVAL_SHA256",
    "project": "BROKER_PROJECT",
    "region": "BROKER_REGION",
    "service": "BROKER_SERVICE",
    "runtime_identity": "BROKER_RUNTIME_IDENTITY",
    "broker_artifact_sha256": "BROKER_ARTIFACT_SHA256",
    "operator_artifact_sha256": "BROKER_OPERATOR_ARTIFACT_SHA256",
    "image_digest": "BROKER_IMAGE_DIGEST",
    "database_secret_version": "BROKER_DATABASE_SECRET_VERSION",
    "subject_secret_version": "BROKER_SUBJECT_SECRET_VERSION",
    "database_identity_sha256": "BROKER_DATABASE_IDENTITY_SHA256",
}


class GoogleSecretAccessor:
    """Return one transient payload record without process-lifetime caching."""

    def access(self, resource):
        try:
            from google.cloud import secretmanager

            response = secretmanager.SecretManagerServiceClient().access_secret_version(
                request={"name": resource}
            )
            return (response.payload.data.decode("utf-8"),)
        except Exception:
            raise BrokerFailure("SECRET_UNAVAILABLE") from None


class LazyPostgresJournal:
    """Create one engine after the gate; its pool unavoidably retains the DSN."""

    def __init__(self, secrets, database_resource):
        self.secrets = secrets
        self.database_resource = database_resource
        self._journal = None
        self._lock = threading.Lock()

    def _get(self):
        with self._lock:
            if self._journal is None:
                records = database_url = None
                try:
                    records = self.secrets.access(self.database_resource)
                    if (
                        len(records) != 1
                        or not isinstance(records[0], str)
                        or not records[0]
                    ):
                        raise BrokerFailure("SECRET_INVALID")
                    database_url = records[0]
                    from sqlalchemy import create_engine

                    from .journal import PostgresJournal

                    self._journal = PostgresJournal(create_engine(database_url))
                except BrokerFailure:
                    raise
                except Exception:
                    raise BrokerFailure("SECRET_INVALID") from None
                finally:
                    records = database_url = None
            return self._journal

    def get(self, operation_id):
        return self._get().get(operation_id)

    def create_or_get(self, operation_id, operation, target_state, fingerprint):
        return self._get().create_or_get(
            operation_id, operation, target_state, fingerprint
        )

    def compare_and_set(
        self, operation_id, expected_state, next_state, reason_code=None
    ):
        return self._get().compare_and_set(
            operation_id, expected_state, next_state, reason_code
        )


def build_runtime():
    try:
        manifest = BrokerManifest.from_mapping(
            {field: os.environ[name] for field, name in _MANIFEST_ENV.items()}
        )
    except KeyError:
        raise BrokerFailure("CONFIG_INVALID") from None

    approval = load_attested_approval(manifest, ROOT)
    # Import the mutation adapter only after actual immutable bytes are attested.
    from .operator import Task126Operator

    secrets = GoogleSecretAccessor()
    return Broker(
        manifest,
        secrets,
        LazyPostgresJournal(secrets, manifest.database_secret_version),
        Task126Operator(approval),
    )
