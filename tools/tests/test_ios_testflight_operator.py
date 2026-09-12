import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools import ios_testflight_operator as operator
from tools import ios_testflight_owner as owner
from tools.tests import test_ios_testflight_hosted as hosted_fixtures
from tools.tests import test_ios_testflight_staging as staging_fixtures


class OperatorTests(unittest.TestCase):
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
            journal=Mock(intact=True),
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
