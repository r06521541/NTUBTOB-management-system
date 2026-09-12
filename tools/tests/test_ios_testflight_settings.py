import io
import json
import os
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import Mock, patch

from tools import ios_testflight_settings as settings


class SettingsTests(unittest.TestCase):
    def values(self):
        return {
            "apple_team_id": "FICTTEAM01",
            "asc_key_id": "FICTKEY001",
            "asc_issuer_id": "11111111-1111-4111-8111-111111111111",
            "google_ios_client_id": "123-ios.apps.googleusercontent.com",
            "owner_email": "owner@example.invalid",
            "asc_p8_path": '"C:/fictional/private/asc.p8"',
        }

    def parse(self, raw):
        with patch.object(settings.intake, "Path", PureWindowsPath):
            return settings.parse(raw, google_web="456-web.apps.googleusercontent.com")

    def test_exact_metadata_no_secret_or_authority_and_quotes(self):
        values = self.values()
        result = self.parse(json.dumps(values).encode())
        self.assertEqual(
            result["asc_p8_path"], str(PureWindowsPath("C:/fictional/private/asc.p8"))
        )
        self.assertEqual(result["asc_key_id"], values["asc_key_id"])
        self.assertEqual(set(json.loads(settings.TEMPLATE)), set(values))
        self.assertEqual(set(json.loads(settings.TEMPLATE).values()), {""})

    def test_all_invalid_fields_reported_without_values(self):
        values = self.values() | {
            "apple_team_id": "private-sentinel",
            "asc_key_id": "bad-key",
        }
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            with self.assertRaisesRegex(
                settings.Rejected, "^SETTINGS_FIELDS_REJECTED$"
            ):
                self.parse(json.dumps(values).encode())
        self.assertIn("field=APPLE_TEAM", output.getvalue())
        self.assertIn("field=ASC_KEY_ID", output.getvalue())
        self.assertNotIn("private-sentinel", output.getvalue())
        self.assertNotIn("bad-key", output.getvalue())
        self.assertNotIn("field=OWNER_EMAIL", output.getvalue())

    def test_invalid_json_duplicate_unknown_and_secret_fields_rejected(self):
        for raw in (
            b"",
            b"{" + b"x" * 65536,
            b"{broken",
            b"[]",
            b"{}",
            b'{"apple_team_id":"x","apple_team_id":"y"}',
            b"\xff",
            json.dumps(self.values() | {"password": "fictional-secret"}).encode(),
            json.dumps(self.values() | {"release_authorized": True}).encode(),
        ):
            with (
                self.subTest(size=len(raw)),
                self.assertRaisesRegex(settings.Rejected, "^SETTINGS_JSON_REJECTED$"),
            ):
                self.parse(raw)

    def test_utf8_bom_from_windows_editor_is_supported(self):
        self.assertEqual(
            self.parse(b"\xef\xbb\xbf" + json.dumps(self.values()).encode())[
                "apple_team_id"
            ],
            "FICTTEAM01",
        )

    def test_load_same_custody_handle_and_close(self):
        reader = Mock()
        reader.file.return_value = json.dumps(self.values()).encode()
        with (
            patch.object(
                settings.preparation,
                "local_app_data",
                return_value=PureWindowsPath("C:/fictional"),
            ),
            patch.object(settings.intake, "Path", PureWindowsPath),
        ):
            settings.load(
                google_web="456-web.apps.googleusercontent.com",
                reader_factory=lambda: reader,
            )
        reader.file.assert_called_once_with(
            PureWindowsPath("C:/fictional")
            / settings.preparation.DIRECTORY
            / settings.FILENAME,
            65536,
        )
        reader.verify.assert_called_once()
        reader.close.assert_called_once()

    def test_acl_and_close_fail_closed_without_parse_or_secret_echo(self):
        for phase in ("directory", "file", "verify", "close"):
            reader = Mock()
            reader.file.return_value = json.dumps(self.values()).encode()
            getattr(reader, phase).side_effect = settings.intake.Rejected(
                "ACL_REJECTED"
            )
            with (
                patch.object(
                    settings.preparation,
                    "local_app_data",
                    return_value=PureWindowsPath("C:/fictional"),
                ),
                self.assertRaises(settings.Rejected),
            ):
                settings.load(google_web="fictional", reader_factory=lambda: reader)
            reader.close.assert_called_once()

    @unittest.skipUnless(os.name == "nt", "native Windows ACL / handle contract")
    def test_real_windows_blank_creation_edit_read_and_never_overwrite(self):
        # Disposable fictional data only; never the Owner's KnownFolder assets.
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve(strict=True)
            root = parent / settings.preparation.DIRECTORY
            root.mkdir()
            settings.preparation.secure_acl(root, establish=True)
            with patch.object(
                settings.preparation, "local_app_data", return_value=parent
            ):
                settings.prepare()
                path = root / settings.FILENAME
                self.assertEqual(path.read_bytes(), settings.TEMPLATE)
                with self.assertRaisesRegex(settings.Rejected, "^HANDLE_REJECTED$"):
                    settings.prepare()
                self.assertEqual(path.read_bytes(), settings.TEMPLATE)
                path.write_text(json.dumps(self.values()), encoding="utf-8-sig")
                actual = settings.load(google_web="456-web.apps.googleusercontent.com")
                self.assertEqual(actual["apple_team_id"], "FICTTEAM01")
                # Oversized edited metadata is rejected by native custody before parsing.
                path.write_bytes(b"x" * 65537)
                with self.assertRaisesRegex(settings.Rejected, "^METADATA_REJECTED$"):
                    settings.load(google_web="456-web.apps.googleusercontent.com")

    def test_prepare_creation_failure_never_writes_or_repairs(self):
        reader = Mock(handles=[], records=[])
        reader.native.open_handle.side_effect = settings.custody.CustodyError(
            "HANDLE_REJECTED"
        )
        with (
            patch.object(
                settings.preparation,
                "local_app_data",
                return_value=PureWindowsPath("C:/fictional"),
            ),
            patch.object(settings.preparation, "secure_acl") as repair,
            self.assertRaisesRegex(settings.Rejected, "^HANDLE_REJECTED$"),
        ):
            settings.prepare(reader_factory=lambda: reader)
        reader.native.write.assert_not_called()
        reader.close.assert_called_once()
        repair.assert_not_called()


if __name__ == "__main__":
    unittest.main()
