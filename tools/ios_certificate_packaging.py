"""Owner-only offline Apple Distribution packaging; no signing or upload.

PKCS12 encryption is not an independent custody boundary: restrictive native
ACLs remain mandatory. Python cannot guarantee private-memory zeroization.
"""

import base64
import hashlib
import json
import re
from datetime import datetime, timezone

from tools import ios_certificate_custody as custody
from tools import ios_certificate_pair as pair
from tools import ios_certificate_preparation as preparation

MARKERS = ("1.2.840.113635.100.6.1.4", "1.2.840.113635.100.6.1.7")
REASONS = frozenset(
    {
        "PACKAGING_REJECTED",
        "CHAIN_REJECTED",
        "PURPOSE_REJECTED",
        "PAIR_REJECTED",
        "KEY_REJECTED",
        "PASSWORD_REJECTED",
        "PINS_REJECTED",
        "REPOSITORY_REJECTED",
        "CONFIRMATION_REJECTED",
    }
)


class PackagingError(Exception):
    pass


def _reject(reason):
    raise PackagingError(reason)


def _certificate(data):
    if type(data) is not bytes or not 0 < len(data) <= custody.LIMIT:
        _reject("CHAIN_REJECTED")
    return pair._parse(data, certificate=True)


def pinned_anchors():
    from tools import apple_distribution_trust as trust

    _, _, serialization, _ = preparation.dependencies()
    for pem, pin in (
        (trust.ROOT_PEM, trust.ROOT_SHA256),
        (trust.INTERMEDIATE_PEM, trust.INTERMEDIATE_SHA256),
    ):
        certificate = _certificate(pem)
        if (
            hashlib.sha256(
                certificate.public_bytes(serialization.Encoding.DER)
            ).hexdigest()
            != pin
        ):
            _reject("PINS_REJECTED")
    return trust.ROOT_PEM, trust.INTERMEDIATE_PEM


def _verify_chain(leaf, intermediate, root, now):
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    if type(now) is not datetime or now.utcoffset() is None:
        _reject("CHAIN_REJECTED")
    now = now.astimezone(timezone.utc)
    standard = {x509.ExtensionOID.BASIC_CONSTRAINTS, x509.ExtensionOID.KEY_USAGE}
    leaf_known = (
        standard
        | {x509.ExtensionOID.EXTENDED_KEY_USAGE}
        | {x509.ObjectIdentifier(oid) for oid in MARKERS}
    )
    for certificate, issuer, is_root in (
        (root, root, True),
        (intermediate, root, False),
        (leaf, intermediate, False),
    ):
        key = issuer.public_key()
        if (
            certificate.issuer != issuer.subject
            or not isinstance(key, rsa.RSAPublicKey)
            or key.key_size < 2048
            or not certificate.not_valid_before_utc
            <= now
            <= certificate.not_valid_after_utc
        ):
            _reject("CHAIN_REJECTED")
        allowed_signatures = {
            "1.2.840.113549.1.1.11",
            "1.2.840.113549.1.1.12",
            "1.2.840.113549.1.1.13",
        }
        if is_root:
            allowed_signatures.add("1.2.840.113549.1.1.5")
        if certificate.signature_algorithm_oid.dotted_string not in allowed_signatures:
            _reject("CHAIN_REJECTED")
        key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            padding.PKCS1v15(),
            certificate.signature_hash_algorithm,
        )
        allowed = leaf_known if certificate is leaf else standard
        if any(
            extension.critical and extension.oid not in allowed
            for extension in certificate.extensions
        ):
            _reject("PURPOSE_REJECTED")
        constraints = certificate.extensions.get_extension_for_class(
            x509.BasicConstraints
        )
        usage = certificate.extensions.get_extension_for_class(x509.KeyUsage)
        if not constraints.critical or not usage.critical:
            _reject("PURPOSE_REJECTED")
        if certificate is not leaf:
            if not constraints.value.ca or not usage.value.key_cert_sign:
                _reject("CHAIN_REJECTED")
            if (
                constraints.value.path_length is not None
                and constraints.value.path_length < (1 if is_root else 0)
            ):
                _reject("CHAIN_REJECTED")
        else:
            if (
                constraints.value.ca
                or not usage.value.digital_signature
                or usage.value.key_cert_sign
                or usage.value.crl_sign
            ):
                _reject("PURPOSE_REJECTED")
            eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
            if not eku.critical or list(eku.value) != [
                x509.ExtendedKeyUsageOID.CODE_SIGNING
            ]:
                _reject("PURPOSE_REJECTED")
            for oid in MARKERS:
                marker = certificate.extensions.get_extension_for_oid(
                    x509.ObjectIdentifier(oid)
                )
                if not marker.critical:
                    _reject("PURPOSE_REJECTED")


