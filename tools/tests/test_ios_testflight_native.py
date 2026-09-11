"""Compile the real supervisor; invalid inputs only, never import signing keys."""

import json
import platform
import tempfile
import unittest
from pathlib import Path

from tools import ios_testflight_signing as signing
from tools import ios_xcode_feasibility as feasibility


@unittest.skipUnless(platform.system() == "Darwin", "requires macOS Security SDK")
class NativeInputTests(unittest.TestCase):
    def test_actual_supervisor_compiles_and_rejects_before_custody(self):
        repo = Path(__file__).resolve().parents[2]
        source = repo / "tools/native/ios_testflight_signing.swift"
        parent = feasibility.os_temp_root()
        with tempfile.TemporaryDirectory(prefix="task-198-", dir=parent) as folder:
            root = Path(folder).resolve(strict=True)
            self.assertEqual(root.parent, parent)
            root.chmod(0o700)
            native = root / "native"
            code, output = feasibility.process(
                ["/usr/bin/xcrun", "swiftc", str(source), "-o", str(native)],
                cwd=root,
                timeout=120,
            )
            # Compiler diagnostics concern committed public source only. No keys,
            # profile, token, runtime input or private environment enters this test.
            self.assertEqual(code, 0, output[:4096].decode("utf-8", errors="replace"))
            native.chmod(0o700)
            for payload in (b"", b"not-json", b"[]", b"{}", b'{"command":"false"}'):
                with self.subTest(case=payload):
                    code, output = feasibility.process(
                        [str(native), str(repo)], cwd=root, payload=payload, timeout=10
                    )
                    self.assertEqual(code, 0)
                    self.assertEqual(
                        json.loads(output),
                        {
                            "stage": "input",
                            "operation": "REJECTED",
                            "cleanup": "NOT_STARTED",
                        },
                    )
                    result = signing.decode_result(output)
                    self.assertEqual(result["classification"], "STOP")
                    self.assertFalse(result["upload_authorized"])
                    self.assertFalse(result["release_authorized"])
                    self.assertEqual(list(root.iterdir()), [native])


if __name__ == "__main__":
    unittest.main()
