import ctypes as c
import io
import plistlib
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

from asn1crypto import cms
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tools import ios_testflight_intake as intake


class IntakeTests(unittest.TestCase):
    def custody_check(self, reader):
        with (
            mock.patch.object(intake, "Path", PureWindowsPath),
            mock.patch.object(
                intake.preparation,
                "local_app_data",
                return_value=PureWindowsPath("C:/fictional"),
            ),
        ):
            return intake.check_custody(
                self.config(asc_path="C:/selected/asc.p8"),
                custodyfactory=lambda: reader,
            )

    def test_custody_check_is_metadata_only_for_exact_upload_files(self):
        reader = mock.Mock()
        self.custody_check(reader)
        root = PureWindowsPath("C:/fictional") / intake.preparation.DIRECTORY
        self.assertEqual(
            reader.directory.call_args_list,
            [mock.call(root), mock.call(PureWindowsPath("C:/selected"))],
        )
        self.assertEqual(
            reader.inspect.call_args_list,
            [
                mock.call(root / "distribution.p12", 65536),
                mock.call(root / "distribution.cer", 65536),
                mock.call(root / "distribution.mobileprovision", 262144),
                mock.call(PureWindowsPath("C:/selected/asc.p8"), 4096),
            ],
        )
        reader.file.assert_not_called()
        reader.verify.assert_called_once()
        reader.close.assert_called_once()

    def test_custody_directory_rejection_reports_only_fixed_alias_and_reason(self):
        reader = mock.Mock()
        reader.directory.side_effect = [
            None,
            intake.custody.CustodyError("ACL_REJECTED"),
        ]
        with (
            mock.patch("sys.stdout", new_callable=io.StringIO) as output,
            self.assertRaisesRegex(intake.Rejected, "^CUSTODY_CHECK_REJECTED$"),
        ):
            self.custody_check(reader)
        self.assertEqual(
            output.getvalue(),
            "custody_rejected target=ASC_DIRECTORY reason=ACL_REJECTED\n",
        )
        reader.inspect.assert_not_called()
        reader.file.assert_not_called()
        reader.close.assert_called_once()

    def test_custody_file_snapshot_and_close_errors_are_sanitized(self):
        for stage, target in (("inspect", "P12"), ("verify", "SNAPSHOT")):
            reader = mock.Mock()
            getattr(reader, stage).side_effect = RuntimeError("private-sentinel")
            with (
                mock.patch("sys.stdout", new_callable=io.StringIO) as output,
                self.assertRaisesRegex(intake.Rejected, "^CUSTODY_CHECK_REJECTED$"),
            ):
                self.custody_check(reader)
            self.assertEqual(
                output.getvalue(),
                f"custody_rejected target={target} reason=INPUT_CHECK_REJECTED\n",
            )
            reader.close.assert_called_once()
        reader = mock.Mock()
        reader.close.side_effect = RuntimeError("private-sentinel")
        with self.assertRaisesRegex(intake.Rejected, "^CLOSE_UNRESOLVED$"):
            self.custody_check(reader)

    def test_custody_reports_each_fixed_file_alias_without_paths(self):
        for index, target in enumerate(("P12", "CERTIFICATE", "PROFILE", "ASC_KEY")):
            reader = mock.Mock()
            reader.inspect.side_effect = [None] * index + [
                intake.Rejected("METADATA_REJECTED")
            ]
            with (
                mock.patch("sys.stdout", new_callable=io.StringIO) as output,
                self.assertRaises(intake.Rejected),
            ):
                self.custody_check(reader)
            self.assertEqual(
                output.getvalue(),
                f"custody_rejected target={target} reason=METADATA_REJECTED\n",
            )
            self.assertEqual(reader.inspect.call_count, index + 1)
            reader.file.assert_not_called()
            reader.verify.assert_not_called()
            reader.close.assert_called_once()

    def test_inspect_retains_size_acl_and_change_guards_without_reads(self):
        for variant in ("size", "acl", "change"):
            native = mock.Mock()
            native.open_handle.return_value = 7
            native.metadata.return_value = (1, 2, 3, 3, 4, 5)
            reader = intake.Reader(lambda: native)
            path = Path("C:/fictional/a.p8")
            reader.directories.add(path.parent)
            if variant == "size":
                native.metadata.return_value = (1, 2, 3, 4097, 4, 5)
            elif variant == "acl":
                native.acl.side_effect = intake.custody.CustodyError("ACL_REJECTED")
            else:
                reader.inspect(path, 4096)
                native.metadata.return_value = (1, 2, 3, 3, 4, 6)
            with self.assertRaises((intake.Rejected, intake.custody.CustodyError)):
                reader.verify() if variant == "change" else reader.inspect(path, 4096)
            reader.close()
            native.read.assert_not_called()
            native.seek.assert_not_called()

    def test_reader_inspect_never_reads_payload_and_keeps_snapshot(self):
        native = mock.Mock()
        native.open_handle.return_value = 7
        native.metadata.return_value = (1, 2, 3, 3, 4, 5)
        reader = intake.Reader(lambda: native)
        path = Path("C:/fictional/a.p8")
        reader.directories.add(path.parent)
        self.assertEqual(reader.inspect(path, 4096), (7, (1, 2, 3, 3, 4, 5)))
        reader.verify()
        native.read.assert_not_called()
        native.seek.assert_not_called()
        native.acl.assert_any_call(7)
        reader.close()
        native.close.assert_called_once_with(7)

    def test_each_field_exhausts_three_syntax_attempts_without_echo(self):
        for field in intake.PROMPTS:
            prompt = mock.Mock(return_value="\ud800private-sentinel")
            with (
                mock.patch("sys.stdout", new_callable=io.StringIO) as output,
                self.assertRaisesRegex(
                    intake.Rejected, "^" + field + "_INPUT_REJECTED$"
                ),
            ):
                intake.read_field(field, prompt=prompt)
            self.assertEqual(prompt.call_count, 3)
            self.assertNotIn("private-sentinel", output.getvalue())

    def test_prompt_failures_and_unknown_fields_are_not_retryable(self):
        for error in (
            EOFError(),
            KeyboardInterrupt(),
            intake.preparation.Rejected(),
            RuntimeError("private-sentinel"),
        ):
            prompt = mock.Mock(side_effect=error)
            with self.assertRaisesRegex(intake.Rejected, "^INPUT_READ_REJECTED$"):
                intake.read_field("P12_PASSWORD", prompt=prompt)
            prompt.assert_called_once()
        prompt = mock.Mock()
        with self.assertRaisesRegex(intake.Rejected, "^INPUT_REJECTED$"):
            intake.read_field("private-sentinel", prompt=prompt)
        prompt.assert_not_called()

    def test_password_whitespace_and_case_are_not_normalized(self):
        value = "  Fictional PaSSphrase  "
        self.assertEqual(
            intake.read_field("P12_PASSWORD", prompt=lambda _: value), value
        )

    def config(self, **changes):
        values = dict(
            team="FICTTEAM01",
            asc_key_id="FICTKEY001",
            asc_issuer_id="11111111-1111-4111-8111-111111111111",
            apple_login_key_id="FICTKEY002",
            api_base_url="https://fictional.invalid",
            google_ios_client_id="fictional-ios.apps.googleusercontent.com",
            google_web_client_id="fictional-web.apps.googleusercontent.com",
            line_channel_id="123",
            version="1.0.0",
            build=1,
        )
        return intake.Config(**(values | changes))

    def reader(self):
        reader = mock.Mock()

        def pem():
            return ec.generate_private_key(ec.SECP256R1()).private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )

        profile = cms.ContentInfo(
            {
                "content_type": "signed_data",
                "content": {
                    "version": "v1",
                    "digest_algorithms": [],
                    "encap_content_info": {
                        "content_type": "data",
                        "content": plistlib.dumps(
                            {
                                "DeveloperCertificates": [b"fictional-cert"],
                                "TeamIdentifier": ["FICTTEAM01"],
                                "UUID": "11111111-1111-1111-1111-111111111111",
                            }
                        ),
                    },
                    "signer_infos": [],
                },
            }
        ).dump()
        reader.file.side_effect = [
            b"fictional-p12",
            b"fictional-cert",
            profile,
            pem(),
            pem(),
        ]
        return reader

    def invoke(
        self, reader, config=None, prompt=None, include_login=True, binding_error=None
    ):
        with (
            # Fake Windows custody must keep Windows path semantics even when
            # these offline tests run on a POSIX CI host. Never bypass _path.
            mock.patch.object(intake, "Path", PureWindowsPath),
            mock.patch.object(
                intake.preparation,
                "local_app_data",
                return_value=PureWindowsPath("C:/fictional"),
            ),
            mock.patch.object(
                intake.signing, "_certificate_binding", side_effect=binding_error
            ),
        ):
            return intake.collect(
                config or self.config(),
                prompt=prompt
                or mock.Mock(
                    side_effect=[
                        "fictional-password",
                        "C:/fictional/asc.p8",
                        "C:/fictional/login.p8",
                    ]
                ),
                custodyfactory=lambda: reader,
                include_login=include_login,
            )

    def test_invalid_config_before_prompt(self):
        with self.assertRaises(intake.Rejected) as error:
            intake.collect(None, prompt=lambda _: self.fail("prompted"))
        self.assertEqual(str(error.exception), "INPUT_REJECTED")

    def test_upload_only_never_requests_or_reads_apple_login_key(self):
        reader = self.reader()
        prompt = mock.Mock(side_effect=["fictional-password", "C:/fictional/asc.p8"])
        with mock.patch.object(intake.inputs, "load_apple_login_key") as login:
            result = self.invoke(reader, prompt=prompt, include_login=False)
        self.assertEqual(prompt.call_count, 2)
        self.assertEqual(reader.file.call_count, 4)
        self.assertIsNone(result.apple_login)
        login.assert_not_called()

    def test_fake_windows_path_seam_preserves_validation(self):
        with mock.patch.object(intake, "Path", PureWindowsPath):
            self.assertEqual(
                intake._path("C:/fictional/asc.p8"),
                PureWindowsPath("C:/fictional/asc.p8"),
            )
            for value in (
                "relative.p8",
                "C:/fictional/../asc.p8",
                "C:/fictional/asc.txt",
                "C:/fictional/a:stream.p8",
            ):
                with self.assertRaises(intake.Rejected):
                    intake._path(value)

    def test_copy_as_path_quotes_preserve_strict_path_checks(self):
        with mock.patch.object(intake, "Path", PureWindowsPath):
            self.assertEqual(
                intake._path('"C:/fictional/private folder/asc.p8"'),
                PureWindowsPath("C:/fictional/private folder/asc.p8"),
            )
            for value in (
                '"relative.p8"',
                '"C:/fictional/../asc.p8"',
                '"C:/fictional/asc.txt"',
                '"C:/fictional/a:stream.p8"',
                '"C:/fictional/asc.p8',
                'C:/fictional/asc.p8"',
                '""C:/fictional/asc.p8""',
                '"C:/fictional/a"b.p8"',
                '"C:/fictional/asc.p8" extra',
                '"C:/fictional/asc.p8\n"',
            ):
                with self.subTest(value=value), self.assertRaises(intake.Rejected):
                    intake._path(value)

    def test_path_correction_keeps_password_and_never_echoes_input(self):
        reader = self.reader()
        prompt = mock.Mock(
            side_effect=[
                "fictional-password",
                "C:/fictional/private-sentinel.txt",
                '"C:/fictional/asc.p8"',
            ]
        )
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.invoke(reader, prompt=prompt, include_login=False)
        self.assertEqual(prompt.call_count, 3)
        self.assertEqual(prompt.call_args_list[1], prompt.call_args_list[2])
        self.assertNotEqual(prompt.call_args_list[0], prompt.call_args_list[1])
        self.assertIn("field=ASC_PATH", output.getvalue())
        self.assertNotIn("private-sentinel", output.getvalue())
        self.assertNotIn("fictional-password", output.getvalue())
        self.assertEqual(reader.file.call_count, 4)

    def test_path_attempts_bounded_and_never_read_private_files_on_exhaustion(self):
        reader = self.reader()
        prompt = mock.Mock(side_effect=["fictional-password"] + ["bad.txt"] * 3)
        with (
            mock.patch("sys.stdout", new_callable=io.StringIO),
            self.assertRaisesRegex(intake.Rejected, "^ASC_PATH_INPUT_REJECTED$"),
        ):
            self.invoke(reader, prompt=prompt, include_login=False)
        self.assertEqual(prompt.call_count, 4)
        reader.file.assert_not_called()
        reader.close.assert_called_once()

    def test_input_interrupt_never_reprompts(self):
        reader = self.reader()
        prompt = mock.Mock(side_effect=["fictional-password", KeyboardInterrupt()])
        with self.assertRaisesRegex(intake.Rejected, "^INPUT_READ_REJECTED$"):
            self.invoke(reader, prompt=prompt, include_login=False)
        self.assertEqual(prompt.call_count, 2)
        reader.file.assert_not_called()
        reader.close.assert_called_once()

    def test_profile_failure_is_distinct_and_never_reprompts(self):
        reader = self.reader()
        prompt = mock.Mock(side_effect=["fictional-password", "C:/fictional/asc.p8"])
        with (
            mock.patch.object(
                intake.signing,
                "_profile_container",
                side_effect=ValueError("private-sentinel"),
            ),
            self.assertRaisesRegex(intake.Rejected, "^PROFILE_CONTAINER_REJECTED$"),
        ):
            self.invoke(reader, prompt=prompt, include_login=False)
        self.assertEqual(prompt.call_count, 2)
        reader.close.assert_called_once()

    def test_signing_material_failure_never_reprompts_and_hides_exception(self):
        reader = self.reader()
        prompt = mock.Mock(side_effect=["fictional-password", "C:/fictional/asc.p8"])
        with self.assertRaisesRegex(intake.Rejected, "^SIGNING_MATERIAL_REJECTED$"):
            self.invoke(
                reader,
                prompt=prompt,
                include_login=False,
                binding_error=ValueError("private-sentinel"),
            )
        self.assertEqual(prompt.call_count, 2)
        self.assertEqual(reader.file.call_count, 4)
        reader.close.assert_called_once()

    def test_binding_stage_propagates_without_another_password_or_asc_parse(self):
        for reason in intake.signing.BINDING_REASONS:
            reader = self.reader()
            prompt = mock.Mock(
                side_effect=["fictional-password", "C:/fictional/asc.p8"]
            )
            with (
                mock.patch.object(intake.inputs, "load_asc_key") as asc,
                self.assertRaisesRegex(intake.Rejected, "^" + reason + "$"),
            ):
                self.invoke(
                    reader,
                    prompt=prompt,
                    include_login=False,
                    binding_error=intake.signing.Rejected(reason),
                )
            self.assertEqual(prompt.call_count, 2)
            reader.close.assert_called_once()
            asc.assert_not_called()

    def test_payload_frame_rejection_is_distinct_from_certificate_binding(self):
        reader = self.reader()
        prompt = mock.Mock(side_effect=["fictional-password", "C:/fictional/asc.p8"])
        with (
            mock.patch.object(
                intake.signing,
                "frame",
                side_effect=[b"fictional", RuntimeError("private-sentinel")],
            ),
            self.assertRaisesRegex(intake.Rejected, "^SIGNING_FRAME_REJECTED$"),
        ):
            self.invoke(reader, prompt=prompt, include_login=False)
        self.assertEqual(prompt.call_count, 2)
        reader.close.assert_called_once()

    def test_separated_material_and_hidden_only_three_inputs(self):
        reader = self.reader()
        prompt = mock.Mock(
            side_effect=[
                "fictional-password",
                "C:/fictional/asc.p8",
                "C:/fictional/login.p8",
            ]
        )
        result = self.invoke(reader, prompt=prompt)
        self.assertEqual(prompt.call_count, 3)
        self.assertEqual(
            result.signing["profile_uuid"], "11111111-1111-1111-1111-111111111111"
        )
        self.assertNotIn(result.apple_login.pem, result.signing.values())
        self.assertNotEqual(result.asc.pem, result.apple_login.pem)
        self.assertNotIn("fictional", repr(result))
        reader.verify.assert_called_once()
        reader.close.assert_called_once()
        self.assertEqual(reader.file.call_args_list[2].args[1], 262144)

    def test_private_paths_supplied_no_reprompt(self):
        prompt = mock.Mock(return_value="fictional-password")
        self.invoke(
            self.reader(),
            self.config(
                asc_path="C:/fictional/a.p8", apple_login_path="C:/fictional/b.p8"
            ),
            prompt,
        )
        prompt.assert_called_once()

    def test_errors_and_close_are_sanitized(self):
        for reason in (
            "ACL_REJECTED",
            "INPUT_CHANGED",
            "METADATA_REJECTED",
            "private-sentinel",
        ):
            reader = self.reader()
            reader.file.side_effect = intake.custody.CustodyError(reason)
            with self.assertRaises(intake.Rejected) as error:
                self.invoke(reader)
            self.assertNotIn("private-sentinel", str(error.exception))
            reader.close.assert_called_once()
        reader = self.reader()
        reader.close.side_effect = OSError("private-sentinel")
        with self.assertRaisesRegex(intake.Rejected, "^CLOSE_UNRESOLVED$"):
            self.invoke(reader)

    def test_same_path_wrong_extension_and_password(self):
        for prompts in (
            ["fictional", "C:/fictional/a.p8", "C:/fictional/a.p8"],
            ["fictional", "C:/fictional/a.txt", "C:/fictional/b.p8"],
            ["x" * 1025],
        ):
            reader = self.reader()
            with self.assertRaises(intake.Rejected):
                self.invoke(reader, prompt=mock.Mock(side_effect=prompts))
            reader.file.assert_not_called()
            reader.close.assert_called_once()

    def test_same_key_rejected(self):
        reader = self.reader()
        values = list(reader.file.side_effect)
        values[-1] = values[-2]
        reader.file.side_effect = values
        with self.assertRaisesRegex(intake.Rejected, "^KEY_REUSE_REJECTED$"):
            self.invoke(reader)

    def test_native_metadata_keeps_all_guards_and_larger_profile(self):
        native = object.__new__(intake.IntakeNative)
        path = Path("C:/fictional/profile.mobileprovision")
        state = dict(name=str(path), kind=1, attributes=0, links=1, size=100000)

        def final(handle, buffer, length, flags):
            buffer.value = state["name"]
            return len(buffer.value)

        def info(handle, pointer):
            value = c.cast(pointer, c.POINTER(intake.custody.FileInfo)).contents
            value.attributes = state["attributes"]
            value.links = state["links"]
            value.size_low = state["size"]
            return True

        native.final = final
        native.info = info
        native.kind = lambda _: state["kind"]
        self.assertEqual(native.metadata(1, path, limit=262144)[3], 100000)
        with self.assertRaises(Exception):
            native.metadata(1, path)
        for field, value in (
            ("name", "C:/other"),
            ("kind", 2),
            ("attributes", 0x400),
            ("attributes", 0x10),
            ("links", 2),
            ("size", 0),
            ("size", 262145),
        ):
            old = state[field]
            state[field] = value
            with self.subTest(field=field), self.assertRaises(Exception):
                native.metadata(1, path, limit=262144)
            state[field] = old

    def test_reader_same_handle_read_and_change(self):
        native = mock.Mock()
        native.open_handle.return_value = 7
        native.metadata.return_value = (1, 2, 3, 3, 4, 5)
        native.seek.return_value = True

        def read(handle, buffer, size, count, _):
            self.assertEqual(handle, 7)
            buffer.raw = b"abc"
            c.cast(count, c.POINTER(intake.custody.w.DWORD)).contents.value = 3
            return True

        native.read.side_effect = read
        reader = intake.Reader(lambda: native)
        path = Path("C:/fictional/a.p8")
        reader.directories.add(path.parent)
        self.assertEqual(reader.file(path, 4096), b"abc")
        reader.verify()
        native.metadata.return_value = (1, 2, 3, 3, 4, 6)
        with self.assertRaisesRegex(intake.Rejected, "^INPUT_CHANGED$"):
            reader.verify()
        reader.close()
        native.close.assert_called_once_with(7)

    def test_parent_acl_failure_closes_opened_handles(self):
        native = mock.Mock()
        native.open_handle.side_effect = range(1, 20)
        native.acl.side_effect = intake.custody.CustodyError("ACL_REJECTED")
        reader = intake.Reader(lambda: native)
        with (
            mock.patch.object(intake.preparation, "safe_directory"),
            self.assertRaises(Exception),
        ):
            reader.directory(Path("C:/fictional/private"))
        count = len(reader.handles)
        reader.close()
        self.assertEqual(native.close.call_count, count)
        self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
