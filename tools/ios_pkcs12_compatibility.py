"""Fictional-only macOS 15 native compatibility evidence, never real asset intake.

Only compiled code is written to a temporary directory. Keys, encrypted fixtures
and passwords stay in memory/pipes; Python cannot promise memory zeroization.
"""

import json
import platform
import struct
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools import ios_certificate_packaging as packaging
from tools import ios_certificate_preparation as preparation

LIMIT = 65536
SOURCE = Path(__file__).resolve().parent / "native" / "ios_pkcs12_memory_import.swift"
OLD = b"fictional-old-password"
NEW = b"fictional-new-password"
NATIVE_REASONS = frozenset(
    {
        "MEMORY_IMPORT_VERIFIED",
        "AUTH_REJECTED",
        "DECODE_REJECTED",
        "IMPORT_REJECTED",
        "IDENTITY_REJECTED",
        "CERTIFICATE_MISMATCH",
        "KEY_REJECTED",
        "FRAME_REJECTED",
        "PLATFORM_UNSUPPORTED",
        "ARGUMENTS_REJECTED",
    }
)
REASONS = NATIVE_REASONS | {
    "NATIVE_COMPILE_FAILED",
    "NATIVE_COMPILE_TIMEOUT",
    "NATIVE_TIMEOUT",
    "NATIVE_OUTPUT_REJECTED",
    "NATIVE_CASE_FAILED",
    "FIXTURE_FAILED",
    "FICTITIOUS_NATIVE_IMPORT_VERIFIED",
}
STAGES = frozenset(
    {
        "preflight",
        "correct",
        "wrong_password",
        "malformed",
        "tampered",
        "mismatch",
        "oversized",
    }
)


class CompatibilityError(Exception):
    pass


def fictional_material():
    """Reuse the actual packaging core, with a wholly fictional signing chain."""
    x509, hashes, serialization, rsa = preparation.dependencies()
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    keys = [
        rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(3)
    ]

    def certificate(label, key, issuer=None, signer=None, depth=None):
        ca = depth is not None
        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, label)])
        builder = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(issuer.subject if issuer else name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=depth), True)
            .add_extension(
                x509.KeyUsage(not ca, False, False, False, False, ca, ca, False, False),
                True,
            )
        )
        if not ca:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CODE_SIGNING]), True
            )
            for oid in packaging.MARKERS:
                builder = builder.add_extension(
                    x509.UnrecognizedExtension(x509.ObjectIdentifier(oid), b"\x05\x00"),
                    True,
                )
        return builder.sign(signer or key, hashes.SHA256())

    root = certificate("fictional-root", keys[0], depth=1)
    intermediate = certificate("fictional-intermediate", keys[1], root, keys[0], 0)
    leaf = certificate("fictional-leaf", keys[2], intermediate, keys[1])
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(leaf.subject)
        .sign(keys[2], hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    encrypted = keys[2].private_bytes(
        pem,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(OLD),
    )
    p12 = packaging.package_material(
        leaf.public_bytes(pem),
        csr.public_bytes(pem),
        encrypted,
        OLD,
        NEW,
        root_pem=root.public_bytes(pem),
        intermediate_pem=intermediate.public_bytes(pem),
        now=now,
    )
    return (
        p12,
        leaf.public_bytes(serialization.Encoding.DER),
        root.public_bytes(serialization.Encoding.DER),
    )


def frame(p12, certificate, wrong_password=False):
    if (
        type(p12) is not bytes
        or type(certificate) is not bytes
        or not 0 < len(p12) <= LIMIT
        or not 0 < len(certificate) <= LIMIT
        or type(wrong_password) is not bool
    ):
        raise CompatibilityError("FRAME_REJECTED")
    return (
        struct.pack(">BII", int(wrong_password), len(p12), len(certificate))
        + p12
        + certificate
    )


def native_case(binary, payload):
    if type(payload) is not bytes or len(payload) > 2 * LIMIT + 9:
        raise CompatibilityError("FRAME_REJECTED")
    process = None
    output = []
    failed = []

    def write_input():
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except Exception:
            failed.append(True)

    def read_output():
        try:
            output.append(process.stdout.read(129))
            if len(output[0]) > 128:
                process.kill()
        except Exception:
            failed.append(True)

    try:
        process = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin"},
        )
        writer = threading.Thread(target=write_input, daemon=True)
        reader = threading.Thread(target=read_output, daemon=True)
        writer.start()
        reader.start()
        process.wait(timeout=30)
        writer.join(timeout=1)
        reader.join(timeout=1)
        if writer.is_alive() or reader.is_alive() or failed:
            raise CompatibilityError("NATIVE_OUTPUT_REJECTED")
    except subprocess.TimeoutExpired:
        raise CompatibilityError("NATIVE_TIMEOUT") from None
    except Exception:
        raise CompatibilityError("NATIVE_OUTPUT_REJECTED") from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            if "writer" in locals():
                writer.join(timeout=1)
                reader.join(timeout=1)
            process.stdin.close()
            process.stdout.close()
    if process.returncode != 0 or not output or len(output[0]) > 128:
        raise CompatibilityError("NATIVE_OUTPUT_REJECTED")
    for reason in NATIVE_REASONS:
        if output[0] == (reason + "\n").encode("ascii"):
            return reason
    raise CompatibilityError("NATIVE_OUTPUT_REJECTED")


