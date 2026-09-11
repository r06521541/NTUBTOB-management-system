"""Endogenous no-account macOS codesign proof, not Apple distribution readiness."""

import json
import os
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools import ios_certificate_preparation as preparation
from tools import ios_pkcs12_compatibility as frames
from tools import ios_xcode_feasibility as bounded

SOURCE = Path(__file__).resolve().parent / "native/ios_fictional_signing.swift"
MARKER_KEYS = (
    "marker_internal_component",
    "marker_interaction",
    "marker_authentication",
    "marker_identity",
    "marker_chain",
    "marker_format",
    "marker_permission",
    "marker_resource_fork",
)


def empty_observation():
    return {
        "codesign_exit": "NOT_RUN",
        "codesign_output": "NOT_READ",
        **{key: False for key in MARKER_KEYS},
    }


EXTRA_PHASES = frozenset(
    {
        "signing_application",
        "fixture_canonical",
        "fixture_stat",
        "fixture_owner",
        "fixture_mode",
        "fixture_regular",
        "fixture_size",
        "codesign_launch",
        "codesign_timeout",
        "codesign_exit",
        "codesign_pipe",
        "codesign_output",
        "requirement",
        "signature_binding",
        "signed_code",
        "signing_info",
        "signed_certificate_count",
        "signed_certificate_der",
        "tamper_write",
        "signed_size",
        "tamper_marker",
        "tamper_rejected",
    }
)


def fictional_material():
    """Fresh self-signed CodeSigning fixture, no Apple chain or trust claims."""
    x509, hashes, serialization, rsa = preparation.dependencies()
    from cryptography.hazmat.primitives.serialization import pkcs12

    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(x509.NameOID.COMMON_NAME, "fictional-task197-signing")]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, False, False, False, False),
            True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CODE_SIGNING]), True
        )
        .sign(key, hashes.SHA256())
    )
    p12 = pkcs12.serialize_key_and_certificates(
        b"fictional-task197",
        key,
        certificate,
        None,
        serialization.BestAvailableEncryption(b"fictional-new-password"),
    )
    der = certificate.public_bytes(serialization.Encoding.DER)
    return p12, der, b"fictional-wrong-certificate"


def native_detail(output):
    try:

        def unique(pairs):
            value = dict(pairs)
            if len(value) != len(pairs):
                raise ValueError
            return value

        if type(output) is not bytes or len(output) > 2048:
            raise ValueError
        value = json.loads(output.decode("ascii"), object_pairs_hook=unique)
        fields = {key: set(values) for key, values in bounded.NATIVE_FIELDS.items()}
        fields["reason"].add("SIGNING_VERIFIED")
        fields["phase"].update(EXTRA_PHASES)
        fields["codesign_exit"] = {
            "NOT_RUN",
            "ZERO",
            "NONZERO",
            "SIGNAL",
            "TIMEOUT",
            "OUTPUT_STOP",
        }
        fields["codesign_output"] = {"NOT_READ", "BOUNDED", "OVERFLOW", "READ_FAILED"}
        for key in MARKER_KEYS:
            fields[key] = {False, True}
        if type(value) is not dict or value.keys() != fields.keys():
            raise ValueError
        if any(
            type(value[key]) is not (bool if key in MARKER_KEYS else str)
            or value[key] not in allowed
            for key, allowed in fields.items()
        ):
            raise ValueError
        if value["cleanup"] == "VERIFIED" and (
            value["cleanup_phase"] != "completed"
            or value["cleanup_error_class"] != "OS_SUCCESS"
        ):
            raise ValueError
        if value["codesign_output"] != "BOUNDED" and any(
            value[key] for key in MARKER_KEYS
        ):
            raise ValueError
        if value["reason"] == "SIGNING_VERIFIED" and (
            value["phase"] != "tamper_rejected"
            or value["error_class"] != "OS_SUCCESS"
            or value["cleanup"] != "VERIFIED"
            or value["codesign_exit"] != "ZERO"
            or value["codesign_output"] != "BOUNDED"
        ):
            raise ValueError
        return {key: value[key] for key in fields}
    except Exception:
        raise bounded.Rejected("OUTPUT_REJECTED") from None


