"""Fixed-query PostgreSQL journal implementation."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .broker import BrokerConflict, BrokerFailure, JournalRecord

_SELECT = text(
    "SELECT operation_id, operation, target_state, inspect_fingerprint, "
    "lifecycle_state, reason_code, created_at, updated_at "
    "FROM ntubtob.staging_broker_operations WHERE operation_id=:operation_id"
)


class PostgresJournal:
    def __init__(self, engine):
        self.engine = engine

    def get(self, operation_id):
        try:
            with self.engine.connect() as connection:
                row = (
                    connection.execute(_SELECT, {"operation_id": operation_id})
                    .mappings()
                    .one_or_none()
                )
        except SQLAlchemyError:
            raise BrokerFailure("JOURNAL_UNAVAILABLE") from None
        return JournalRecord(**dict(row)) if row else None

    def create_or_get(self, operation_id, operation, target_state, inspect_fingerprint):
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.staging_broker_operations "
                        "(operation_id, operation, target_state, inspect_fingerprint, "
                        "lifecycle_state, inspected_at, created_at, updated_at) "
                        "VALUES (:operation_id, :operation, :target_state, "
                        ":inspect_fingerprint, 'inspected', timezone('utc', now()), "
                        "timezone('utc', now()), timezone('utc', now())) "
                        "ON CONFLICT (operation_id) DO NOTHING"
                    ),
                    locals(),
                )
                row = (
                    connection.execute(_SELECT, {"operation_id": operation_id})
                    .mappings()
                    .one()
                )
        except SQLAlchemyError:
            raise BrokerFailure("JOURNAL_UNAVAILABLE") from None
        record = JournalRecord(**dict(row))
        if (
            record.operation,
            record.target_state,
            record.inspect_fingerprint,
        ) != (operation, target_state, inspect_fingerprint):
            raise BrokerConflict("INTENT_CONFLICT")
        return record

    def compare_and_set(
        self, operation_id, expected_state, next_state, reason_code=None
    ):
        timestamp_column = {
            "confirmed": "confirmed_at",
            "mutation_issued": "mutation_issued_at",
            "postcheck_complete": "completed_at",
            "reconcile_required": "completed_at",
        }.get(next_state)
        if timestamp_column is None:
            raise BrokerFailure("JOURNAL_CONFLICT")
        statement = text(
            "UPDATE ntubtob.staging_broker_operations SET "
            "lifecycle_state=:next_state, reason_code=:reason_code, "
            f"{timestamp_column}=timezone('utc', now()), "
            "updated_at=timezone('utc', now()) "
            "WHERE operation_id=:operation_id AND lifecycle_state=:expected_state"
        )
        try:
            with self.engine.begin() as connection:
                changed = connection.execute(
                    statement,
                    {
                        "operation_id": operation_id,
                        "expected_state": expected_state,
                        "next_state": next_state,
                        "reason_code": reason_code,
                    },
                ).rowcount
        except SQLAlchemyError:
            raise BrokerFailure("JOURNAL_UNAVAILABLE") from None
        return changed == 1
