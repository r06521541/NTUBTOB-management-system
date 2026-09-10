"""Memory-only restrictive CMS profile verification. No live asset intake CLI.

ASN.1 parsing grants no trust. Only the fixed production native build may supply
signature/chain evidence; this is not parity with Apple's private profile policy.
"""

import base64
import contextlib
import hashlib
import json
import platform
import struct
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from tools import apple_distribution_trust, ios_profile_validation

MAX_CMS = 1048576
MAX_OUTPUT = 700000
SOURCE = Path(__file__).resolve().parent / "native" / "ios_profile_cms_verify.swift"
LEAF_CN = "Apple iPhone OS Provisioning Profile Signing"
INTERMEDIATE_CN = "Apple iPhone Certification Authority"
REASONS = frozenset(
    {
        "CMS_STRUCTURE_REJECTED",
        "DEPENDENCY_REJECTED",
        "TIME_REJECTED",
        "PLATFORM_UNSUPPORTED",
        "NATIVE_COMPILE_FAILED",
        "NATIVE_TIMEOUT",
        "NATIVE_OUTPUT_REJECTED",
        "CMS_SIGNATURE_REJECTED",
        "CMS_TRUST_REJECTED",
        "CMS_PURPOSE_REJECTED",
        "CMS_BINDING_REJECTED",
        "PROFILE_CONTENT_REJECTED",
        "CMS_CHECK_REJECTED",
        "TEST_BUILD_REJECTED",
    }
)


class Rejected(Exception):
    pass


DIAGNOSTIC_STAGES = frozenset(
    {
        "CMS_SIZE_REJECTED",
        "CMS_DEPENDENCY_REJECTED",
        "CMS_DECODE_REJECTED",
        "CMS_CONTAINER_REJECTED",
        "CMS_SCHEMA_REJECTED",
        "CMS_ALGORITHM_REJECTED",
        "CMS_ATTRIBUTES_REJECTED",
        "CMS_CERTIFICATES_REJECTED",
        "CMS_CANONICAL_REJECTED",
        "CMS_UNKNOWN_REJECTED",
    }
)


def _dependencies():
    import asn1crypto
    import cryptography
    from asn1crypto import cms
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    if asn1crypto.__version__ != "1.5.1" or cryptography.__version__ != "50.0.0":
        raise Rejected("DEPENDENCY_REJECTED")
    return cms, x509, serialization