def cleanup(root, identity):
    info = root.lstat()
    if (
        root.is_symlink()
        or (info.st_dev, info.st_ino) != identity
        or root.parent != bounded.os_temp_root()
        or not root.name.startswith("task-197-")
    ):
        raise bounded.Rejected("CLEANUP_UNRESOLVED")
    shutil.rmtree(root)
    if root.exists():
        raise bounded.Rejected("CLEANUP_UNRESOLVED")


def rehearse(*, _run=bounded.process):
    result = {
        "classification": "REHEARSAL_REJECTED",
        "stage": "preflight",
        "fictional_codesign_verified": False,
        "cleanup_verified": False,
        "positive_export_verified": False,
        "flutter_nested_signing_verified": False,
        "real_assets_verified": False,
        "real_signing_authorized": False,
        "signing_authorized": False,
        "upload_authorized": False,
        "release_authorized": False,
    }
    root = None
    active = False
    try:
        if platform.system() != "Darwin":
            raise bounded.Rejected("TOOLCHAIN_UNSUPPORTED")
        root = Path(
            tempfile.mkdtemp(prefix="task-197-", dir=bounded.os_temp_root())
        ).resolve()
        os.chmod(root, 0o700)
        identity = (root.stat().st_dev, root.stat().st_ino)
        result["toolchain"] = bounded.toolchain(_run, root)
        result["stage"] = "compile"
        native = bounded.safe_path(root, root / "native")
        source = bounded.safe_path(root, root / "fictional.c")
        fixture = bounded.safe_path(root, root / "fictional-mach-o")
        source.write_text(
            'volatile const char marker[] = "fictional-task197-tamper-marker"; int main(void) { return marker[0]; }\n',
            encoding="ascii",
        )
        bounded.checked(
            _run,
            ["/usr/bin/xcrun", "swiftc", str(SOURCE), "-o", str(native)],
            root,
            timeout=90,
        )
        bounded.checked(
            _run,
            ["/usr/bin/xcrun", "clang", str(source), "-o", str(fixture)],
            root,
            timeout=90,
        )
        os.chmod(fixture, 0o700)
        custody = bounded.safe_path(root, root / "custody")
        custody.mkdir(mode=0o700)
        # All build/dependency execution has ended before generating/importing keys.
        p12, certificate, wrong = fictional_material()
        for index, (payload, expected) in enumerate(
            (
                (frames.frame(p12, certificate), "SIGNING_VERIFIED"),
                (frames.frame(p12, wrong), "CERTIFICATE_MISMATCH"),
                (frames.frame(p12, certificate, True), "AUTH_REJECTED"),
            )
        ):
            result["stage"] = "native"
            result["native_case"] = index
            active = True
            code, output = _run([str(native)], cwd=custody, payload=payload, timeout=90)
            detail = native_detail(output)
            result["native_detail"] = detail
            if (
                code == 0
                and detail["cleanup"] in {"VERIFIED", "NOT_CREATED"}
                and not list(custody.iterdir())
            ):
                active = False
            if (
                code != 0
                or detail["reason"] != expected
                or detail["cleanup"] != "VERIFIED"
                or active
            ):
                raise bounded.Rejected("CUSTODY_REJECTED")
        result["fictional_codesign_verified"] = True
        result["classification"] = "FICTIONAL_SIGNING_VERIFIED"
        result["stage"] = "completed"
    except KeyboardInterrupt:
        result["classification"] = "CANCELLED"
    except Exception as error:
        result["classification"] = (
            error.args[0]
            if isinstance(error, bounded.Rejected)
            and len(error.args) == 1
            and error.args[0] in bounded.REASONS
            else "REHEARSAL_REJECTED"
        )
    finally:
        if root is not None:
            try:
                cleanup(root, identity)
                result["cleanup_verified"] = not active
                if active:
                    result["classification"] = "CLEANUP_UNRESOLVED"
            except Exception:
                result["classification"] = "CLEANUP_UNRESOLVED"
    return result


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    result = (
        rehearse()
        if args == ["--rehearsal"]
        else {"classification": "ARGUMENTS_REJECTED"}
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["classification"] == "FICTIONAL_SIGNING_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
