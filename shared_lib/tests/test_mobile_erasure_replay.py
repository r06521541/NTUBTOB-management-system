"""Default-off candidate/replay fencing with fictional data and no database."""

import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from shared_module.mobile_api import AccountUnavailable, IdempotencyConflict
from shared_module.portal_data import mobile_repository as module
from shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    ErasureGuardUnavailable,
)
from sqlalchemy.orm import Session, make_transient_to_detached

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


class CandidateErasureFenceTests(unittest.TestCase):
    def candidate(self, provider, row, *, enabled=True, error=None, first_login=False):
        session = MagicMock()
        session.__enter__.return_value = session
        events = []
        session.scalar.side_effect = lambda _statement: events.append("read") or row
        repo = module.MobileRepository(object(), erasure_checks_enabled=enabled)
        repo.lifecycle._thread = Mock()
        with (
            patch.object(module, "Session", return_value=session),
            patch.object(
                module,
                "acquire_admin_event_locks",
                side_effect=lambda _s: events.append("locks"),
            ),
            patch.object(module, "require_account_not_erasing") as gate,
        ):

            def check(current, **scope):
                self.assertIs(current, session)
                self.assertEqual(events, ["locks", "read"])
                self.assertEqual(
                    scope, {"person_id": row.person_id, "identity_id": row.id}
                )
                events.append("gate")
                if error is not None:
                    raise error("fictional-private-detail")

            gate.side_effect = check
            call = getattr(repo, f"ensure_{provider}_link_candidate")
            extra = {"first_login": first_login} if provider == "apple" else {}
            if error is not None:
                with self.assertRaisesRegex(
                    AccountUnavailable, "^account access unavailable$"
                ):
                    call("fictional-subject", "fictional-request", NOW, **extra)
                result = None
            else:
                result = call("fictional-subject", "fictional-request", NOW, **extra)
        return result, session, events, gate

    def test_existing_pending_and_linked_candidates_recheck_current_mapping(self):
        for provider in ("google", "apple"):
            for person_id in (None, 7, 19):
                with self.subTest(provider=provider, person_id=person_id):
                    row = SimpleNamespace(
                        id=11,
                        provider=provider,
                        person_id=person_id,
                        status="pending" if person_id is None else "linked",
                        updated_at=NOW,
                    )
                    result, session, events, gate = self.candidate(provider, row)
                    self.assertEqual(result["person_id"], person_id)
                    self.assertEqual(events, ["locks", "read", "gate"])
                    gate.assert_called_once()
                    session.add.assert_not_called()
                    session.flush.assert_not_called()

    def test_blocked_or_unavailable_candidate_never_returns_or_writes(self):
        for provider in ("google", "apple"):
            for error in (ErasureAccessBlocked, ErasureGuardUnavailable):
                with self.subTest(provider=provider, error=error):
                    row = SimpleNamespace(
                        id=11,
                        provider=provider,
                        person_id=None,
                        status="pending",
                        updated_at=NOW,
                    )
                    _, session, _, gate = self.candidate(provider, row, error=error)
                    gate.assert_called_once()
                    session.add.assert_not_called()
                    session.flush.assert_not_called()

    def test_default_off_preserves_existing_candidate_and_apple_first_login_lock(self):
        for provider, first_login in (
            ("google", False),
            ("apple", False),
            ("apple", True),
        ):
            with self.subTest(provider=provider, first_login=first_login):
                row = SimpleNamespace(
                    id=11,
                    provider=provider,
                    person_id=7,
                    status="linked",
                    updated_at=NOW,
                )
                result, _, events, gate = self.candidate(
                    provider, row, enabled=False, first_login=first_login
                )
                self.assertEqual(result["identity_id"], 11)
                self.assertEqual(events, ["locks", "read"] if first_login else ["read"])
                gate.assert_not_called()

    def test_missing_candidate_keeps_existing_creation_not_restore_suppression(self):
        for provider in ("google", "apple"):
            with self.subTest(provider=provider):
                result, session, events, gate = self.candidate(provider, None)
                self.assertEqual(result["status"], "pending")
                self.assertIsNone(result["person_id"])
                self.assertEqual(events, ["locks", "read"])
                self.assertEqual(session.add.call_count, 2)
                session.flush.assert_called_once()
                gate.assert_not_called()

    def test_existing_candidate_projection_is_inside_real_clean_transaction(self):
        for provider in ("google", "apple"):
            with self.subTest(provider=provider):
                row = module.AuthIdentityRecord(
                    id=11,
                    provider=provider,
                    provider_subject="fictional-subject",
                    person_id=7,
                    status="linked",
                    created_at=NOW,
                    updated_at=NOW,
                )
                make_transient_to_detached(row)
                session = Session()

                def read(_statement):
                    self.assertTrue(session.in_transaction())
                    session.add(row)
                    return row

                def check(current, **scope):
                    self.assertIs(current, session)
                    self.assertTrue(session.in_transaction())
                    self.assertFalse(session.new or session.dirty or session.deleted)
                    self.assertEqual(scope, {"person_id": 7, "identity_id": 11})

                with (
                    patch.object(module, "Session", return_value=session),
                    patch.object(session, "scalar", side_effect=read),
                    patch.object(
                        session, "connection", side_effect=AssertionError("NO DATABASE")
                    ),
                    patch.object(module, "acquire_admin_event_locks"),
                    patch.object(
                        module, "require_account_not_erasing", side_effect=check
                    ) as gate,
                ):
                    repo = module.MobileRepository(
                        object(), erasure_checks_enabled=True
                    )
                    result = getattr(repo, f"ensure_{provider}_link_candidate")(
                        "fictional-subject", "fictional-request", NOW
                    )
                self.assertEqual(result["identity_id"], 11)
                gate.assert_called_once()