def preflight(data):
    """Fully materialize the permitted ASN.1 tree and force canonical DER.

    No encrypted/other content reaches CMSDecoder. This deliberately excludes
    CRLs, unsigned attributes, alternative certificate choices and non-RSA/SHA256.
    """
    stage = "CMS_SIZE_REJECTED"
    try:
        if type(data) is not bytes or not 0 < len(data) <= MAX_CMS:
            raise ValueError
        stage = "CMS_DEPENDENCY_REJECTED"
        cms, x509, serialization = _dependencies()
        from asn1crypto import core

        stage = "CMS_DECODE_REJECTED"
        document = cms.ContentInfo.load(data, strict=True)
        stage = "CMS_CONTAINER_REJECTED"
        if document["content_type"].native != "signed_data":
            raise ValueError
        signed = document["content"]
        if (
            signed["version"].native != "v1"
            or signed["encap_content_info"]["content_type"].native != "data"
        ):
            raise ValueError
        payload = signed["encap_content_info"]["content"].native
        if type(payload) is not bytes or not 0 < len(payload) <= 262144:
            raise ValueError
        stage = "CMS_SCHEMA_REJECTED"
        if (
            not isinstance(signed["crls"], core.Void)
            or len(signed["signer_infos"]) != 1
            or not 2 <= len(signed["certificates"]) <= 3
        ):
            raise ValueError
        _materialize(document)
        stage = "CMS_ALGORITHM_REJECTED"
        algorithms = signed["digest_algorithms"]
        if len(algorithms) != 1 or algorithms[0]["algorithm"].native != "sha256":
            raise ValueError
        signer = signed["signer_infos"][0]
        if (
            signer["version"].native != "v1"
            or signer["sid"].name != "issuer_and_serial_number"
            or not isinstance(signer["unsigned_attrs"], core.Void)
        ):
            raise ValueError
        if (
            signer["digest_algorithm"]["algorithm"].native != "sha256"
            or signer["signature_algorithm"]["algorithm"].native
            not in {"rsassa_pkcs1v15", "sha256_rsa"}
            or not 256 <= len(signer["signature"].native) <= 512
        ):
            raise ValueError
        for algorithm in (
            algorithms[0],
            signer["digest_algorithm"],
            signer["signature_algorithm"],
        ):
            if algorithm["parameters"].native is not None:
                raise ValueError
        stage = "CMS_ATTRIBUTES_REJECTED"
        attrs = signer["signed_attrs"]
        if not 2 <= len(attrs) <= 3:
            raise ValueError
        seen = set()
        for attribute in attrs:
            name = attribute["type"].native
            if (
                name not in {"content_type", "message_digest", "signing_time"}
                or name in seen
                or len(attribute["values"]) != 1
            ):
                raise ValueError
            seen.add(name)
            value = attribute["values"][0].native
            if name == "content_type" and value != "data":
                raise ValueError
            if name == "message_digest" and (
                type(value) is not bytes or len(value) != 32
            ):
                raise ValueError
            if name == "signing_time" and not isinstance(value, datetime):
                raise ValueError
        if not {"content_type", "message_digest"} <= seen:
            raise ValueError
        stage = "CMS_CERTIFICATES_REJECTED"
        certificates = []
        matches = []
        for choice in signed["certificates"]:
            if choice.name != "certificate":
                raise ValueError
            certificate = choice.chosen
            encoded = certificate.dump(force=True)
            if len(encoded) > 65536:
                raise ValueError
            parsed = x509.load_der_x509_certificate(encoded)
            if parsed.public_bytes(serialization.Encoding.DER) != encoded:
                raise ValueError
            certificates.append(encoded)
            sid = signer["sid"].chosen
            if (
                certificate.issuer.dump() == sid["issuer"].dump()
                and certificate.serial_number == sid["serial_number"].native
            ):
                matches.append(encoded)
        if len(set(certificates)) != len(certificates) or len(matches) != 1:
            raise ValueError
        # .native forces every remaining allowed field, including certificate
        # structures, before force=True rebuilds descendants instead of cached BER.
        stage = "CMS_CANONICAL_REJECTED"
        document.native
        if document.dump(force=True) != data:
            raise ValueError
        return {
            "cms": data,
            "payload": payload,
            "certificates": certificates,
            "signer": matches[0],
        }
    except Rejected as error:
        error.diagnostic_stage = stage
        raise
    except Exception as error:
        rejected = Rejected("CMS_STRUCTURE_REJECTED")
        rejected.diagnostic_stage = (
            stage
            if isinstance(
                error,
                (
                    ValueError,
                    TypeError,
                    KeyError,
                    IndexError,
                    OverflowError,
                    RecursionError,
                ),
            )
            else "CMS_UNKNOWN_REJECTED"
        )
        raise rejected from None


def _materialize(document):
    # Walk library-defined schemas, NOT a custom ASN.1 decoder. Sequence's
    # permissive unknown trailing children must not survive canonical re-encode.
    from asn1crypto import core

    count = 0

    def visit(node, depth):
        nonlocal count
        count += 1
        if depth > 32 or count > 4096:
            raise ValueError
        if isinstance(node, core.Choice):
            visit(node.chosen, depth + 1)
        elif isinstance(node, core.Sequence):
            if len(node) != len(node._fields):
                raise ValueError
            for index in range(len(node)):
                visit(node[index], depth + 1)
        elif isinstance(node, core.SequenceOf):
            if len(node) > 128:
                raise ValueError
            for child in node:
                visit(child, depth + 1)
        elif isinstance(node, core.Any):
            visit(node.parsed, depth + 1)
        elif (
            isinstance(node, (core.ParsableOctetString, core.ParsableOctetBitString))
            and node._parsed is not None
        ):
            visit(node.parsed, depth + 1)
        else:
            node.native

    visit(document, 0)


