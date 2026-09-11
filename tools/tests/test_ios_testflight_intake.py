import ctypes as c
import plistlib
import unittest
from pathlib import Path
from unittest import mock

from asn1crypto import cms
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tools import ios_testflight_intake as intake


class IntakeTests(unittest.TestCase):
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

    def invoke(self, reader, config=None, prompt=None):
        with (
            mock.patch.object(
                intake.preparation, "local_app_data", return_value=Path("C:/fictional")
            ),
            mock.patch.object(intake.signing, "_certificate_binding"),
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
            )

    def test_invalid_config_before_prompt(self):
        with self.assertRaises(intake.Rejected) as error:
            intake.collect(None, prompt=lambda _: self.fail("prompted"))
        self.assertEqual(str(error.exception), "INPUT_REJECTED")

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
