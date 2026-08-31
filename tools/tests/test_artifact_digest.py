from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.artifact_digest import (
    MAX_MANIFEST_BYTES,
    MAX_MANIFEST_ENTRIES,
    ArtifactDigestError,
    ManifestEntry,
    digest_bytes,
    digest_file,
    parse_manifest_bytes,
)


class ArtifactDigestTest(unittest.TestCase):
    def test_text_digest_canonicalizes_only_crlf_while_binary_is_raw(self):
        lf = b"first\nsecond\n"
        crlf = b"first\r\nsecond\r\n"
        self.assertEqual(digest_bytes(lf, text=True), digest_bytes(crlf, text=True))
        self.assertNotEqual(
            digest_bytes(lf, text=False), digest_bytes(crlf, text=False)
        )
        self.assertNotEqual(
            digest_bytes(b"first\rsecond\n", text=True),
            digest_bytes(lf, text=True),
        )

    def test_file_digest_handles_crlf_across_bounded_chunk_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.txt"
            path.write_bytes(b"a\r\nb\r\n")
            self.assertEqual(
                digest_file(path, text=True, chunk_size=2),
                hashlib.sha256(b"a\nb\n").hexdigest(),
            )
            self.assertEqual(
                digest_file(path, text=False, chunk_size=2),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )

    def test_manifest_parser_accepts_lf_and_crlf_with_safe_relative_names(self):
        digest = "a" * 64
        lf = f"{digest}  artifact.sql\n{'b' * 64}  nested/tool.py\n".encode()
        expected = (
            ManifestEntry(digest, "artifact.sql"),
            ManifestEntry("b" * 64, "nested/tool.py"),
        )
        self.assertEqual(parse_manifest_bytes(lf), expected)
        self.assertEqual(parse_manifest_bytes(lf.replace(b"\n", b"\r\n")), expected)

    def test_manifest_parser_rejects_unsafe_ambiguous_or_unbounded_input(self):
        digest = "a" * 64
        cases = (
            b"",
            b"x" * (MAX_MANIFEST_BYTES + 1),
            f"{'A' * 64}  artifact.sql\n".encode(),
            f"{digest} *artifact.sql\n".encode(),
            f"{digest}  ../artifact.sql\n".encode(),
            f"{digest}  /artifact.sql\n".encode(),
            f"{digest}  nested\\artifact.sql\n".encode(),
            f"{digest}  artifact with spaces.sql\n".encode(),
            f"{digest}  nested//artifact.sql\n".encode(),
            f"{digest}  artifact.sql\rbroken\n".encode(),
            f"{digest}  artifact.sql\v{'b' * 64}  other.sql\n".encode(),
            f"{digest}  artifact.sql\n{digest}  artifact.sql\n".encode(),
            f"{digest}  Artifact.sql\n{digest}  artifact.sql\n".encode(),
            f"{digest}  artifact.sql\n\n".encode(),
            b"".join(
                f"{digest}  artifact-{index}.sql\n".encode()
                for index in range(MAX_MANIFEST_ENTRIES + 1)
            ),
            b"a" * 64 + b"  \xff\n",
        )
        for source in cases:
            with self.subTest(size=len(source)), self.assertRaises(ArtifactDigestError):
                parse_manifest_bytes(source)

    def test_digest_mode_must_be_explicit_boolean(self):
        with self.assertRaises(TypeError):
            digest_bytes(b"artifact", text=None)


if __name__ == "__main__":
    unittest.main()
