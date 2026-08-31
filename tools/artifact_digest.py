"""Canonical text and explicit raw-binary SHA-256 helpers for new artifacts."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional, Sequence

MAX_MANIFEST_BYTES = 65_536
MAX_MANIFEST_ENTRIES = 512
MAX_MANIFEST_NAME_BYTES = 1024
READ_CHUNK_BYTES = 65_536
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class ArtifactDigestError(ValueError):
    """An artifact digest or checksum manifest was invalid."""


@dataclass(frozen=True)
class ManifestEntry:
    sha256: str
    name: str


def digest_bytes(source: bytes, *, text: bool) -> str:
    if not isinstance(source, bytes) or not isinstance(text, bool):
        raise TypeError("digest input and mode must be explicit")
    payload = source.replace(b"\r\n", b"\n") if text else source
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path, *, text: bool, chunk_size: int = READ_CHUNK_BYTES) -> str:
    if not isinstance(text, bool):
        raise TypeError("digest mode must be explicit")
    if not 1 <= chunk_size <= 1024 * 1024:
        raise ValueError("digest chunk size is out of bounds")
    digest = hashlib.sha256()
    pending_carriage_return = False
    with path.open("rb") as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            if not text:
                digest.update(chunk)
                continue
            if pending_carriage_return:
                chunk = b"\r" + chunk
                pending_carriage_return = False
            if chunk.endswith(b"\r"):
                chunk = chunk[:-1]
                pending_carriage_return = True
            digest.update(chunk.replace(b"\r\n", b"\n"))
    if pending_carriage_return:
        digest.update(b"\r")
    return digest.hexdigest()


def _manifest_name(value: str) -> str:
    if (
        not value
        or len(value.encode("ascii")) > MAX_MANIFEST_NAME_BYTES
        or not value.isprintable()
        or "\\" in value
        or re.fullmatch(r"[A-Za-z0-9._/-]+", value) is None
    ):
        raise ArtifactDigestError("checksum manifest name is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ArtifactDigestError("checksum manifest name is invalid")
    normalized = "/".join(path.parts)
    if normalized != value:
        raise ArtifactDigestError("checksum manifest name is invalid")
    return normalized


def parse_manifest_bytes(source: bytes) -> tuple[ManifestEntry, ...]:
    if not isinstance(source, bytes):
        raise TypeError("checksum manifest must be bytes")
    if not 1 <= len(source) <= MAX_MANIFEST_BYTES:
        raise ArtifactDigestError("checksum manifest size is invalid")
    canonical = source.replace(b"\r\n", b"\n")
    if b"\r" in canonical or any(
        byte < 32 and byte != 10 or byte == 127 for byte in canonical
    ):
        raise ArtifactDigestError("checksum manifest line endings are invalid")
    try:
        lines = canonical.decode("ascii").splitlines()
    except UnicodeDecodeError:
        raise ArtifactDigestError("checksum manifest encoding is invalid") from None
    if not 1 <= len(lines) <= MAX_MANIFEST_ENTRIES or any(not line for line in lines):
        raise ArtifactDigestError("checksum manifest entry count is invalid")
    entries = []
    names = set()
    for line in lines:
        digest, separator, raw_name = line.partition("  ")
        if not separator or SHA256_PATTERN.fullmatch(digest) is None:
            raise ArtifactDigestError("checksum manifest entry is invalid")
        name = _manifest_name(raw_name)
        comparable_name = name.casefold()
        if comparable_name in names:
            raise ArtifactDigestError("checksum manifest contains duplicate names")
        names.add(comparable_name)
        entries.append(ManifestEntry(digest, name))
    return tuple(entries)


def load_manifest(path: Path) -> tuple[ManifestEntry, ...]:
    with path.open("rb") as source:
        payload = source.read(MAX_MANIFEST_BYTES + 1)
    return parse_manifest_bytes(payload)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    digest_parser = subparsers.add_parser("digest")
    digest_parser.add_argument("path", type=Path)
    mode = digest_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--text", action="store_true")
    mode.add_argument("--binary", action="store_true")
    manifest_parser = subparsers.add_parser("parse-manifest")
    manifest_parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "digest":
            print(digest_file(args.path, text=args.text))
        else:
            entries = load_manifest(args.path)
            print(f"valid checksum manifest: {len(entries)} entries")
    except (ArtifactDigestError, OSError, TypeError, ValueError) as error:
        print(f"artifact digest failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