def _encrypted_key(data, password):
    from cryptography.hazmat.primitives import serialization

    if type(data) is not bytes or not 0 < len(data) <= custody.LIMIT:
        _reject("KEY_REJECTED")
    normalized = data.replace(b"\r\n", b"\n")
    match = re.fullmatch(
        rb"-----BEGIN ENCRYPTED PRIVATE KEY-----\n([A-Za-z0-9+/=\n]+)-----END ENCRYPTED PRIVATE KEY-----\n?",
        normalized,
    )
    if not match:
        _reject("KEY_REJECTED")
    der = base64.b64decode(match[1].replace(b"\n", b""), validate=True)
    # Validate the outer DER envelope length, not the private-key ASN.1 schema.
    if len(der) < 2 or der[0] != 0x30:
        _reject("KEY_REJECTED")
    count = der[1] & 0x7F if der[1] & 0x80 else 0
    if count > 4 or (der[1] == 0x80) or len(der) < 2 + count:
        _reject("KEY_REJECTED")
    length = int.from_bytes(der[2 : 2 + count], "big") if count else der[1]
    if length + 2 + count != len(der) or (count and (der[2] == 0 or length < 128)):
        _reject("KEY_REJECTED")
    return serialization.load_der_private_key(der, password)


def package_material(
    certificate_bytes,
    csr_bytes,
    encrypted_key_bytes,
    old_password,
    new_password,
    *,
    root_pem,
    intermediate_pem,
    now,
):
    """Pure core; fictional trust may be injected only by tests, never the CLI."""
    try:
        _, hashes, serialization, rsa = preparation.dependencies()
        from cryptography.hazmat.primitives.serialization import pkcs12

        if (
            type(old_password) is not bytes
            or not 0 < len(old_password) <= 1024
            or type(new_password) is not bytes
            or not 16 <= len(new_password) <= 1024
        ):
            _reject("PASSWORD_REJECTED")
        if (
            pair.check_pair(certificate_bytes, csr_bytes, now=now)["classification"]
            != "PAIR_MATCH_ONLY"
        ):
            _reject("PAIR_REJECTED")
        leaf, intermediate, root = (
            _certificate(certificate_bytes),
            _certificate(intermediate_pem),
            _certificate(root_pem),
        )
        try:
            _verify_chain(leaf, intermediate, root, now)
        except PackagingError:
            raise
        except Exception:
            raise PackagingError("CHAIN_REJECTED") from None
        try:
            key = _encrypted_key(encrypted_key_bytes, old_password)
        except Exception:
            raise PackagingError("KEY_REJECTED") from None
        if (
            not isinstance(key, rsa.RSAPrivateKey)
            or key.key_size != 2048
            or key.public_key().public_numbers() != leaf.public_key().public_numbers()
        ):
            _reject("KEY_REJECTED")
        encryption = (
            serialization.PrivateFormat.PKCS12.encryption_builder()
            .kdf_rounds(200000)
            .key_cert_algorithm(pkcs12.PBES.PBESv2SHA256AndAES256CBC)
            .hmac_hash(hashes.SHA256())
            .build(new_password)
        )
        result = pkcs12.serialize_key_and_certificates(
            b"Apple Distribution", key, leaf, [intermediate, root], encryption
        )
        if len(result) > custody.LIMIT:
            _reject("PACKAGING_REJECTED")
        restored_key, restored_leaf, restored_chain = pkcs12.load_key_and_certificates(
            result, new_password
        )
        if (
            restored_key.private_numbers() != key.private_numbers()
            or restored_leaf != leaf
            or restored_chain != [intermediate, root]
        ):
            _reject("PACKAGING_REJECTED")
        try:
            pkcs12.load_key_and_certificates(result, None)
        except ValueError:
            return result
        _reject("PACKAGING_REJECTED")
    except PackagingError:
        raise
    except Exception:
        raise PackagingError("PACKAGING_REJECTED") from None


