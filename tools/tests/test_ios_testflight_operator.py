import io
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools import ios_testflight_operator as operator
from tools import ios_testflight_owner as owner
from tools.tests import test_ios_testflight_hosted as hosted_fixtures
from tools.tests import test_ios_testflight_staging as staging_fixtures


class OperatorTests(unittest.TestCase):
    def test_unresolved_output_always_directs_readonly_review(self):
        for reason in (
            "OPERATION_UNRESOLVED",
            "RETENTION_UNRESOLVED",
            "private-sentinel",
        ):
            with (
                self.subTest(reason=reason),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                result = operator.emit(reason)
                self.assertEqual(result["next_action"], "READ_ONLY_REVIEW")
                self.assertFalse(result["retry_authorized"])
                self.assertNotIn("private-sentinel", output.getvalue())

    def test_real_recovery_chain_keeps_failure_and_known_effect_state(self):
        from tools.tests.test_ios_testflight_journal import JournalTests

        for cancel_code, record_error, close_error, legacy in (
            (202, False, False, False),
            (503, False, False, False),
            (202, True, False, False),
            (202, False, True, False),
            (202, False, False, True),
        ):
            with self.subTest(
                cancel_code=cancel_code,
                record_error=record_error,
                close_error=close_error,
                legacy=legacy,
            ):
                helper = JournalTests()
                native = helper.fake()
                journal = helper.opening(native)
                start = helper.start()
                journal.record("START", **start)
                journal.record("DISPATCH_ATTEMPT")
                journal.record(
                    "DISPATCH_CONFIRMED", run_id=123, workflow_id=7, environment_id=8
                )
                first = {
                    "stage": "awaiting_job",
                    "check": "run_binding",
                    "reason": "CHECK_REJECTED",
                }
                if legacy:
                    first = {
                        "stage": "recovery",
                        "check": "unexpected",
                        "reason": "LEGACY_REASON_UNAVAILABLE",
                    }
                    journal.record(
                        "RESULT",
                        classification="UNRESOLVED",
                        cleanup_verified=False,
                        secret_absence_verified=False,
                        owner_distribution_verified=False,
                    )
                else:
                    journal.record("FAILURE", **first)
                original_bytes = native.data
                cancelled = False
                api = Mock()

                def call(method, path, body=None):
                    nonlocal cancelled
                    prefix = operator.dispatch.API + "/actions/runs/123"
                    if method == "POST" and path == prefix + "/cancel":
                        cancelled = True
                        return cancel_code, {"message": "private-sentinel"}
                    self.assertEqual(method, "GET")
                    status = "completed" if cancelled else "waiting"
                    if path == prefix:
                        return 200, {
                            "id": 123,
                            "workflow_id": 7,
                            "path": ".github/workflows/" + operator.wire.WORKFLOW,
                            "event": "workflow_dispatch",
                            "head_branch": "main",
                            "head_sha": start["sha"],
                            "run_attempt": 1,
                            "display_title": "ios-tf-" + start["nonce"],
                            "repository": {"full_name": operator.wire.REPO},
                            "status": status,
                            "conclusion": "cancelled" if cancelled else None,
                        }
                    self.assertEqual(path, prefix + "/attempts/1/jobs?per_page=100")
                    return 200, {
                        "total_count": 1,
                        "jobs": [
                            {
                                "id": 456,
                                "name": "owner_testflight",
                                "run_id": 123,
                                "head_sha": start["sha"],
                                "status": status,
                                "conclusion": "cancelled" if cancelled else None,
                            }
                        ],
                    }

                api.call.side_effect = call
                factory = Mock(return_value=journal)
                asc = Mock(side_effect=AssertionError("private input forbidden"))
                record = operator.result_record
                close = journal.close

                def finish(*args, **kwargs):
                    if record_error:
                        raise OSError("private-sentinel")
                    return record(*args, **kwargs)

                def closing():
                    close()
                    if close_error:
                        raise OSError("private-sentinel")

                with (
                    patch.object(
                        operator.dispatch.primitives, "GitHub", return_value=api
                    ),
                    patch.object(operator, "result_record", side_effect=finish),
                    patch.object(journal, "close", side_effect=closing),
                    patch("sys.stdout", new_callable=io.StringIO) as output,
                ):
                    result = operator.recover_operation(
                        journal_factory=factory, asc_input=asc
                    )
                self.assertEqual(json.loads(output.getvalue()), result)
                self.assertEqual(result["run_id"], 123)
                self.assertEqual(result["failure"], first)
                self.assertEqual(result["next_action"], "READ_ONLY_REVIEW")
                damaged = record_error or close_error
                self.assertEqual(
                    result["external_write_state"],
                    "UNKNOWN" if damaged or cancel_code != 202 else "ATTEMPTED",
                )
                self.assertEqual(
                    result["secret_transfer_state"],
                    "UNRESOLVED" if damaged else "NOT_ATTEMPTED",
                )
                if cancel_code != 202:
                    self.assertEqual(
                        result["cleanup_failure"],
                        {
                            "stage": "cancel",
                            "check": "cancel_result",
                            "reason": "HTTP_SERVER_ERROR",
                        },
                    )
                else:
                    self.assertEqual(result["cleanup_failure"] is not None, damaged)
                self.assertFalse(result["retry_authorized"])
                self.assertFalse(result["secret_absence_verified"])
                self.assertNotIn("private-sentinel", output.getvalue())
                self.assertNotIn(start["nonce"], output.getvalue())
                asc.assert_not_called()
                factory.assert_called_once_with(create=False)
                self.assertTrue(native.data.startswith(original_bytes))
                self.assertEqual(
                    [c.args[0] for c in api.call.call_args_list if c.args[0] != "GET"],
                    ["POST"],
                )

    def test_unsent_cli_modes_are_explicit_and_preserve_source_gate(self):
        staging, _, _, _ = self.fixture()
        for args in (["--check-unsent"], ["--execute-unsent", "--settings"]):
            with (
                patch.object(
                    operator, "preflight", return_value=("c" * 40, staging)
                ) as preflight,
                patch.object(operator, "check_unsent") as check,
                patch.object(
                    operator,
                    "execute_unsent",
                    return_value={"classification": "BUILD_PENDING"},
                ) as run,
                patch.object(operator, "metadata") as metadata,
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                operator.main(args)
            preflight.assert_called_once_with(recovery_only=False)
            metadata.assert_not_called()
            if args == ["--check-unsent"]:
                check.assert_called_once_with("c" * 40)
                run.assert_not_called()
            else:
                check.assert_not_called()
                run.assert_called_once_with("c" * 40, staging)
        with (
            patch.object(operator, "preflight") as preflight,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            self.assertEqual(operator.main(["--execute-unsent"]), 2)
        preflight.assert_not_called()

    def test_successor_unacknowledged_append_never_begins_or_finalizes(self):
        from tools.tests.test_ios_testflight_journal import JournalTests

        staging, config, materials, target = self.fixture()
        helper = JournalTests()
        value, native = helper.stopped()
        before = native.data
        proof = Mock()
        proof.consume.return_value = value.unsent_snapshot()["digest"]
        native.flush.return_value = False
        session = Mock(nonce="d" * 64, issued=200, run_id=None)
        session.public.return_value = {"failure": None}
        lookup = Mock()
        lookup.inventory.return_value = target
        with (
            patch.object(operator, "finalize_session") as finalize,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            result = operator.execute(
                "c" * 40,
                staging,
                config,
                "owner@example.invalid",
                collect=Mock(return_value=materials),
                owner_factory=Mock(return_value=lookup),
                session_factory=Mock(return_value=session),
                successor_journal=value,
                unsent_verify=Mock(return_value=proof),
            )
        self.assertEqual(result["classification"], "JOURNAL_REJECTED")
        self.assertEqual(result["failure"]["stage"], "journal_start")
        self.assertEqual(result["external_write_state"], "UNKNOWN")
        self.assertTrue(native.data.startswith(before))
        self.assertEqual(
            [r["event"] for r in operator.journal_module.parse(native.data)[0]],
            ["START", "RESULT", "UNSENT_SUCCESSOR"],
        )
        session.begin.assert_not_called()
        finalize.assert_not_called()
        self.assertEqual(session.signing, b"")
        reopened = helper.opening(helper.fake(native.data), create=False)
        with self.assertRaises(operator.journal_module.Rejected):
            reopened.unsent_snapshot()
        reopened.close()

    def test_successor_pretransition_faults_never_append_or_cleanup(self):
        from tools.tests.test_ios_testflight_journal import JournalTests

        staging, config, materials, target = self.fixture()
        for point in (
            "initial_proof",
            "collect",
            "inventory",
            "frames",
            "final_proof",
            "consume",
        ):
            with self.subTest(point=point):
                journal, native = JournalTests().stopped()
                before = native.data
                session = Mock(nonce="d" * 64, issued=200, run_id=None)
                session.public.return_value = {"failure": None}
                proof = Mock()
                proof.consume.return_value = journal.unsent_snapshot()["digest"]
                verifier = Mock(return_value=proof)
                collect = Mock(return_value=materials)
                lookup = Mock()
                lookup.inventory.return_value = target
                frames = Mock(return_value=(b"fictional-sign", b"fictional-asc"))
                error = operator.unsent.Rejected("UNSENT_PROOF_EXPIRED")
                if point == "final_proof":
                    verifier.side_effect = [proof, error]
                else:
                    {
                        "initial_proof": verifier,
                        "collect": collect,
                        "inventory": lookup.inventory,
                        "frames": frames,
                        "consume": proof.consume,
                    }[point].side_effect = error
                with (
                    patch.object(operator, "frames", frames),
                    patch.object(operator, "finalize_session") as finalize,
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    result = operator.execute(
                        "c" * 40,
                        staging,
                        config,
                        "owner@example.invalid",
                        collect=collect,
                        owner_factory=Mock(return_value=lookup),
                        session_factory=Mock(return_value=session),
                        successor_journal=journal,
                        unsent_verify=verifier,
                    )
                self.assertEqual(result["classification"], "UNSENT_PROOF_EXPIRED")
                self.assertEqual(native.data, before)
                session.begin.assert_not_called()
                finalize.assert_not_called()
                if point in {"final_proof", "consume"}:
                    self.assertEqual(session.signing, b"")
                    self.assertEqual(session.asc, b"")

    def test_successor_execution_keeps_old_prefix_and_new_failure(self):
        from tools.tests.test_ios_testflight_journal import JournalTests

        staging, config, materials, target = self.fixture()
        helper = JournalTests()
        native = helper.fake()
        journal = helper.opening(native)
        journal.record("START", **helper.start())
        old = operator.diagnostics.failure(
            "journal_start", "journal_write", "JOURNAL_REJECTED"
        )
        journal.record("FAILURE", **old)
        journal.record(
            "RESULT",
            classification="UNRESOLVED",
            cleanup_verified=False,
            secret_absence_verified=True,
            owner_distribution_verified=False,
        )
        before = native.data
        proof = Mock()
        proof.consume.return_value = journal.unsent_snapshot()["digest"]
        verifier = Mock(return_value=proof)
        session = Mock(nonce="d" * 64, issued=200, run_id=None)
        new = operator.diagnostics.failure(
            "dispatch_preflight", "main_head", "CHECK_REJECTED"
        )
        state = dict(
            failure=new,
            current_absence_verified=False,
            retention_resolved=True,
            external_write_state="NOT_ATTEMPTED",
            secret_transfer_state="NOT_ATTEMPTED",
        )
        session.public.return_value = state

        def begin():
            self.assertEqual(journal.events[-1]["event"], "UNSENT_SUCCESSOR")
            self.assertEqual(verifier.call_count, 2)
            proof.consume.assert_called_once_with(journal, "c" * 40)
            return {"status": "STOP"}

        session.begin.side_effect = begin
        lookup = Mock()
        lookup.inventory.return_value = target
        with (
            patch.object(operator, "finalize_session", return_value=state),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            result = operator.execute(
                "c" * 40,
                staging,
                config,
                "owner@example.invalid",
                collect=Mock(return_value=materials),
                owner_factory=Mock(return_value=lookup),
                session_factory=Mock(return_value=session),
                successor_journal=journal,
                unsent_verify=verifier,
            )
        self.assertEqual(result["failure"], new)
        self.assertTrue(native.data.startswith(before))
        physical, intact = operator.journal_module.parse(native.data)
        self.assertTrue(intact)
        self.assertEqual(
            [r["event"] for r in physical],
            ["START", "FAILURE", "RESULT", "UNSENT_SUCCESSOR", "FAILURE", "RESULT"],
        )
        self.assertEqual(physical[1]["data"], old)
        self.assertEqual(physical[4]["data"], new)

    def test_unsent_check_has_no_private_input_or_writes(self):
        value = Mock(intact=True)
        verify = Mock()
        with (
            patch.object(
                operator.journal_module.Journal, "open", return_value=value
            ) as opening,
            patch.object(operator.unsent, "verify", verify),
            patch.object(operator, "settings_metadata") as saved,
            patch.object(operator, "asc_preflight") as asc,
            patch.object(operator, "execute") as execute,
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            result = operator.check_unsent("c" * 40)
        opening.assert_called_once_with(create=False, readonly=True)
        verify.assert_called_once_with(value, "c" * 40)
        self.assertEqual(result["classification"], "UNSENT_READY")
        self.assertFalse(result["retry_authorized"])
        for blocked in (saved, asc, execute, value.record):
            blocked.assert_not_called()
        value.close.assert_called_once()
        self.assertNotIn("c" * 40, output.getvalue())

    def test_unsent_exclusive_preparation_stops_before_private_input(self):
        staging, config, _, _ = self.fixture()
        for point in ("proof", "settings", "asc", "complete"):
            with self.subTest(point=point):
                value = Mock(intact=True)
                verify = Mock()
                saved = Mock(return_value=(config, "owner@example.invalid"))
                asc = Mock()
                execute = Mock(return_value={"classification": "BUILD_PENDING"})
                if point != "complete":
                    {"proof": verify, "settings": saved, "asc": asc}[
                        point
                    ].side_effect = operator.unsent.Rejected("UNSENT_REMOTE_REJECTED")
                with (
                    patch.object(
                        operator.journal_module.Journal, "open", return_value=value
                    ) as opening,
                    patch.object(operator.unsent, "verify", verify),
                    patch.object(operator, "settings_metadata", saved),
                    patch.object(operator, "asc_preflight", asc),
                    patch.object(operator, "execute", execute),
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    if point == "complete":
                        operator.execute_unsent("c" * 40, staging)
                    else:
                        with self.assertRaises(operator.Rejected):
                            operator.execute_unsent("c" * 40, staging)
                opening.assert_called_once_with(create=False)
                value.record.assert_not_called()
                if point == "proof":
                    saved.assert_not_called()
                    asc.assert_not_called()
                if point != "complete":
                    execute.assert_not_called()
                    value.close.assert_called_once()
                else:
                    execute.assert_called_once_with(
                        "c" * 40,
                        staging,
                        config,
                        "owner@example.invalid",
                        successor_journal=value,
                    )
                    value.close.assert_not_called()  # delegated execute owns close

    def setUp(self):
        # Every test uses fictional custody; never inspect the Owner journal.
        guard = patch.object(
            operator.journal_module,
            "new_operation_preflight",
            return_value="READY_NO_JOURNAL",
        )
        self.journal_guard = guard.start()
        self.addCleanup(guard.stop)

    def test_existing_operation_blocks_direct_and_cli_before_private_input(self):
        staging, config, _, _ = self.fixture()
        self.journal_guard.return_value = "EXISTING_OPERATION"
        with (
            patch.object(operator, "preflight", return_value=("a" * 40, staging)),
            patch.object(operator, "metadata") as metadata,
            patch.object(operator, "settings_metadata") as saved,
            patch.object(operator, "asc_preflight") as asc,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            self.assertEqual(operator.main(["--execute", "--settings"]), 2)
            collect, journal, session = Mock(), Mock(), Mock()
            result = operator.execute(
                "a" * 40,
                staging,
                config,
                "owner@example.invalid",
                collect=collect,
                journal_factory=journal,
                session_factory=session,
            )
        for blocked in (metadata, saved, asc, collect, journal, session):
            blocked.assert_not_called()
        self.assertEqual(result["classification"], "EXISTING_OPERATION")
        self.assertEqual(result["failure"]["check"], "existing_journal")
        self.assertEqual(result["external_write_state"], "UNKNOWN")

    def test_status_is_source_and_readonly_journal_only(self):
        from tools.tests.test_ios_testflight_journal import JournalTests

        raw = operator.journal_module.encode_event([], "START", JournalTests().start())
        events, _ = operator.journal_module.parse(raw)
        value = Mock(intact=True, events=events)
        with (
            patch.object(
                operator, "preflight", return_value=("c" * 40, None)
            ) as preflight,
            patch.object(
                operator.journal_module.Journal, "open", return_value=value
            ) as opening,
            patch.object(operator, "settings_metadata") as settings,
            patch.object(operator, "asc_preflight") as asc,
            patch.object(operator, "recover_operation") as recovery,
            patch.object(operator.intake, "collect_upload") as collect,
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(operator.main(["--status"]), 0)
        preflight.assert_called_once_with(recovery_only=True)
        opening.assert_called_once_with(create=False, readonly=True)
        value.record.assert_not_called()
        value.close.assert_called_once()
        for blocked in (settings, asc, recovery, collect, self.journal_guard):
            blocked.assert_not_called()
        self.assertIn("LEGACY_REASON_UNAVAILABLE", output.getvalue())
        self.assertNotIn("nonce", output.getvalue())
        self.assertNotIn("c" * 40, output.getvalue())

    def test_first_dispatch_failure_survives_cleanup_and_journal_faults(self):
        staging, config, materials, target = self.fixture()
        first = dict(
            stage="dispatch_preflight", check="unexpected", reason="CHECK_REJECTED"
        )
        for fault in ("cleanup", "journal", "interrupt"):
            session = Mock(
                nonce="b" * 64, issued=100, run_id=None, job_status="UNKNOWN"
            )
            session.begin.return_value = {"status": "STOP", "failure": first}
            session.public.return_value = {
                "failure": first,
                "current_absence_verified": False,
                "retention_resolved": True,
                "external_write_state": "NOT_ATTEMPTED",
                "secret_transfer_state": "NOT_ATTEMPTED",
            }
            journal = Mock(intact=True, events=[])
            lookup = Mock()
            lookup.inventory.return_value = target
            final = Mock(return_value=session.public.return_value)
            if fault == "cleanup":
                final.side_effect = RuntimeError("private-sentinel")
            elif fault == "interrupt":
                session.begin.side_effect = KeyboardInterrupt()
            else:

                def record(event, **data):
                    if event == "FAILURE":
                        raise RuntimeError("private-sentinel")

                journal.record.side_effect = record
            with (
                patch.object(operator, "finalize_session", final),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                result = operator.execute(
                    "a" * 40,
                    staging,
                    config,
                    "owner@example.invalid",
                    collect=Mock(return_value=materials),
                    journal_factory=Mock(return_value=journal),
                    session_factory=Mock(return_value=session),
                    owner_factory=Mock(return_value=lookup),
                )
            self.assertEqual(result["failure"], first)
            self.assertNotIn("private-sentinel", output.getvalue())
            self.assertFalse(result["secret_absence_verified"])
            if fault != "interrupt":
                self.assertIsNotNone(result["cleanup_failure"])
            final.assert_called_once()
            journal.close.assert_called_once()

    def test_each_execution_boundary_has_safe_failure_location(self):
        staging, config, materials, target = self.fixture()
        cases = (
            ("collect", "signing_input", "signing_material"),
            ("inventory", "asc_preflight", "asc_scope"),
            ("frames", "frame_validation", "frames"),
            ("open", "journal_open", "journal_path"),
            ("start", "journal_start", "journal_write"),
            ("begin", "dispatch_preflight", "dispatch_result"),
            ("advance", "awaiting_job", "job_status"),
            ("settle", "observe_run", "job_status"),
            ("artifact", "artifact_verification", "artifact"),
            ("apple", "apple_reconcile", "apple_result"),
        )
        for point, stage, check in cases:
            with self.subTest(point=point):
                fault = RuntimeError("private-sentinel password token")
                journal = Mock(intact=True, events=[])
                state = {
                    "current_absence_verified": False,
                    "retention_resolved": True,
                    "cancel_unresolved": False,
                    "failure": None,
                    "external_write_state": "NOT_ATTEMPTED",
                    "secret_transfer_state": "NOT_ATTEMPTED",
                }
                session = Mock(
                    nonce="b" * 64, issued=100, run_id=None, job_status="COMPLETED"
                )
                session.begin.return_value = {"status": "WAITING"}
                session.advance.return_value = {"status": "APPROVED"}
                session.public.return_value = state
                lookup = Mock()
                lookup.inventory.return_value = target
                callables = {
                    "collect": Mock(return_value=materials),
                    "inventory": lookup.inventory,
                    "frames": Mock(wraps=operator.frames),
                    "open": Mock(return_value=journal),
                    "begin": session.begin,
                    "advance": session.advance,
                    "settle": Mock(),
                    "artifact": session.artifact,
                    "apple": Mock(),
                }
                if point == "start":

                    def record(event, **data):
                        if event == "START":
                            raise fault

                    journal.record.side_effect = record
                else:
                    callables[point].side_effect = fault
                with (
                    patch.object(operator, "frames", callables["frames"]),
                    patch.object(operator, "settle", callables["settle"]),
                    patch.object(operator, "finalize_session", return_value=state),
                    patch.object(
                        operator.recovery,
                        "result_from_logs",
                        return_value={"cleanup_verified": False},
                    ),
                    patch.object(operator.recovery, "rediscover", callables["apple"]),
                    patch("sys.stdout", new_callable=io.StringIO) as output,
                ):
                    result = operator.execute(
                        "a" * 40,
                        staging,
                        config,
                        "owner@example.invalid",
                        collect=callables["collect"],
                        journal_factory=callables["open"],
                        session_factory=Mock(return_value=session),
                        owner_factory=Mock(return_value=lookup),
                    )
                self.assertEqual(
                    result["failure"],
                    dict(stage=stage, check=check, reason="UNEXPECTED_INTERNAL_ERROR"),
                )
                self.assertFalse(result["retry_authorized"])
                self.assertNotIn("private-sentinel", output.getvalue())

    def test_unreadable_status_never_claims_no_external_attempt(self):
        with (
            patch.object(operator, "preflight", return_value=("a" * 40, None)),
            patch.object(
                operator.journal_module.Journal,
                "open",
                side_effect=operator.journal_module.Rejected(),
            ),
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(operator.main(["--status"]), 2)
        self.assertIn('"external_write_state":"UNKNOWN"', output.getvalue())
        self.assertIn('"check":"journal_integrity"', output.getvalue())
        self.assertNotIn("NOT_ATTEMPTED", output.getvalue())

    def test_asc_input_failures_never_query_and_always_close(self):
        _, config, _, _ = self.fixture()
        config = replace(config, asc_path="C:/fictional/asc.p8")
        for stage in ("directory", "file", "verify", "close"):
            reader, factory = Mock(), Mock()
            getattr(reader, stage).side_effect = RuntimeError("private-sentinel")
            with (
                patch.object(operator.intake, "Path", PureWindowsPath),
                patch.object(operator.intake.inputs, "load_asc_key"),
                self.assertRaises(operator.Rejected) as caught,
            ):
                operator.asc_preflight(
                    config,
                    "owner@example.invalid",
                    reader_factory=lambda: reader,
                    owner_factory=factory,
                )
            self.assertEqual(caught.exception.stage, "asc_input")
            self.assertNotIn("private-sentinel", str(caught.exception))
            reader.close.assert_called_once()
            if stage != "close":
                factory.assert_not_called()

    def test_asc_check_requires_preflight_and_saved_settings(self):
        for phase in ("preflight", "settings_metadata"):
            staging, config, _, _ = self.fixture()
            with (
                patch.object(
                    operator, "preflight", return_value=("a" * 40, staging)
                ) as preflight,
                patch.object(
                    operator,
                    "settings_metadata",
                    return_value=(config, "owner@example.invalid"),
                ) as metadata,
                patch.object(operator, "asc_preflight") as asc,
                patch.object(operator, "execute") as execute,
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                (preflight if phase == "preflight" else metadata).side_effect = (
                    RuntimeError("private-sentinel")
                )
                self.assertEqual(operator.main(["--check-asc"]), 2)
            asc.assert_not_called()
            execute.assert_not_called()

    def test_stage_is_allowlisted_not_arbitrary_exception_data(self):
        for stage in ("private-sentinel", {"private-sentinel": True}, None):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                result = operator.emit("ASC_SCOPE_REJECTED", stage=stage)
            self.assertNotIn("stage", result)
            self.assertNotIn("private-sentinel", output.getvalue())

    def test_owner_scope_error_is_not_masked_by_operation_unresolved(self):
        staging, config, materials, _ = self.fixture()
        lookup = Mock()
        lookup.inventory.side_effect = owner.Rejected()
        journal, dispatch = Mock(), Mock()
        with patch("sys.stdout", new_callable=io.StringIO):
            result = operator.execute(
                "a" * 40,
                staging,
                config,
                "owner@example.invalid",
                collect=Mock(return_value=materials),
                owner_factory=Mock(return_value=lookup),
                journal_factory=journal,
                session_factory=dispatch,
            )
        self.assertEqual(result["classification"], "ASC_SCOPE_REJECTED")
        journal.assert_not_called()
        dispatch.assert_not_called()

    def test_asc_preflight_reads_only_selected_key_with_same_custody(self):
        _, config, _, _ = self.fixture()
        config = replace(config, asc_path="C:/fictional/asc.p8")
        reader, lookup = Mock(), Mock()
        reader.file.return_value = b"fictional-key"
        material = object()
        with (
            patch.object(operator.intake, "Path", PureWindowsPath),
            patch.object(
                operator.intake.inputs, "load_asc_key", return_value=material
            ) as load,
        ):
            operator.asc_preflight(
                config,
                "owner@example.invalid",
                reader_factory=lambda: reader,
                owner_factory=Mock(return_value=lookup),
            )
        reader.directory.assert_called_once_with(PureWindowsPath("C:/fictional"))
        reader.file.assert_called_once_with(PureWindowsPath(config.asc_path), 4096)
        reader.verify.assert_called_once()
        reader.close.assert_called_once()
        load.assert_called_once_with(
            b"fictional-key", key_id=config.asc_key_id, issuer_id=config.asc_issuer_id
        )
        lookup.inventory.assert_called_once_with(version=config.version)
        lookup.assign.assert_not_called()

    def test_asc_preflight_failure_closes_reader_and_suppresses_raw_values(self):
        _, config, _, _ = self.fixture()
        config = replace(config, asc_path="C:/fictional/asc.p8")
        for error, reason in (
            (owner.Rejected(), "ASC_SCOPE_REJECTED"),
            (owner.Rejected("ASC_PERMISSION_REJECTED"), "ASC_PERMISSION_REJECTED"),
            (RuntimeError("private-sentinel"), "ASC_SCOPE_REJECTED"),
        ):
            reader, lookup = Mock(), Mock(stage="asc_testers")
            lookup.inventory.side_effect = error
            with (
                patch.object(operator.intake, "Path", PureWindowsPath),
                patch.object(operator.intake.inputs, "load_asc_key"),
                self.assertRaises(operator.Rejected) as caught,
            ):
                operator.asc_preflight(
                    config,
                    "owner@example.invalid",
                    reader_factory=lambda: reader,
                    owner_factory=Mock(return_value=lookup),
                )
            self.assertEqual(caught.exception.args, (reason,))
            self.assertEqual(caught.exception.stage, "asc_testers")
            self.assertNotIn("private-sentinel", str(caught.exception))
            reader.close.assert_called_once()

    def test_asc_cli_never_prompts_or_executes_and_execution_checks_asc_first(self):
        staging, config, _, _ = self.fixture()
        config = replace(config, asc_path="C:/fictional/asc.p8")
        for args in (["--check-asc"], ["--execute", "--settings"]):
            for failure in (False, True):
                order = []

                def check(*args):
                    order.append("asc")
                    if failure:
                        raise operator.Rejected(
                            "ASC_PERMISSION_REJECTED", stage="asc_testers"
                        )

                def execute(*args):
                    order.append("execute")
                    return {"classification": "BUILD_VALID_UNDISTRIBUTED"}

                with (
                    patch.object(
                        operator, "preflight", return_value=("a" * 40, staging)
                    ),
                    patch.object(
                        operator,
                        "settings_metadata",
                        return_value=(config, "owner@example.invalid"),
                    ),
                    patch.object(operator, "asc_preflight", side_effect=check),
                    patch.object(operator, "execute", side_effect=execute) as run,
                    patch.object(operator.intake, "read_field") as prompt,
                    patch("sys.stdout", new_callable=io.StringIO) as output,
                ):
                    self.assertEqual(operator.main(args), 2 if failure else 0)
                self.assertEqual(
                    order,
                    (
                        ["asc", "execute"]
                        if args[0] == "--execute" and not failure
                        else ["asc"]
                    ),
                )
                prompt.assert_not_called()
                if args == ["--check-asc"] or failure:
                    run.assert_not_called()
                if failure:
                    self.assertIn('"stage":"asc_testers"', output.getvalue())
                elif args == ["--check-asc"]:
                    self.assertIn("ASC_PREFLIGHT_PASSED", output.getvalue())
                self.assertNotIn("owner@example.invalid", output.getvalue())

    def test_signing_input_reason_reaches_result_without_dispatch_or_journal(self):
        reasons = operator.intake.signing.BINDING_REASONS | {"SIGNING_FRAME_REJECTED"}
        for reason in reasons:
            staging, config, _, _ = self.fixture()
            collect = Mock(side_effect=operator.intake.Rejected(reason))
            journal, session, inventory = Mock(), Mock(), Mock()
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                result = operator.execute(
                    "a" * 40,
                    staging,
                    config,
                    "owner@example.invalid",
                    collect=collect,
                    journal_factory=journal,
                    session_factory=session,
                    owner_factory=inventory,
                )
            self.assertEqual(result["classification"], reason)
            self.assertIsNone(result["run_id"])
            self.assertFalse(result["release_authorized"])
            self.assertIn(reason, output.getvalue())
            self.assertNotIn("owner@example.invalid", output.getvalue())
            collect.assert_called_once_with(config)
            journal.assert_not_called()
            session.assert_not_called()
            inventory.assert_not_called()

    def test_key_import_modes_are_separate_from_execution_and_password(self):
        staging, _, _, _ = self.fixture()
        for args, classification in (
            (["--check-key-import"], "ASC_IMPORT_READY"),
            (["--import-asc-key"], "ASC_IMPORT_COMPLETE"),
        ):
            with (
                patch.object(operator, "preflight", return_value=("a" * 40, staging)),
                patch.object(
                    operator.key_custody,
                    "check_import",
                    return_value="ASC_IMPORT_READY",
                ) as preview,
                patch.object(
                    operator.key_custody,
                    "import_key",
                    return_value="ASC_IMPORT_COMPLETE",
                ) as apply,
                patch.object(operator, "settings_metadata") as metadata,
                patch.object(operator, "execute") as execute,
                patch.object(operator.intake, "read_field") as prompt,
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                self.assertEqual(operator.main(args), 0)
            self.assertIn(classification, output.getvalue())
            self.assertEqual(preview.call_count, args == ["--check-key-import"])
            self.assertEqual(apply.call_count, args == ["--import-asc-key"])
            (
                preview if args == ["--check-key-import"] else apply
            ).assert_called_once_with(google_web=staging.google_web)
            metadata.assert_not_called()
            execute.assert_not_called()
            prompt.assert_not_called()

    def test_import_preflight_failure_and_unresolved_never_retry(self):
        staging, _, _, _ = self.fixture()
        for args in (["--check-key-import"], ["--import-asc-key"]):
            with (
                patch.object(
                    operator,
                    "preflight",
                    side_effect=operator.Rejected("SOURCE_REJECTED"),
                ),
                patch.object(operator.key_custody, "check_import") as preview,
                patch.object(operator.key_custody, "import_key") as apply,
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                self.assertEqual(operator.main(args), 2)
            preview.assert_not_called()
            apply.assert_not_called()
        for error, expected in (
            (
                operator.key_custody.Rejected("ASC_IMPORT_UNRESOLVED"),
                "ASC_IMPORT_UNRESOLVED",
            ),
            (RuntimeError("private-sentinel"), "OPERATION_UNRESOLVED"),
        ):
            with (
                patch.object(operator, "preflight", return_value=("a" * 40, staging)),
                patch.object(
                    operator.key_custody, "import_key", side_effect=error
                ) as apply,
                patch.object(operator, "execute") as execute,
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                self.assertEqual(operator.main(["--import-asc-key"]), 2)
            self.assertIn(expected, output.getvalue())
            self.assertNotIn("private-sentinel", output.getvalue())
            apply.assert_called_once()
            execute.assert_not_called()

    def test_import_preview_present_is_metadata_only_not_complete(self):
        staging, _, _, _ = self.fixture()
        with (
            patch.object(operator, "preflight", return_value=("a" * 40, staging)),
            patch.object(
                operator.key_custody, "check_import", return_value="ASC_IMPORT_PRESENT"
            ),
            patch.object(operator.key_custody, "import_key") as apply,
            patch.object(operator, "execute") as execute,
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(operator.main(["--check-key-import"]), 2)
        self.assertIn("ASC_IMPORT_PRESENT", output.getvalue())
        self.assertNotIn("ASC_IMPORT_COMPLETE", output.getvalue())
        apply.assert_not_called()
        execute.assert_not_called()

    def test_saved_metadata_populates_six_fields_without_hidden_prompt(self):
        staging, config, _, _ = self.fixture()
        values = {
            "apple_team_id": config.team,
            "asc_key_id": config.asc_key_id,
            "asc_issuer_id": config.asc_issuer_id,
            "google_ios_client_id": config.google_ios_client_id,
            "owner_email": "owner@example.invalid",
            "asc_p8_path": "C:/fictional/asc.p8",
        }
        with (
            patch.object(operator.settings, "load", return_value=values) as load,
            patch.object(operator.intake, "read_field") as prompt,
            patch.object(operator.intake, "check_custody", create=True) as custody,
        ):
            actual, email = operator.settings_metadata(staging)
        self.assertEqual(actual.asc_path, values["asc_p8_path"])
        self.assertEqual(actual.api_base_url, staging.url)
        self.assertEqual(email, values["owner_email"])
        self.assertEqual(actual.build, 1)
        load.assert_called_once_with(google_web=staging.google_web)
        prompt.assert_not_called()
        custody.assert_called_once_with(actual)

    def test_saved_inputs_custody_failure_precedes_password_and_execute(self):
        staging, config, _, _ = self.fixture()
        values = {
            "apple_team_id": config.team,
            "asc_key_id": config.asc_key_id,
            "asc_issuer_id": config.asc_issuer_id,
            "google_ios_client_id": config.google_ios_client_id,
            "owner_email": "owner@example.invalid",
            "asc_p8_path": "C:/fictional/asc.p8",
        }
        for args in (["--check-inputs"], ["--execute", "--settings"]):
            with (
                patch.object(operator, "preflight", return_value=("a" * 40, staging)),
                patch.object(operator.settings, "load", return_value=values),
                patch.object(
                    operator.intake,
                    "check_custody",
                    side_effect=operator.intake.Rejected("CUSTODY_CHECK_REJECTED"),
                ) as custody,
                patch.object(operator.intake, "read_field") as prompt,
                patch.object(operator, "execute") as execute,
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                self.assertEqual(operator.main(args), 2)
            self.assertIn("CUSTODY_CHECK_REJECTED", output.getvalue())
            self.assertNotIn("SETTINGS_READY", output.getvalue())
            custody.assert_called_once()
            prompt.assert_not_called()
            execute.assert_not_called()

    def test_settings_modes_require_preflight_and_never_execute_on_invalid_file(self):
        staging, _, _, _ = self.fixture()
        for args in (
            ["--prepare-inputs"],
            ["--check-inputs"],
            ["--execute", "--settings"],
        ):
            with (
                patch.object(
                    operator,
                    "preflight",
                    side_effect=operator.Rejected("SOURCE_REJECTED"),
                ),
                patch.object(operator.settings, "prepare") as prepare,
                patch.object(operator.settings, "load") as load,
                patch.object(operator, "execute") as execute,
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                self.assertEqual(operator.main(args), 2)
            prepare.assert_not_called()
            load.assert_not_called()
            execute.assert_not_called()
        with (
            patch.object(operator, "preflight", return_value=("a" * 40, staging)),
            patch.object(
                operator.settings,
                "load",
                side_effect=operator.settings.Rejected("SETTINGS_FIELDS_REJECTED"),
            ),
            patch.object(operator, "execute") as execute,
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(operator.main(["--execute", "--settings"]), 2)
        self.assertIn("SETTINGS_FIELDS_REJECTED", output.getvalue())
        execute.assert_not_called()

    def test_prepare_and_check_never_read_signing_assets_or_execute(self):
        staging, config, _, _ = self.fixture()
        for args, classification in (
            (["--prepare-inputs"], "SETTINGS_TEMPLATE_CREATED"),
            (["--check-inputs"], "SETTINGS_READY"),
        ):
            with (
                patch.object(operator, "preflight", return_value=("a" * 40, staging)),
                patch.object(operator.settings, "prepare") as prepare,
                patch.object(
                    operator,
                    "settings_metadata",
                    return_value=(config, "owner@example.invalid"),
                ) as metadata,
                patch.object(operator, "execute") as execute,
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                self.assertEqual(operator.main(args), 0)
            self.assertIn(classification, output.getvalue())
            self.assertEqual(prepare.call_count, args == ["--prepare-inputs"])
            self.assertEqual(metadata.call_count, args == ["--check-inputs"])
            execute.assert_not_called()

    def test_metadata_reprompts_only_invalid_field_and_rejects_web_client(self):
        staging, config, _, _ = self.fixture()
        prompt = Mock(
            side_effect=[
                config.team,
                "bad-key",
                config.asc_key_id,
                config.asc_issuer_id,
                staging.google_web,
                config.google_ios_client_id,
                "owner@example.invalid",
            ]
        )
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            actual, email = operator.metadata(staging, prompt=prompt)
        self.assertEqual(actual.google_ios_client_id, config.google_ios_client_id)
        self.assertEqual(email, "owner@example.invalid")
        self.assertEqual(prompt.call_count, 7)
        self.assertEqual(prompt.call_args_list[1], prompt.call_args_list[2])
        self.assertEqual(prompt.call_args_list[4], prompt.call_args_list[5])
        self.assertIn("field=ASC_KEY_ID", output.getvalue())
        self.assertIn("field=GOOGLE_IOS", output.getvalue())
        self.assertNotIn("bad-key", output.getvalue())
        self.assertNotIn(staging.google_web, output.getvalue())

    def test_exhausted_metadata_never_reaches_private_intake_or_execute(self):
        staging, _, _, _ = self.fixture()
        with (
            patch.object(operator, "preflight", return_value=("a" * 40, staging)),
            patch.object(
                operator,
                "metadata",
                side_effect=operator.intake.Rejected("ASC_KEY_ID_INPUT_REJECTED"),
            ),
            patch.object(operator, "execute") as execute,
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(operator.main(["--execute"]), 2)
        self.assertIn("ASC_KEY_ID_INPUT_REJECTED", output.getvalue())
        execute.assert_not_called()

    def test_cli_resolves_tool_and_rejects_missing_executable(self):
        with (
            patch.object(
                operator.shutil, "which", return_value="C:/fixture/gcloud.CMD"
            ),
            patch.object(
                operator.primitives, "bounded_process", return_value=(0, b"{}")
            ) as run,
        ):
            self.assertEqual(operator.cli_json(["gcloud", "version"]), {})
        run.assert_called_once_with(["C:/fixture/gcloud.CMD", "version"])
        with (
            patch.object(operator.shutil, "which", return_value=None),
            self.assertRaises(operator.Rejected),
        ):
            operator.cli_json(["gcloud", "version"])

    @unittest.skipUnless(os.name == "nt", "Windows batch launch contract")
    def test_cli_launches_fictional_windows_batch_without_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory) / "fictional gcloud.cmd"
            batch.write_text('@echo {"fixture":true}\n', encoding="ascii")
            with patch.object(operator.shutil, "which", return_value=str(batch)):
                self.assertEqual(operator.cli_json(["gcloud"]), {"fixture": True})

    def fixture(self):
        staging = operator.Staging(
            "https://fictional-staging.run.app",
            "456-web.apps.googleusercontent.com",
            "123",
            False,
        )
        config = operator.intake.Config(
            "FICTTEAM01",
            "FICTKEY001",
            "11111111-1111-4111-8111-111111111111",
            "FICTKEY002",
            staging.url,
            "123-ios.apps.googleusercontent.com",
            staging.google_web,
            staging.line,
            "1.0.0",
            1,
        )
        material = SimpleNamespace(
            signing=hosted_fixtures.HostedTests().material(),
            asc=SimpleNamespace(pem=b"fake", material=object()),
        )
        target = owner.Target("123", "group", "tester", "1.0.0", 0, 1)
        return staging, config, material, target

    def test_exact_frames_keep_apple_login_out(self):
        staging, config, material, target = self.fixture()
        sign, asc = operator.frames(material, config, target)
        self.assertNotIn(b"apple_login", asc)
        self.assertNotIn(b"p12", asc)
        self.assertEqual(operator.hosted.asc_fields(asc)["owner_group_id"], "group")

    def test_complete_fake_path_records_intent_and_never_assigns_group(self):
        staging, config, materials, target = self.fixture()
        journal = Mock(intact=True)
        session = Mock(
            nonce="b" * 64,
            issued=100,
            run_id=123,
            job_status="COMPLETED",
            journal_failed=False,
        )
        session.attempted = list(operator.wire.SECRETS)
        session.begin.return_value = {"status": "WAITING"}
        session.advance.return_value = {"status": "APPROVED"}
        state = {
            "current_absence_verified": True,
            "retention_resolved": True,
            "cancel_unresolved": False,
        }
        session.public.return_value = session.cleanup.return_value = state
        factory = Mock(return_value=session)
        owner_session = Mock()
        owner_session.inventory.return_value = target
        with (
            patch.object(operator, "settle"),
            patch.object(
                operator.recovery,
                "result_from_logs",
                return_value={"cleanup_verified": True},
            ),
            patch.object(
                operator.recovery,
                "rediscover",
                return_value=(
                    SimpleNamespace(classification="BUILD_VALID_UNDISTRIBUTED"),
                    None,
                ),
            ),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            result = operator.execute(
                "a" * 40,
                staging,
                config,
                "owner@example.invalid",
                collect=Mock(return_value=materials),
                journal_factory=Mock(return_value=journal),
                session_factory=factory,
                owner_factory=Mock(return_value=owner_session),
            )
        self.assertEqual(result["classification"], "BUILD_VALID_UNDISTRIBUTED")
        self.assertFalse(result["owner_distribution_verified"])
        journal.record.assert_any_call(
            "START",
            sha="a" * 40,
            nonce="b" * 64,
            version="1.0.0",
            build=1,
            previous_build=0,
            issued=100,
            expires=7300,
        )
        self.assertEqual(session.signing, b"")
        owner_session.assign.assert_not_called()
        journal.close.assert_called_once()

    def test_scope_or_private_intake_failure_never_dispatches(self):
        staging, config, materials, target = self.fixture()
        for collect in (Mock(side_effect=operator.intake.Rejected()),):
            factory = Mock()
            with patch("sys.stdout", new_callable=io.StringIO):
                result = operator.execute(
                    "a" * 40,
                    staging,
                    config,
                    "owner@example.invalid",
                    collect=collect,
                    session_factory=factory,
                )
            self.assertEqual(result["classification"], "INPUT_REJECTED")
            factory.assert_not_called()

    def test_settle_deletes_once_not_on_every_poll(self):
        session = Mock(journal_failed=False, deadline=float("inf"))
        session.observe.side_effect = [
            {"job_status": "RUNNING"},
            {"job_status": "RUNNING"},
            {"job_status": "COMPLETED"},
        ]
        sleep = Mock()
        with patch("sys.stdout", new_callable=io.StringIO):
            operator.settle(session, sleep=sleep)
        session.cleanup.assert_called_once()
        self.assertEqual(sleep.call_count, 2)

    def interrupted_session(self):
        session = Mock(
            run_id=123,
            job_status="RUNNING",
            journal_failed=False,
            cancel_attempted=False,
            deadline=float("inf"),
            journal=Mock(intact=True, events=[]),
        )
        session.attempted = list(operator.wire.SECRETS)
        session.public.return_value = {
            "current_absence_verified": True,
            "retention_resolved": True,
            "cancel_unresolved": False,
        }

        def observe():
            session.job_status = "COMPLETED"
            return {"job_status": "COMPLETED"}

        session.observe.side_effect = observe
        return session

    def test_failure_finalization_cancels_then_observes_and_cleans(self):
        session = self.interrupted_session()
        operator.finalize_session(session, sleep=Mock())
        session.restrict_to_cleanup.assert_called_once()
        session.cancel.assert_called_once()
        session.observe.assert_called_once()
        session.cleanup.assert_called_once()
        self.assertEqual(session.signing, b"")

    def test_cancel_failure_does_not_skip_cleanup_or_claim_terminal(self):
        session = self.interrupted_session()
        session.cancel.side_effect = RuntimeError("fictional transport failure")
        session.observe.side_effect = RuntimeError("fictional transport failure")
        operator.finalize_session(session, sleep=Mock())
        session.cleanup.assert_called_once()
        session.cancel.assert_called_once()
        self.assertEqual(session.job_status, "RUNNING")
        self.assertTrue(session.cancel_unresolved)

    def test_completed_torn_unknown_or_previous_cancel_never_cancel_again(self):
        for variant in ("completed", "torn", "unknown", "attempted"):
            with self.subTest(variant=variant):
                session = self.interrupted_session()
                if variant == "completed":
                    session.job_status = "COMPLETED"
                elif variant == "torn":
                    session.journal.intact = False
                    session.journal_failed = True
                elif variant == "unknown":
                    session.run_id = None
                else:
                    session.cancel_attempted = True
                operator.finalize_session(session, sleep=Mock())
                session.cancel.assert_not_called()
                session.cleanup.assert_called_once()

    def test_advance_failure_interrupt_and_settle_timeout_finalize_once(self):
        staging, config, materials, target = self.fixture()
        for phase in ("advance_failure", "interrupt", "timeout"):
            with self.subTest(phase=phase):
                session = self.interrupted_session()
                session.nonce, session.issued = "b" * 64, 100
                session.begin.return_value = {"status": "WAITING"}
                session.advance.return_value = {"status": "APPROVED"}
                if phase == "advance_failure":
                    session.advance.side_effect = RuntimeError("fictional")
                elif phase == "interrupt":
                    session.advance.side_effect = KeyboardInterrupt()
                owner_session = Mock()
                owner_session.inventory.return_value = target
                with (
                    patch.object(
                        operator,
                        "settle",
                        side_effect=operator.Rejected("OBSERVATION_TIMEOUT"),
                    ),
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    result = operator.execute(
                        "a" * 40,
                        staging,
                        config,
                        "owner@example.invalid",
                        collect=Mock(return_value=materials),
                        journal_factory=Mock(return_value=session.journal),
                        session_factory=Mock(return_value=session),
                        owner_factory=Mock(return_value=owner_session),
                        sleep=Mock(),
                    )
                session.cancel.assert_called_once()
                session.cleanup.assert_called_once()
                self.assertNotEqual(
                    result["classification"], "BUILD_VALID_UNDISTRIBUTED"
                )
                session.journal.close.assert_called_once()

    def test_preflight_does_not_read_private_material(self):
        with (
            patch.object(operator, "preflight", return_value=("a" * 40, Mock())),
            patch.object(operator, "metadata") as metadata,
            patch.object(operator, "execute") as execute,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            self.assertEqual(operator.main(["--preflight"]), 0)
        metadata.assert_not_called()
        execute.assert_not_called()

    def test_unverified_staging_stops_before_private_input(self):
        with (
            patch.object(
                operator,
                "preflight",
                side_effect=lambda **kw: ("a" * 40, operator.staging_scope()),
            ),
            patch.object(
                operator.staging_contract,
                "verify",
                return_value={"ownership_verified": False},
            ),
            patch.object(operator, "metadata") as metadata,
            patch.object(operator, "execute") as execute,
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(operator.main(["--execute"]), 2)
        self.assertIn("STAGING_OWNERSHIP_UNVERIFIED", output.getvalue())
        metadata.assert_not_called()
        execute.assert_not_called()

    def test_staging_inputs_use_exact_ownership_verified_snapshot(self):
        fixture = staging_fixtures.StagingTests()
        fixture.setUp()
        fixture.service["status"]["url"] = "https://fictional-staging.run.app"
        for spec in (fixture.spec, fixture.service["spec"]["template"]["spec"]):
            spec["containers"][0]["env"][1]["value"] = "123"
            spec["containers"][0]["env"].append(
                {
                    "name": "MOBILE_API_GOOGLE_AUDIENCES",
                    "value": "456-web.apps.googleusercontent.com",
                }
            )
        with patch.object(operator, "cli_json", side_effect=fixture.cli):
            result = operator.staging_scope()
        self.assertEqual(result.url, "https://fictional-staging.run.app")
        self.assertEqual(result.line, "123")
        self.assertFalse(result.apple_configured)

    def test_recovery_input_only_reads_asc_key(self):
        from pathlib import PureWindowsPath

        reader = Mock()
        key = object()
        prompt = Mock(
            side_effect=[
                "FICTKEY001",
                "11111111-1111-4111-8111-111111111111",
                "owner@example.invalid",
                "ignored",
            ]
        )
        with (
            patch.object(
                operator.intake,
                "_path",
                return_value=PureWindowsPath("C:/private/key.p8"),
            ),
            patch.object(operator.intake.inputs, "load_asc_key", return_value=key),
        ):
            result = operator.asc_recovery_input(
                prompt=prompt, reader_factory=Mock(return_value=reader)
            )
        self.assertIs(result[0], key)
        reader.file.assert_called_once_with(PureWindowsPath("C:/private/key.p8"), 4096)
        reader.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
