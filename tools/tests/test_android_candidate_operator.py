from __future__ import annotations

import contextlib
import io
import os
import socket
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import android_candidate_operator as operator


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


class AndroidCandidateOperatorTests(unittest.TestCase):
    def test_pubspec_version_is_exact_and_monotonic(self):
        self.assertEqual(
            operator.parse_version("version: 1.2.3+7\n"), operator.Version("1.2.3", 7)
        )
        for source in (
            "version: 1.2.3\n",
            "version: 1.2.3+01\n",
            "version: 1.2.3+0\n",
            "version: 0.0.0+1\n",
            "version: release+1\n",
        ):
            with self.subTest(source=source), self.assertRaises(operator.OperatorError):
                operator.parse_version(source)

    def test_preflight_requires_clean_exact_main(self):
        with tempfile.TemporaryDirectory() as directory:
            pubspec = Path(directory) / "pubspec.yaml"
            pubspec.write_text("version: 0.1.0+1\n", encoding="utf-8")
            values = iter(("main", "a" * 40, "a" * 40, ""))
            with (
                mock.patch.object(
                    operator, "_git", side_effect=lambda *_: next(values)
                ),
                mock.patch.object(operator, "PUBSPEC", pubspec),
                mock.patch.object(operator, "FLUTTER_WRAPPER", pubspec),
            ):
                result = operator.preflight(previous_version_code=0)
        self.assertEqual(result["classification"], "READY_FOR_PRIVATE_INPUT")
        self.assertEqual(result["external_mutation_count"], 0)

        for state in (
            ("codex/work", "a" * 40, "a" * 40, ""),
            ("main", "a" * 40, "b" * 40, ""),
            ("main", "a" * 40, "a" * 40, " M file"),
        ):
            values = iter(state)
            with (
                self.subTest(state=state),
                mock.patch.object(
                    operator, "_git", side_effect=lambda *_: next(values)
                ),
                self.assertRaises(operator.OperatorError),
            ):
                operator.preflight(previous_version_code=0)

    def test_private_lines_are_external_bounded_and_never_echoed(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "release.jks"
            key.write_bytes(b"fictional")
            values = (
                "https://mobile-release.invalid",
                "12345",
                "android.apps.googleusercontent.com",
                "server.apps.googleusercontent.com",
                str(key),
                "release-key",
                "password-one",
                "password-two",
            )
            self.assertEqual(
                operator.validate_private_lines(values, contract_test=False), values
            )
            for changed in (
                values[:-1],
                (*values[:-1], " padded "),
                (*values[:-1], "x" * 2049),
            ):
                with (
                    self.subTest(changed=len(changed)),
                    self.assertRaises(operator.OperatorError) as raised,
                ):
                    operator.validate_private_lines(changed, contract_test=False)
                self.assertNotIn("password", str(raised.exception))

    def test_build_command_contains_only_public_contract(self):
        command = operator.build_command(
            operator.Version("0.1.0", 1),
            private_port=23456,
            private_nonce="a" * 32,
        )
        rendered = " ".join(command)
        for expected in (
            "mobile-release-private-mode=candidate",
            "RELEASE_CHANNEL=android-closed",
            "APP_FLAVOR=staging",
            "CLIENT_MODE=real",
            "RELEASE_SCOPE=basic",
        ):
            self.assertIn(expected, rendered)
        for forbidden in (
            "API_BASE_URL",
            "LINE_CHANNEL_ID",
            "GOOGLE_CLIENT_ID",
            "PASSWORD",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_child_environment_does_not_inherit_sensitive_values(self):
        with mock.patch.dict(
            os.environ,
            {
                "PATH": "public-path",
                "SECRET_SENTINEL": "do-not-copy",
                "MOBILE_RELEASE_STORE_PASSWORD": "do-not-copy",
            },
            clear=True,
        ):
            environment = operator._minimal_environment({"SAFE": "value"})
        self.assertEqual(environment["PATH"], "public-path")
        self.assertEqual(environment["SAFE"], "value")
        self.assertNotIn("SECRET_SENTINEL", environment)
        self.assertNotIn("MOBILE_RELEASE_STORE_PASSWORD", environment)
        if os.name == "nt":
            self.assertEqual(environment["JAVA_HOME"], str(operator.BUNDLED_JAVA_HOME))
            self.assertEqual(
                environment["ANDROID_SDK_ROOT"], str(operator.BUNDLED_ANDROID_HOME)
            )

    def test_private_channel_authenticates_before_sending_values(self):
        wrong_port = _free_port()
        command = operator.build_command(
            operator.Version("0.1.0", 1),
            private_port=wrong_port,
            private_nonce="a" * 32,
        )
        received = bytearray()

        def wrong_client(*_: object, **__: object) -> subprocess.CompletedProcess:
            with socket.create_connection(("127.0.0.1", wrong_port)) as client:
                client.sendall(b"b" * 32 + b"\n")
                received.extend(client.recv(4096))
            return subprocess.CompletedProcess(command, 1)

        with (
            mock.patch(
                "tools.android_candidate_operator.subprocess.run",
                side_effect=wrong_client,
            ),
            self.assertRaisesRegex(operator.OperatorError, "channel failed safely"),
        ):
            operator._run_private_build(
                command,
                private_lines=("SECRET-SENTINEL",),
                environment={},
            )
        self.assertEqual(received, b"")

        correct_port = _free_port()
        command = operator.build_command(
            operator.Version("0.1.0", 1),
            private_port=correct_port,
            private_nonce="c" * 32,
        )

        def correct_client(*_: object, **__: object) -> subprocess.CompletedProcess:
            with socket.create_connection(("127.0.0.1", correct_port)) as client:
                client.sendall(b"c" * 32 + b"\n")
                while chunk := client.recv(4096):
                    received.extend(chunk)
            return subprocess.CompletedProcess(command, 0)

        received.clear()
        private_lines = tuple(f"FICTIONAL-VALUE-{index}" for index in range(8))
        with mock.patch(
            "tools.android_candidate_operator.subprocess.run",
            side_effect=correct_client,
        ):
            result = operator._run_private_build(
                command,
                private_lines=private_lines,
                environment={},
            )
        self.assertEqual(result, 0)
        expected = bytearray()
        for value in private_lines:
            encoded = value.encode()
            expected.extend(struct.pack(">I", len(encoded)))
            expected.extend(encoded)
        self.assertEqual(received, expected)

    def test_cli_failure_is_fixed_and_does_not_echo_private_reason(self):
        stderr = io.StringIO()
        with (
            mock.patch.object(
                operator,
                "preflight",
                side_effect=operator.OperatorError("SECRET-SENTINEL"),
            ),
            contextlib.redirect_stderr(stderr),
        ):
            result = operator.main(["preflight", "--previous-version-code", "0"])
        self.assertEqual(result, 2)
        self.assertEqual(
            stderr.getvalue(), "STOP: Android candidate operator failed safely\n"
        )
        self.assertNotIn("SECRET-SENTINEL", stderr.getvalue())

    def test_build_failure_does_not_emit_child_output(self):
        private_values = ["safe"] * len(operator.PRIVATE_LABELS)
        with (
            mock.patch.object(
                operator,
                "preflight",
                return_value={"version_name": "0.1.0", "version_code": 1},
            ),
            mock.patch.object(
                operator, "validate_private_lines", return_value=tuple(private_values)
            ),
            mock.patch(
                "tools.android_candidate_operator._run_private_build",
                return_value=1,
            ),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(operator.OperatorError, "failed safely"),
        ):
            operator.build_candidate(
                previous_version_code=0,
                prompt=lambda _: operator.APPROVAL,
                hidden_prompt=lambda label: "a" * 64 if "SHA-256" in label else "safe",
            )


if __name__ == "__main__":
    unittest.main()