def repository(expected_commit):
    preparation.dependencies()
    if (
        not re.fullmatch("[0-9a-f]{40}", expected_commit)
        or preparation.git("rev-parse", "HEAD") != expected_commit
        or preparation.git("status", "--porcelain", "--untracked-files=all")
    ):
        _reject("REPOSITORY_REJECTED")


def operate(expected_commit, *, execute=False):
    session = None
    stage = "preflight"
    try:
        repository(expected_commit)
        root, intermediate = pinned_anchors()
        directory = preparation.local_app_data() / preparation.DIRECTORY
        stage = "metadata"
        with custody.Custody(directory) as session:
            if not execute:
                return result("preflight_passed", "METADATA_CHECKS_PASSED", stage)
            print(
                "PREFLIGHT_OK action=package_encrypted_pkcs12 target=local_apple_distribution inputs=3 output=distribution.p12 count=1"
            )
            print("commit=" + expected_commit)
            stage = "confirmation"
            if (
                preparation.hidden(
                    "Type PACKAGE P12 followed by a space and the exact commit (hidden): "
                )
                != "PACKAGE P12 " + expected_commit
            ):
                _reject("CONFIRMATION_REJECTED")
            repository(expected_commit)
            stage = "password_input"
            old = preparation.hidden("Existing key passphrase (hidden): ").encode(
                "utf-8"
            )
            new = preparation.hidden("New PKCS12 passphrase (hidden): ").encode("utf-8")
            repeat = preparation.hidden("Repeat new passphrase (hidden): ").encode(
                "utf-8"
            )
            if new != repeat or not 0 < len(old) <= 1024 or not 16 <= len(new) <= 1024:
                _reject("PASSWORD_REJECTED")
            stage = "crypto"
            material = package_material(
                *(session.read_input(name) for name in custody.INPUTS),
                old,
                new,
                root_pem=root,
                intermediate_pem=intermediate,
                now=datetime.now(timezone.utc),
            )
            stage = "output"
            session.write_output(material)
            return result("confirmed_success", "OFFLINE_PACKAGE_VERIFIED", stage)
    except (Exception, KeyboardInterrupt) as error:
        reason = "PACKAGING_REJECTED"
        if (
            isinstance(error, (PackagingError, custody.CustodyError))
            and str(error) in REASONS | custody.REASONS
        ):
            reason = str(error)
        return result(
            (
                "uncertain"
                if session is not None and session.output_attempted
                else "pre_execution_rejected"
            ),
            reason,
            stage,
        )
    finally:
        # Drop references; this is not a guarantee of memory zeroization.
        old = new = repeat = material = None


def result(classification, reason, stage="preflight"):
    return {
        "classification": classification,
        "reason": reason,
        "stage": stage,
        "offline_chain_verified": classification == "confirmed_success",
        "distribution_purpose_verified": classification == "confirmed_success",
        "private_key_match_verified": classification == "confirmed_success",
        "revocation_verified": False,
        "team_verified": False,
        "app_profile_verified": False,
        "signing_authorized": False,
        "upload_authorized": False,
        "release_authorized": False,
    }


def main(argv=None):
    parser = preparation.SafeParser(add_help=False, exit_on_error=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--execute", action="store_true")
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown:
            raise PackagingError()
        response = operate(args.expected_commit, execute=args.execute)
    except (Exception, KeyboardInterrupt, SystemExit):
        response = result("pre_execution_rejected", "PACKAGING_REJECTED")
    print(json.dumps(response, sort_keys=True))
    return (
        0
        if response["classification"] in ("confirmed_success", "preflight_passed")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