def _instant(now):
    if type(now) is not datetime or now.utcoffset() is None:
        raise Rejected("TIME_REJECTED")
    instant = now.astimezone(timezone.utc)
    if not 2001 <= instant.year <= 9998:
        raise Rejected("TIME_REJECTED")
    return instant


def _production_root():
    _, x509, serialization = _dependencies()
    root = x509.load_pem_x509_certificate(
        apple_distribution_trust.ROOT_PEM
    ).public_bytes(serialization.Encoding.DER)
    if hashlib.sha256(root).hexdigest() != apple_distribution_trust.ROOT_SHA256:
        raise Rejected("CMS_TRUST_REJECTED")
    return root


@contextlib.contextmanager
def _compile_native(*, _fictional_root=None):
    if platform.system() != "Darwin":
        raise Rejected("PLATFORM_UNSUPPORTED")
    try:
        if int(platform.mac_ver()[0].split(".")[0]) < 15:
            raise ValueError
    except Exception:
        raise Rejected("PLATFORM_UNSUPPORTED") from None
    root = _production_root() if _fictional_root is None else _fictional_root
    marker = "PRODUCTION" if _fictional_root is None else "FICTIONAL_ONLY"
    # Generated file contains fixed code plus PUBLIC anchor only, never CMS,
    # profile contents or private key material. Test marker cannot be overridden.
    with tempfile.TemporaryDirectory(prefix="cms-code-only-") as directory:
        source = Path(directory) / "main.swift"
        binary = Path(directory) / "cms-verify"
        source.write_text(
            'let compiledAnchor = "'
            + base64.b64encode(root).decode("ascii")
            + '"\nlet buildMarker = "'
            + marker
            + '"\n'
            + SOURCE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        try:
            result = subprocess.run(
                ["/usr/bin/xcrun", "swiftc", str(source), "-o", str(binary)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
                check=False,
            )
            if result.returncode:
                raise ValueError
        except Exception:
            raise Rejected("NATIVE_COMPILE_FAILED") from None
        yield binary


def _pipe(binary, request):
    """Bound both pipes, join workers and kill on timeout; never log raw output."""
    if type(request) is not bytes or len(request) > MAX_CMS + 12:
        raise Rejected("CMS_STRUCTURE_REJECTED")
    process = None
    output, errors, workers = [], [], []
    try:
        process = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin"},
        )

        def write():
            try:
                process.stdin.write(request)
                process.stdin.close()
            except Exception:
                errors.append(True)

        def read():
            try:
                output.append(process.stdout.read(MAX_OUTPUT + 1))
                if len(output[0]) > MAX_OUTPUT:
                    process.kill()
            except Exception:
                errors.append(True)

        workers = [
            threading.Thread(target=write, daemon=True),
            threading.Thread(target=read, daemon=True),
        ]
        for worker in workers:
            worker.start()
        process.wait(timeout=30)
        for worker in workers:
            worker.join(timeout=1)
        if (
            any(worker.is_alive() for worker in workers)
            or errors
            or process.returncode
            or not output
            or len(output[0]) > MAX_OUTPUT
        ):
            raise ValueError
        return output[0]
    except subprocess.TimeoutExpired:
        raise Rejected("NATIVE_TIMEOUT") from None
    except Exception:
        raise Rejected("NATIVE_OUTPUT_REJECTED") from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for worker in workers:
                worker.join(timeout=1)
            process.stdin.close()
            process.stdout.close()


def _native_verified(parsed, now, binary, *, _test_root=None):
    # Re-establish the structural boundary at the sole native-call site too;
    # a fabricated internal parsed dictionary must never bypass preflight.
    parsed = preflight(parsed["cms"])
    instant = _instant(now)
    request = (
        struct.pack(">dI", instant.timestamp(), len(parsed["cms"])) + parsed["cms"]
    )
    try:

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result

        result = json.loads(_pipe(binary, request), object_pairs_hook=unique)
        if type(result) is not dict or result.get("marker") != (
            "PRODUCTION" if _test_root is None else "FICTIONAL_ONLY"
        ):
            raise Rejected("TEST_BUILD_REJECTED")
        reason = result.get("reason")
        if reason != "VERIFIED":
            if set(result) != {"marker", "reason"} or reason not in {
                "CMS_SIGNATURE_REJECTED",
                "CMS_TRUST_REJECTED",
                "CMS_BINDING_REJECTED",
            }:
                raise ValueError
            raise Rejected(reason)
        if (
            set(result) != {"marker", "reason", "payload", "signer", "chain"}
            or type(result["chain"]) is not list
            or len(result["chain"]) != 3
        ):
            raise ValueError

        def decode(value, maximum):
            if type(value) is not str or len(value) > maximum * 2:
                raise ValueError
            decoded = base64.b64decode(value, validate=True)
            if len(decoded) > maximum:
                raise ValueError
            return decoded

        payload = decode(result["payload"], 262144)
        signer = decode(result["signer"], 65536)
        chain = [decode(value, 65536) for value in result["chain"]]
        root = _production_root() if _test_root is None else _test_root
        if (
            payload != parsed["payload"]
            or signer != parsed["signer"]
            or chain[0] != signer
            or chain[-1] != root
            or len(set(chain)) != 3
            or set(parsed["certificates"]) not in (set(chain[:2]), set(chain))
        ):
            raise Rejected("CMS_BINDING_REJECTED")
        _, x509, _ = _dependencies()
        certificates = [x509.load_der_x509_certificate(value) for value in chain]

        def cn(name, expected):
            return [
                item.value
                for item in name.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
            ] == [expected]

        if (
            not cn(certificates[0].subject, LEAF_CN)
            or not cn(certificates[0].issuer, INTERMEDIATE_CN)
            or not cn(certificates[1].subject, INTERMEDIATE_CN)
        ):
            raise Rejected("CMS_PURPOSE_REJECTED")
        return payload
    except Rejected:
        raise
    except Exception:
        raise Rejected("NATIVE_OUTPUT_REJECTED") from None


def _result(reason):
    success = reason == "CMS_PROFILE_VERIFIED_RESTRICTED"
    return {
        "classification": "CMS_PROFILE_VERIFIED_RESTRICTED" if success else "STOP",
        "reason": reason if success or reason in REASONS else "CMS_CHECK_REJECTED",
        "cms_signature_verified": success,
        "restricted_apple_chain_verified": success,
        "profile_content_verified": success,
        "apple_private_policy_verified": False,
        "revocation_verified": False,
        "private_key_possession_verified": False,
        "pkcs12_import_verified": False,
        "signing_authorized": False,
        "upload_authorized": False,
        "release_authorized": False,
    }


def verify_profile_cms(
    data, *, expected_bundle, expected_team, expected_certificate_der, now
):
    """No caller anchor/trust overrides, private files, CLI or payload results."""
    try:
        parsed = preflight(data)
        instant = _instant(now)
        with _compile_native() as binary:
            payload = _native_verified(parsed, instant, binary)
        content = ios_profile_validation.validate_profile(
            payload,
            expected_bundle=expected_bundle,
            expected_team=expected_team,
            expected_certificate_der=expected_certificate_der,
            now=instant,
        )
        if content["classification"] != "PROFILE_CONTENT_MATCH_ONLY":
            raise Rejected("PROFILE_CONTENT_REJECTED")
        return _result("CMS_PROFILE_VERIFIED_RESTRICTED")
    except Rejected as error:
        return _result(error.args[0] if error.args else "CMS_CHECK_REJECTED")
    except Exception:
        return _result("CMS_CHECK_REJECTED")