def run_fictional_checks():
    if platform.system() != "Darwin":
        raise CompatibilityError("PLATFORM_UNSUPPORTED")
    try:
        if int(platform.mac_ver()[0].split(".")[0]) < 15:
            raise ValueError
    except ValueError:
        raise CompatibilityError("PLATFORM_UNSUPPORTED") from None
    # No material generation until the fixed source compiles against an SDK
    # exposing the real memory-only constant. Never substitute a string key.
    with tempfile.TemporaryDirectory(prefix="fictional-native-code-") as directory:
        binary = Path(directory) / "memory-import"
        try:
            compiled = subprocess.run(
                ["/usr/bin/xcrun", "swiftc", str(SOURCE), "-o", str(binary)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise CompatibilityError("NATIVE_COMPILE_TIMEOUT") from None
        except Exception:
            raise CompatibilityError("NATIVE_COMPILE_FAILED") from None
        if compiled.returncode != 0:
            raise CompatibilityError("NATIVE_COMPILE_FAILED")
        try:
            p12, leaf, other = fictional_material()
        except Exception:
            raise CompatibilityError("FIXTURE_FAILED") from None
        cases = (
            ("correct", frame(p12, leaf), "MEMORY_IMPORT_VERIFIED"),
            ("wrong_password", frame(p12, leaf, True), "AUTH_REJECTED"),
            (
                "malformed",
                frame(b"fictional-not-asn1", leaf),
                {"DECODE_REJECTED", "AUTH_REJECTED"},
            ),
            (
                "tampered",
                frame(p12[:-1] + bytes([p12[-1] ^ 1]), leaf),
                {"DECODE_REJECTED", "AUTH_REJECTED"},
            ),
            ("mismatch", frame(p12, other), "CERTIFICATE_MISMATCH"),
            ("oversized", struct.pack(">BII", 0, LIMIT + 1, 1), "FRAME_REJECTED"),
        )
        for stage, payload, expected in cases:
            try:
                allowed = expected if isinstance(expected, set) else {expected}
                if native_case(binary, payload) not in allowed:
                    raise CompatibilityError("NATIVE_CASE_FAILED")
            except CompatibilityError as error:
                raise CompatibilityError(error.args[0], stage) from None
    return "FICTITIOUS_NATIVE_IMPORT_VERIFIED"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    stage = "preflight"
    try:
        reason = "ARGUMENTS_REJECTED" if args else run_fictional_checks()
        if reason == "FICTITIOUS_NATIVE_IMPORT_VERIFIED":
            stage = "completed"
    except CompatibilityError as error:
        if len(error.args) == 2 and error.args[1] in STAGES:
            stage = error.args[1]
        reason = (
            error.args[0]
            if error.args and error.args[0] in REASONS
            else "NATIVE_OUTPUT_REJECTED"
        )
    except Exception:
        reason = "NATIVE_OUTPUT_REJECTED"
    result = {
        "classification": reason,
        "stage": stage,
        "real_assets_verified": False,
        "cms_authenticity_verified": False,
        "certificate_trust_verified": False,
        "real_private_key_possession_verified": False,
        "signing_authorized": False,
        "upload_authorized": False,
        "release_authorized": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if reason == "FICTITIOUS_NATIVE_IMPORT_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
