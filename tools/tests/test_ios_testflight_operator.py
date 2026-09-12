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
