"""Fictional CLI responses; no Owner assets, credentials or network."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import ios_native_secret_setup as setup

SHA = "a" * 40


class Fake:
    def __init__(self):
        self.names = []
        self.calls = []
        self.inputs = []
        self.approval = "SET p12"
        self.write_error = None
        self.post_error = False
        self.bypass = False
        self.concurrent = False

    def run(self, stage, args, payload=None):
        self.calls.append((stage, args, payload))
        if stage == "store":
            if self.write_error:
                raise setup.Failure(stage, self.write_error, 1)
            self.names.append(args[3])
            return b""
        if stage == "source_head" or stage == "source_branch":
            return (SHA if stage == "source_head" else "main").encode()
        if stage == "source_clean":
            return b""
        if stage == "identity":
            value = {"login": setup.OWNER}
        elif stage == "remote_head":
            value = {"object": {"sha": SHA}}
        elif stage == "environment":
            value = {
                "name": setup.ENVIRONMENT,
                "can_admins_bypass": self.bypass,
                "deployment_branch_policy": {
                    "protected_branches": False,
                    "custom_branch_policies": True,
                },
                "protection_rules": [
                    {
                        "type": "required_reviewers",
                        "prevent_self_review": False,
                        "reviewers": [
                            {"type": "User", "reviewer": {"login": setup.OWNER}}
                        ],
                    },
                    {"type": "branch_policy"},
                ],
            }
        elif stage == "branches":
            value = {
                "total_count": 1,
                "branch_policies": [{"name": "main", "type": "branch"}],
            }
        elif stage in ("presence", "postcheck"):
            if stage == "postcheck" and self.post_error:
                raise setup.Failure(stage, "HTTP_503", 1)
            names = self.names[:]
            if self.concurrent and self.inputs:
                names.append(setup.FIELDS["p12"])
            value = {"total_count": len(names), "secrets": [{"name": n} for n in names]}
        else:
            raise AssertionError(stage)
        return json.dumps(value).encode()

    def prompt(self, field):
        self.inputs.append(field)
        return self.approval if field == "approval" else "fictional-selected-file"


class SetupTests(unittest.TestCase):
    def test_saved_asc_holds_only_settings_and_selected_key_until_verify_close(self):
        import base64

        from tools import ios_testflight_intake as intake
        from tools.tests.test_ios_native_upload import fixture

        data = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            values = {
                "apple_team_id": "FAKETEAM01",
                "asc_key_id": data["key_id"],
                "asc_issuer_id": data["issuer_id"],
                "owner_email": "owner@example.invalid",
                "google_ios_client_id": "fake-ios.apps.googleusercontent.com",
                "asc_p8_path": str(root / "asc.p8"),
            }
            reader = Mock()
            reader.file.side_effect = [
                json.dumps(values).encode(),
                base64.b64decode(data["p8_base64"]),
            ]
            payload = setup.saved_asc(reader_factory=lambda: reader, root=root)
            self.assertEqual(json.loads(payload), data)
            self.assertEqual(
                [str(c.args[0].name) for c in reader.file.call_args_list],
                ["testflight-inputs.json", "asc.p8"],
            )
            self.assertEqual(
                [c[0] for c in reader.mock_calls][-2:], ["verify", "close"]
            )
            reader.file.side_effect = intake.Rejected("READ_REJECTED")
            reader.close.side_effect = RuntimeError("fictional-private")
            with self.assertRaises(setup.Failure) as caught:
                setup.saved_asc(reader_factory=lambda: reader, root=root)
            self.assertEqual(caught.exception.stage, "asc_settings")
            self.assertEqual(caught.exception.reason, "READ_REJECTED")
            self.assertEqual(caught.exception.cleanup, "CUSTODY_CLOSE_UNRESOLVED")

    def test_asc_input_primary_and_close_failure_reach_final_without_write(self):
        fake = Fake()
        fake.approval = "SET asc"
        failure = setup.Failure(
            "asc_input", "ACL_REJECTED", cleanup="CUSTODY_CLOSE_UNRESOLVED"
        )
        with patch.object(setup, "saved_asc", side_effect=failure):
            result = setup.perform(
                "asc",
                SHA,
                execute=True,
                run=fake.run,
                prompt=fake.prompt,
                emit=lambda _: None,
            )
        self.assertEqual(result["failure"]["stage"], "asc_input")
        self.assertEqual(result["failure"]["reason"], "ACL_REJECTED")
        self.assertEqual(result["cleanup_failure"], "CUSTODY_CLOSE_UNRESOLVED")
        self.assertFalse(any(c[0] == "store" for c in fake.calls))

    def test_asc_reuses_saved_input_once_without_reasking_fields(self):
        from tools.tests.test_ios_native_upload import fixture

        fake = Fake()
        fake.approval = "SET asc"
        payload = json.dumps(fixture()).encode()
        with patch.object(setup, "saved_asc", return_value=payload) as load:
            result = setup.perform(
                "asc",
                SHA,
                execute=True,
                run=fake.run,
                prompt=fake.prompt,
                emit=lambda _: None,
            )
        self.assertEqual(result["classification"], "STORED_METADATA_CONFIRMED")
        self.assertEqual(fake.inputs, ["approval"])
        load.assert_called_once()
        writes = [c for c in fake.calls if c[0] == "store"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][2], payload)
        self.assertNotIn(payload.decode(), str(writes[0][1]))

    def test_existing_asc_and_preflight_never_load_private_file(self):
        for present in (False, True):
            fake = Fake()
            if present:
                fake.names.append(setup.FIELDS["asc"])
            with patch.object(setup, "saved_asc") as load:
                result = setup.perform(
                    "asc",
                    SHA,
                    execute=present,
                    run=fake.run,
                    prompt=fake.prompt,
                    emit=lambda _: None,
                )
            self.assertEqual(
                result["classification"], "ALREADY_PRESENT" if present else "READY"
            )
            load.assert_not_called()
            self.assertEqual(fake.inputs, [])

    def test_escape_guard_is_not_network_or_generic_failure(self):
        self.assertEqual(
            setup.cli_reason(
                b"the response contains terminal escape sequences; pass --allow-escape-sequences to output it anyway"
            ),
            "TERMINAL_ESCAPE_GUARD",
        )

    def test_schema_failure_retains_each_actual_stage(self):
        for missing_stage in ("identity", "remote_head", "environment", "branches"):
            with self.subTest(stage=missing_stage):
                fake = Fake()
                original = fake.run

                def malformed(stage, args, payload=None):
                    return (
                        b"{}"
                        if stage == missing_stage
                        else original(stage, args, payload)
                    )

                result = setup.perform(
                    "p12",
                    SHA,
                    execute=True,
                    run=malformed,
                    prompt=fake.prompt,
                    emit=lambda _: None,
                )
                self.assertEqual(result["failure"]["stage"], missing_stage)
                self.assertEqual(result["failure"]["reason"], "SCHEMA_REJECTED")
                self.assertEqual(fake.inputs, [])
                self.assertEqual(result["write_state"], "NOT_ATTEMPTED")

    def perform(self, fake, execute=True, reader=lambda _: b"fictional-p12"):
        return setup.perform(
            "p12",
            SHA,
            execute=execute,
            run=fake.run,
            prompt=fake.prompt,
            read=reader,
            emit=lambda _: None,
        )

    def test_ready_does_not_read_private_input_or_write(self):
        fake = Fake()
        result = self.perform(fake, execute=False)
        self.assertEqual(result["classification"], "READY")
        self.assertEqual(fake.inputs, [])
        self.assertFalse(any(call[0] == "store" for call in fake.calls))

    def test_one_stdin_write_and_presence_is_not_signing(self):
        fake = Fake()
        result = self.perform(fake)
        writes = [call for call in fake.calls if call[0] == "store"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][2], b"ZmljdGlvbmFsLXAxMg==")
        self.assertNotIn("ZmljdGlvbmFs", str(writes[0][1]))
        self.assertEqual(result["classification"], "STORED_METADATA_CONFIRMED")
        self.assertFalse(result["signing_verified"])

    def test_existing_field_does_not_prompt_or_overwrite(self):
        fake = Fake()
        fake.names = [setup.FIELDS["p12"]]
        result = self.perform(fake)
        self.assertEqual(result["classification"], "ALREADY_PRESENT")
        self.assertEqual(fake.inputs, [])

    def test_protection_rejection_precedes_private_input(self):
        fake = Fake()
        fake.bypass = True
        result = self.perform(fake)
        self.assertEqual(result["failure"]["stage"], "environment")
        self.assertEqual(fake.inputs, [])

    def test_approval_rejection_and_race_never_write(self):
        for race in (False, True):
            fake = Fake()
            fake.concurrent = race
            if not race:
                fake.approval = "no"
            result = self.perform(fake)
            self.assertFalse(any(c[0] == "store" for c in fake.calls))
            self.assertEqual(result["write_state"], "NOT_ATTEMPTED")

    def test_uncertain_write_has_cause_and_never_retries(self):
        fake = Fake()
        fake.write_error = "TIMEOUT"
        result = self.perform(fake)
        self.assertEqual(result["write_state"], "ATTEMPTED_UNKNOWN")
        self.assertEqual(result["failure"]["stage"], "store")
        self.assertEqual(result["failure"]["reason"], "TIMEOUT")
        self.assertEqual(result["next_action"], "READ_ONLY_REVIEW")
        self.assertEqual(sum(c[0] == "store" for c in fake.calls), 1)

    def test_postcheck_failure_preserves_confirmed_write(self):
        fake = Fake()
        fake.post_error = True
        result = self.perform(fake)
        self.assertEqual(result["write_state"], "CONFIRMED")
        self.assertEqual(result["failure"]["stage"], "postcheck")
        self.assertEqual(result["failure"]["reason"], "HTTP_503")

    def test_input_exception_cannot_leak_path_or_secret(self):
        def broken(_):
            raise OSError("fictional-sensitive-password-path")

        result = self.perform(Fake(), reader=broken)
        self.assertNotIn("fictional-sensitive", json.dumps(result))
        self.assertEqual(result["failure"]["stage"], "input")
        self.assertEqual(result["write_state"], "NOT_ATTEMPTED")

    def test_password_utf8_and_spaces_are_preserved_without_base64(self):
        fake = Fake()

        def prompt(field):
            return "SET password" if field == "approval" else " fictional-假 密碼 "

        result = setup.perform(
            "password",
            SHA,
            execute=True,
            run=fake.run,
            prompt=prompt,
            emit=lambda _: None,
        )
        writes = [c for c in fake.calls if c[0] == "store"]
        self.assertEqual(writes[0][2], " fictional-假 密碼 ".encode("utf-8"))
        self.assertEqual(result["classification"], "STORED_METADATA_CONFIRMED")
        self.assertNotIn("fictional", json.dumps(result))

    def test_bad_password_and_oversized_file_never_write(self):
        for value in ("", "secret\n", "secret\x00", "x" * 1025):
            fake = Fake()
            result = setup.perform(
                "password",
                SHA,
                execute=True,
                run=fake.run,
                prompt=lambda f: "SET password" if f == "approval" else value,
                emit=lambda _: None,
            )
            self.assertEqual(result["failure"]["stage"], "input")
            self.assertFalse(any(c[0] == "store" for c in fake.calls))
        fake = Fake()
        result = self.perform(fake, reader=lambda _: b"x" * (setup.MAX_RAW + 1))
        self.assertEqual(result["failure"]["reason"], "INPUT_TOO_LARGE")
        self.assertFalse(any(c[0] == "store" for c in fake.calls))

    def test_schema_and_source_rejection_never_prompt(self):
        fake = Fake()
        result = setup.perform(
            "p12",
            "b" * 40,
            execute=True,
            run=fake.run,
            prompt=fake.prompt,
            emit=lambda _: None,
        )
        self.assertEqual(result["failure"]["reason"], "SOURCE_REJECTED")
        self.assertEqual(fake.inputs, [])
        original = fake.run

        def malformed(stage, args, payload=None):
            return (
                b'{"secrets":[],"total_count":101}'
                if stage == "presence"
                else original(stage, args, payload)
            )

        result = setup.perform(
            "p12",
            SHA,
            execute=True,
            run=malformed,
            prompt=fake.prompt,
            emit=lambda _: None,
        )
        self.assertEqual(result["failure"]["stage"], "presence")
        self.assertEqual(fake.inputs, [])

    def test_launch_failure_and_known_success_cleanup_effects(self):
        for started, confirmed in ((False, False), (True, True)):
            fake = Fake()
            original = fake.run

            def broken(stage, args, payload=None):
                if stage == "store":
                    raise setup.Failure(
                        stage,
                        "CLI_LAUNCH_FAILED" if not started else "PROCESS_UNRESOLVED",
                        started=started,
                        confirmed=confirmed,
                        cleanup="PROCESS_UNRESOLVED" if confirmed else None,
                    )
                return original(stage, args, payload)

            result = setup.perform(
                "p12",
                SHA,
                execute=True,
                run=broken,
                prompt=fake.prompt,
                read=lambda _: b"fictional",
                emit=lambda _: None,
            )
            self.assertEqual(
                result["write_state"], "CONFIRMED" if confirmed else "NOT_ATTEMPTED"
            )
            self.assertEqual(result["next_action"], "READ_ONLY_REVIEW")

    def test_private_file_custody_reuse_and_close_failure(self):
        from tools import ios_testflight_key_custody as existing
        from tools.tests.test_ios_testflight_key_custody import FakeNative

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fictional.p12"
            native = FakeNative()
            native.files[path] = b"fictional"
            with (
                patch.object(existing, "Native", return_value=native),
                patch.object(existing.preparation, "safe_directory", return_value=None),
            ):
                self.assertEqual(setup.read_file(str(path), "p12"), b"fictional")
                self.assertEqual(native.writes, [])
                self.assertEqual(native.handles, {})
                native.fail_acl = native.fail_close = True
                with self.assertRaises(setup.Failure) as caught:
                    setup.read_file(str(path), "p12")
                self.assertEqual(caught.exception.reason, "ACL_REJECTED")
                self.assertEqual(caught.exception.cleanup, "CUSTODY_CLOSE_UNRESOLVED")


class Child:
    def __init__(self, error=None, kill_error=False, close_error=False):
        self.error, self.kill_error, self.returncode = error, kill_error, None
        self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
        if close_error:
            self.stdout.close = lambda: (_ for _ in ()).throw(
                OSError("fictional-private")
            )

    def communicate(self, **kwargs):
        if self.error:
            raise self.error
        self.returncode = 0
        return b"", b""

    def poll(self):
        return self.returncode

    def kill(self):
        if self.kill_error:
            raise KeyboardInterrupt()
        self.returncode = -1

    def wait(self, **kwargs):
        return self.returncode


class CommandTests(unittest.TestCase):
    def test_entry_preserves_selected_field_and_cleanup_failure(self):
        failure = setup.Failure("version", "TIMEOUT", cleanup="PROCESS_UNRESOLVED")
        output = io.StringIO()
        with (
            patch.object(setup.sys, "platform", "win32"),
            patch.object(setup, "command", side_effect=failure),
            patch.object(setup.sys, "stdout", output),
            patch.dict(os.environ, {"GH_DEBUG": ""}),
        ):
            self.assertEqual(setup.main(["p12", "--expected-commit", SHA]), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result.get("cleanup_failure"), "PROCESS_UNRESOLVED")
        self.assertEqual(result.get("field"), setup.FIELDS["p12"])
        self.assertEqual(result["failure"]["stage"], "version")
        self.assertEqual(result["failure"]["reason"], "TIMEOUT")
        self.assertEqual(result["write_state"], "NOT_ATTEMPTED")

    def test_timeout_retains_primary_when_cleanup_interrupted(self):
        child = Child(subprocess.TimeoutExpired("fictional", 60), kill_error=True)
        with patch.object(setup.subprocess, "Popen", return_value=child):
            with self.assertRaises(setup.Failure) as caught:
                setup.command("store", [setup.GH], b"fictional-password")
        self.assertEqual(caught.exception.reason, "TIMEOUT")
        self.assertEqual(caught.exception.cleanup, "PROCESS_UNRESOLVED")

    def test_stdout_stderr_capture_and_env_are_private(self):
        with patch.dict(
            os.environ,
            {
                "GH_DEBUG": "api",
                "GH_TOKEN": "fictional-token",
                "SENSITIVE_TEST": "fictional-password",
            },
        ):
            env = setup.child_env()
        self.assertNotIn("GH_DEBUG", env)
        self.assertNotIn("GH_TOKEN", env)
        self.assertNotIn("SENSITIVE_TEST", env)
        self.assertEqual(env["GH_HOST"], "github.com")
        child = Child()
        with patch.object(setup.subprocess, "Popen", return_value=child) as popen:
            setup.command("store", [setup.GH, "secret", "set"], b"fictional")
        options = popen.call_args.kwargs
        self.assertFalse(options["shell"])
        self.assertEqual(options["stdout"], subprocess.PIPE)
        self.assertEqual(options["stderr"], subprocess.PIPE)

    def test_real_fictional_child_roundtrip_and_safe_nonzero(self):
        self.assertEqual(
            setup.command(
                "fictional_child",
                [
                    sys.executable,
                    "-c",
                    "import sys; print(len(sys.stdin.buffer.read()))",
                ],
                b"fictional",
            ),
            b"9\r\n" if sys.platform == "win32" else b"9\n",
        )
        with self.assertRaises(setup.Failure) as caught:
            setup.command(
                "fictional_child",
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.buffer.write(sys.stdin.buffer.read()); sys.exit(7)",
                ],
                b"fictional-sensitive",
            )
        self.assertEqual(caught.exception.exit_code, 7)
        self.assertEqual(caught.exception.reason, "CLI_FAILED")
        self.assertNotIn("fictional-sensitive", json.dumps(caught.exception.public()))

    def test_known_cli_success_retained_when_pipe_close_fails(self):
        child = Child(close_error=True)
        with patch.object(setup.subprocess, "Popen", return_value=child):
            with self.assertRaises(setup.Failure) as caught:
                setup.command("store", [setup.GH], b"fictional-password")
        self.assertTrue(caught.exception.confirmed)
        self.assertEqual(caught.exception.cleanup, "PROCESS_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