class IdempotentErasureFenceTests(unittest.TestCase):
    def setUp(self):
        self.repo = module.MobileRepository(object(), erasure_checks_enabled=True)
        self.active = None
        self.key_locked = False
        self.sessions = []
        self.events = []
        self.block_at = set()
        self.guard_error = ErasureAccessBlocked
        self.read_rows = {}
        self.record = SimpleNamespace(
            request_hash="fictional-body",
            state="pending",
            response_status=200,
            response_body={"fictional": "saved"},
        )
        self.result = (200, {"fictional": "new"})
        self.values = dict(
            session_id="fictional-session",
            person_id=7,
            method="PUT",
            route="/fake",
            key_hash="fictional-key",
            request_hash="fictional-body",
            now=NOW,
            mutation=Mock(side_effect=lambda: self.callback(self.result)),
            reconcile=Mock(side_effect=lambda: self.callback(None)),
        )
        for target, replacement in (
            ("Session", self.new_session),
            ("acquire_admin_event_locks", self.locks),
            ("require_account_not_erasing", self.gate),
        ):
            patcher = patch.object(module, target, side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(self.repo, "_idempotency_execution_lock", self.key_lock)
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextmanager
    def key_lock(self, _values):
        self.key_locked = True
        try:
            yield
        finally:
            self.key_locked = False

    @contextmanager
    def transaction(self, index):
        self.assertIsNone(self.active)
        self.active = index
        try:
            yield
        finally:
            self.active = None

    def new_session(self, _engine):
        index = len(self.sessions) + 1
        session = MagicMock()
        session.__enter__.return_value = session
        session.begin.side_effect = lambda: self.transaction(index)
        session.scalar.side_effect = lambda _s: (
            self.events.append((index, "read"))
            or self.read_rows.get(index, self.record)
        )
        self.sessions.append(session)
        return session

    def locks(self, session):
        self.assertIs(session, self.sessions[self.active - 1])
        self.events.append((self.active, "locks"))

    def gate(self, session, **scope):
        self.assertIs(session, self.sessions[self.active - 1])
        self.assertEqual(scope, {"person_id": 7, "identity_id": None})
        self.assertEqual(
            [event for event in self.events if event[0] == self.active],
            [(self.active, "locks")],
        )
        self.events.append((self.active, "gate"))
        if self.active in self.block_at:
            raise self.guard_error("fictional-private-detail")

    def callback(self, result):
        self.assertIsNone(self.active, "account transaction held across callback")
        self.assertTrue(self.key_locked, "request execution lock was lost")
        return result

    def run_request(self):
        return self.repo.idempotent(**self.values)

    def assert_blocked(self, index):
        self.block_at = {index}
        with self.assertRaisesRegex(AccountUnavailable, "^account access unavailable$"):
            self.run_request()
        self.sessions[index - 1].scalar.assert_not_called()
        self.sessions[index - 1].add.assert_not_called()
        self.assertFalse(self.key_locked)

    def test_completed_claim_replay_blocks_before_receipt_read(self):
        self.record.state = "completed"
        self.assert_blocked(1)
        self.values["mutation"].assert_not_called()
        self.values["reconcile"].assert_not_called()

    def test_guard_unavailability_does_not_return_cached_response(self):
        self.guard_error = ErasureGuardUnavailable
        self.record.state = "completed"
        self.assert_blocked(1)
        self.values["mutation"].assert_not_called()
        self.values["reconcile"].assert_not_called()

    def test_pending_pre_callback_read_blocks_without_callbacks(self):
        self.assert_blocked(2)
        self.values["mutation"].assert_not_called()
        self.values["reconcile"].assert_not_called()

    def test_normal_finalize_blocks_after_mutation_without_new_reconciliation(self):
        self.assert_blocked(3)
        self.values["mutation"].assert_called_once()
        self.values["reconcile"].assert_called_once()
        self.assertEqual(self.record.state, "pending")
        self.assertEqual(len(self.sessions), 3)

    def test_reconciled_result_cannot_bypass_final_guard(self):
        self.values["reconcile"].side_effect = lambda: self.callback(self.result)
        self.assert_blocked(3)
        self.values["mutation"].assert_not_called()
        self.assertEqual(self.record.state, "pending")

    def test_recovery_read_blocks_before_saved_response_or_second_readback(self):
        def failed_mutation():
            self.callback(None)
            self.record.state = "completed"
            raise RuntimeError("fictional lost response")

        self.values["mutation"].side_effect = failed_mutation
        self.assert_blocked(3)
        self.values["reconcile"].assert_called_once()

    def test_recovery_finalize_rechecks_after_outside_transaction_readback(self):
        with patch.object(
            self.repo,
            "_complete_idempotency",
            side_effect=[RuntimeError("fictional"), None],
        ):
            self.values["reconcile"].side_effect = lambda: self.callback(
                None if self.values["reconcile"].call_count == 1 else self.result
            )
            self.assert_blocked(5)
        self.assertEqual(self.values["reconcile"].call_count, 2)
        self.assertEqual(self.record.state, "pending")

    def test_new_claim_is_guarded_before_insert(self):
        self.read_rows[1] = None
        self.assertEqual(self.run_request(), (*self.result, False))
        self.sessions[0].add.assert_called_once()
        claim = self.sessions[0].add.call_args.args[0]
        self.assertEqual(claim.person_id, 7)
        self.assertEqual(claim.state, "pending")
        self.assertEqual(self.events[:3], [(1, "locks"), (1, "gate"), (1, "read")])

    def test_missing_receipt_after_callback_is_not_recreated(self):
        self.read_rows.update({3: None, 4: None})
        with self.assertRaises(IdempotencyConflict):
            self.run_request()
        self.values["mutation"].assert_called_once()
        self.values["reconcile"].assert_called_once()
        self.assertTrue(all(not session.add.called for session in self.sessions))
        self.assertEqual(self.record.state, "pending")

    def test_reconciliation_success_is_finalized_only_after_fresh_gate(self):
        self.values["reconcile"].side_effect = lambda: self.callback(self.result)
        self.assertEqual(self.run_request(), (*self.result, True))
        self.values["mutation"].assert_not_called()
        self.assertEqual(self.record.state, "completed")
        self.assertEqual(sum(event == "gate" for _, event in self.events), 3)

    def test_allowed_mutation_and_reconcile_keep_callbacks_outside_account_transactions(
        self,
    ):
        self.assertEqual(self.run_request(), (*self.result, False))
        self.assertEqual(
            self.events,
            [(i, event) for i in (1, 2, 3) for event in ("locks", "gate", "read")],
        )
        self.assertEqual(self.run_request(), (*self.result, True))
        self.values["mutation"].assert_called_once()
        self.values["reconcile"].assert_called_once()

    def test_completed_receipt_still_wins_after_mutation_error_when_allowed(self):
        def failed_mutation():
            self.callback(None)
            self.record.state = "completed"
            raise RuntimeError("fictional lost response")

        self.values["mutation"].side_effect = failed_mutation
        self.assertEqual(self.run_request(), (200, {"fictional": "saved"}, True))
        self.assertEqual(sum(event == "gate" for _, event in self.events), 3)
        self.values["reconcile"].assert_called_once()

    def test_default_off_does_not_run_erasure_gate(self):
        self.repo.erasure_checks_enabled = False
        self.assertEqual(self.run_request(), (*self.result, False))
        self.assertFalse(any(event == "gate" for _, event in self.events))

    def test_default_off_preserves_existing_callback_error_reconciliation(self):
        self.repo.erasure_checks_enabled = False
        self.values["mutation"].side_effect = AccountUnavailable("fictional")
        self.values["reconcile"].side_effect = lambda: self.callback(
            None if self.values["reconcile"].call_count == 1 else self.result
        )
        self.assertEqual(self.run_request(), (*self.result, True))
        self.assertEqual(self.values["reconcile"].call_count, 2)
        self.assertFalse(any(event == "gate" for _, event in self.events))

    def test_enabled_callback_access_denial_does_not_reconcile(self):
        self.values["mutation"].side_effect = AccountUnavailable("fictional")
        with self.assertRaises(AccountUnavailable):
            self.run_request()
        self.values["reconcile"].assert_called_once()
        self.assertEqual(len(self.sessions), 2)
        self.assertEqual(self.record.state, "pending")


if __name__ == "__main__":
    unittest.main()
