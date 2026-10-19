"""Explicit local evidence reconciliation; never retries a provider effect.

Trusted inspect_outcome must verify existing, exact-item provider evidence without
network I/O, DB mutation or commit. Absence, inference from a deleted credential,
and operator belief are not proof. No runtime adapter enables this coordinator.
It neither completes erasure nor clears the job's needs_attention state.
"""

import hmac
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..mobile_api import utc_now
from . import erasure_provider_execution as execution


@dataclass(frozen=True, repr=False)
class ProviderOutcomeEvidence:
    binding_hash: str
    scope_hash: str
    expected_generation: str
    result: str


class ProviderErasureReconciler:
    def __init__(self, engine, inspect_outcome, *, clock=utc_now):
        if (
            not isinstance(engine, Engine)
            or not callable(inspect_outcome)
            or not callable(clock)
        ):
            raise ValueError("invalid_reconciler_configuration")
        self.engine, self.inspect_outcome, self.clock = engine, inspect_outcome, clock

    def reconcile(self, *, job_id, item_id):
        stage, known_result = "input", None
        try:
            execution._uuid(job_id)
            execution._uuid(item_id)
            stage = "reconciliation"
            with execution.Session(self.engine) as session, session.begin():
                connection = execution._connection(session)
                job, item = execution._locked(connection, job_id, item_id)
                if job["irreversible_started_at"] is None:
                    raise execution._Rejected("dispatch_fence_missing")
                # No current live target requirement: subsequent erasure may have
                # removed it. Immutable item/job scope binds the earlier effect.
                history = (
                    connection.execute(
                        text(
                            "SELECT event_sequence,event_kind,result_code FROM "
                            "ntubtob.account_erasure_item_events WHERE item_id=:id "
                            "ORDER BY event_sequence"
                        ),
                        {"id": item_id},
                    )
                    .mappings()
                    .all()
                )
                states = [
                    tuple(
                        row[key]
                        for key in ("event_sequence", "event_kind", "result_code")
                    )
                    for row in history
                ]
                if states not in (
                    [(1, "started", "in_progress")],
                    [(1, "started", "in_progress"), (2, "unknown", "response_unknown")],
                ):
                    raise execution._Rejected("item_not_uncertain")
                evidence = self.inspect_outcome(connection, job, item)
                if (
                    type(evidence) is not ProviderOutcomeEvidence
                    or not execution._hash(evidence.binding_hash)
                    or not execution._hash(evidence.scope_hash)
                    or not hmac.compare_digest(
                        evidence.binding_hash, item["binding_hash"]
                    )
                    or not hmac.compare_digest(evidence.scope_hash, job["scope_hash"])
                    or evidence.expected_generation != str(job["expected_generation"])
                    or type(evidence.result) is not str
                    or evidence.result not in execution.ProviderErasureExecutor.RESULTS
                ):
                    raise execution._Rejected("evidence_not_verified")
                known_result = evidence.result
                now = execution._time(self.clock())
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events "
                        "(item_id,event_sequence,event_kind,result_code,occurred_at) "
                        "VALUES (:id,:sequence,'confirmed',:result,:now)"
                    ),
                    dict(
                        id=item_id,
                        sequence=len(states) + 1,
                        result=known_result,
                        now=now,
                    ),
                )
                stage = "reconciliation_commit"
        except execution._Rejected as error:
            return execution.ProviderExecutionResult(
                "unresolved", stage, str(error), known_result
            )
        except Exception:
            return execution.ProviderExecutionResult(
                "outcome_unknown",
                stage,
                (
                    "evidence_commit_unconfirmed"
                    if stage == "reconciliation_commit"
                    else "reconciliation_unavailable"
                ),
                known_result,
            )
        return execution.ProviderExecutionResult(
            "confirmed", stage, "evidence_recorded", known_result, "next_item"
        )
