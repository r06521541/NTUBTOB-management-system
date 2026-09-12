"""Bounded in-memory inputs, not a file reader, CMS gate or authorization.

The controller must obtain bytes through reviewed custody, keep the raw profile
separate, enforce distinct keys, and never log these objects or JWT values.
Python cannot guarantee zeroization. Key purpose/role cannot be inferred from
P256 bytes: Apple account metadata remains an independent controller check.
"""

import base64
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from tools import ios_certificate_preparation as preparation
from tools import ios_profile_validation as profiles

MAX_INPUT_BYTES = 65536
MAX_KEY_BYTES = 4096
ASC_TTL_SECONDS = 600
APPLE_LOGIN_TTL_SECONDS = 604800
REASONS = frozenset(
    {
        "DEPENDENCY_REJECTED",
        "INPUT_REJECTED",
        "TIME_REJECTED",
        "P12_REJECTED",
        "CERTIFICATE_REJECTED",
        "PROFILE_REJECTED",
        "KEY_REJECTED",
        "KEY_REUSE_REJECTED",
        "TOKEN_REJECTED",
    }
)


class InputError(Exception):
    def __init__(self, reason="INPUT_REJECTED"):
        super().__init__(reason if reason in REASONS else "INPUT_REJECTED")


@dataclass(frozen=True, repr=False)
class SigningMaterial:
    private_key: object
    certificate_der: bytes
    team: str
    bundle: str
    apple_trust_verified: bool = field(default=False, init=False)
    signing_authorized: bool = field(default=False, init=False)


@dataclass(frozen=True, repr=False)
class AscMaterial:
    private_key: object
    key_id: str
    issuer_id: str


@dataclass(frozen=True, repr=False)
class AppleLoginMaterial:
    private_key: object
    key_id: str
    team: str
    bundle: str


@dataclass(frozen=True, repr=False)
class PrivateJWT:
    value: str
    expires_at: datetime


def _dependencies():
    try:
        return preparation.dependencies()
    except Exception:
        raise InputError("DEPENDENCY_REJECTED") from None


def _bytes(value, limit=MAX_INPUT_BYTES):
    if type(value) is not bytes or not 0 < len(value) <= limit:
        raise InputError()


def _identifier(value):
    if type(value) is not str or not re.fullmatch(r"[A-Z0-9]{10}", value):
        raise InputError()


def _bundle(value):
    if (
        type(value) is not str
        or len(value) > 255
        or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+", value
        )
    ):
        raise InputError()


def _time(now):
    try:
        if type(now) is not datetime or now.utcoffset() != timedelta(0):
            raise ValueError()
        if now.timestamp() < 0:
            raise ValueError()
        return now.astimezone(timezone.utc)
    except Exception:
        raise InputError("TIME_REJECTED") from None


def validate_signing(p12, password, decoded_profile, *, team, bundle, now):
    """Match decrypted P12 and decoded XML contents; no certificate/CMS trust."""
    _, _, serialization, rsa = _dependencies()
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import pkcs12

    _bytes(p12)
    _bytes(password, 1024)
    _bytes(decoded_profile, profiles.MAX_PLIST_BYTES)
    _identifier(team)
    _bundle(bundle)
    instant = _time(now)
    try:
        # A single definite-length DER envelope: crypto parsers can ignore tails.
        if len(p12) < 2 or p12[0] != 0x30:
            raise ValueError()
        count = p12[1] & 0x7F if p12[1] & 0x80 else 0
        if p12[1] == 0x80 or count > 4 or len(p12) < 2 + count:
            raise ValueError()
        length = int.from_bytes(p12[2 : 2 + count], "big") if count else p12[1]
        if length + 2 + count != len(p12) or (
            count and (p12[2] == 0 or length < 128 or length < 256 ** (count - 1))
        ):
            raise ValueError()
        key, certificate, additional = pkcs12.load_key_and_certificates(p12, password)
        if key is None or certificate is None or len(additional) > 8:
            raise ValueError()
        # Reject unprotected P12 even if a supplied password happened to be ignored.
        try:
            pkcs12.load_key_and_certificates(p12, None)
        except ValueError:
            pass
        else:
            raise ValueError()
    except Exception:
        raise InputError("P12_REJECTED") from None
    try:
        public = certificate.public_key()
        if (
            not isinstance(key, rsa.RSAPrivateKey)
            or key.key_size < 2048
            or not isinstance(public, rsa.RSAPublicKey)
            or key.public_key().public_numbers() != public.public_numbers()
        ):
            raise ValueError()
        if (
            not certificate.not_valid_before_utc
            <= instant
            <= certificate.not_valid_after_utc
        ):
            raise ValueError()
        if [
            v.value
            for v in certificate.subject.get_attributes_for_oid(
                x509.NameOID.ORGANIZATIONAL_UNIT_NAME
            )
        ] != [team]:
            raise ValueError()
        bc = certificate.extensions.get_extension_for_class(x509.BasicConstraints)
        ku = certificate.extensions.get_extension_for_class(x509.KeyUsage)
        eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        if (
            not bc.critical
            or bc.value.ca
            or not ku.critical
            or not ku.value.digital_signature
            or ku.value.key_cert_sign
            or ku.value.crl_sign
            or not eku.critical
            or list(eku.value) != [x509.ExtendedKeyUsageOID.CODE_SIGNING]
        ):
            raise ValueError()
        known = {bc.oid, ku.oid, eku.oid}
        for oid in ("1.2.840.113635.100.6.1.4", "1.2.840.113635.100.6.1.7"):
            marker = certificate.extensions.get_extension_for_oid(
                x509.ObjectIdentifier(oid)
            )
            if not marker.critical:
                raise ValueError()
            known.add(marker.oid)
        if any(ext.critical and ext.oid not in known for ext in certificate.extensions):
            raise ValueError()
        der = certificate.public_bytes(serialization.Encoding.DER)
    except Exception:
        raise InputError("CERTIFICATE_REJECTED") from None
    result = profiles.validate_profile(
        decoded_profile,
        expected_bundle=bundle,
        expected_team=team,
        expected_certificate_der=der,
        now=instant,
    )
    if result["classification"] != "PROFILE_CONTENT_MATCH_ONLY":
        raise InputError("PROFILE_REJECTED")
    return SigningMaterial(key, der, team, bundle)


def _key(pem):
    _, _, serialization, _ = _dependencies()
    from asn1crypto import keys
    from asn1crypto import pem as asn1_pem
    from cryptography.hazmat.primitives.asymmetric import ec

    _bytes(pem, MAX_KEY_BYTES)
    try:
        key = serialization.load_pem_private_key(pem, None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
            key.curve, ec.SECP256R1
        ):
            raise ValueError()
        if (
            ec.derive_private_key(key.private_numbers().private_value, ec.SECP256R1())
            .public_key()
            .public_numbers()
            != key.public_key().public_numbers()
        ):
            raise ValueError()
        canonical_der = key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        # RFC5915 inner parameters/public point can be present or absent in
        # PKCS8. Compare finite exact encodings regenerated from the validated
        # key; never accept unknown fields or parser-ignored trailing bytes.
        encodings = set()
        for parameters in (False, True):
            for public in (False, True):
                info = keys.PrivateKeyInfo.load(canonical_der, strict=True)
                inner = info["private_key"].parsed
                inner["parameters"] = (
                    keys.ECDomainParameters(name="named", value="secp256r1")
                    if parameters
                    else None
                )
                if not public:
                    inner["public_key"] = None
                info["private_key"] = inner
                encoded = asn1_pem.armor("PRIVATE KEY", info.dump())
                encodings.update((encoded, encoded[:-1]))
        if pem.replace(b"\r\n", b"\n") not in encodings:
            raise ValueError()
        return key
    except Exception:
        raise InputError("KEY_REJECTED") from None


def load_asc_key(pem, *, key_id, issuer_id):
    _identifier(key_id)
    _issuer(issuer_id)
    return AscMaterial(_key(pem), key_id, issuer_id)


def _issuer(issuer_id):
    if type(issuer_id) is not str or not re.fullmatch(
        r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", issuer_id
    ):
        raise InputError()


def load_apple_login_key(pem, *, key_id, team, bundle):
    _identifier(key_id)
    _identifier(team)
    _bundle(bundle)
    return AppleLoginMaterial(_key(pem), key_id, team, bundle)


def validate_distinct_keys(asc, login):
    try:
        if (
            type(asc) is not AscMaterial
            or type(login) is not AppleLoginMaterial
            or asc.private_key.public_key().public_numbers()
            == login.private_key.public_key().public_numbers()
        ):
            raise ValueError()
    except Exception:
        raise InputError("KEY_REUSE_REJECTED") from None


def _jwt(material, now, *, login):
    _, hashes, _, _ = _dependencies()
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    instant = _time(now).replace(microsecond=0)
    try:
        if type(material) is not (AppleLoginMaterial if login else AscMaterial):
            raise ValueError()
        _identifier(material.key_id)
        if not isinstance(
            material.private_key, ec.EllipticCurvePrivateKey
        ) or not isinstance(material.private_key.curve, ec.SECP256R1):
            raise ValueError()
        expires = instant + timedelta(
            seconds=APPLE_LOGIN_TTL_SECONDS if login else ASC_TTL_SECONDS
        )
        claims = {
            "iss": material.team if login else material.issuer_id,
            "iat": int(instant.timestamp()),
            "exp": int(expires.timestamp()),
            "aud": "https://appleid.apple.com" if login else "appstoreconnect-v1",
        }
        if login:
            _identifier(material.team)
            _bundle(material.bundle)
            claims["sub"] = material.bundle
        else:
            _issuer(material.issuer_id)

        def encoded(value):
            return base64.urlsafe_b64encode(value).rstrip(b"=")

        body = b".".join(
            encoded(
                json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")
            )
            for value in (
                {"alg": "ES256", "kid": material.key_id, "typ": "JWT"},
                claims,
            )
        )
        signature = material.private_key.sign(body, ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(signature)
        return PrivateJWT(
            (
                body + b"." + encoded(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
            ).decode("ascii"),
            expires,
        )
    except Exception:
        raise InputError("TOKEN_REJECTED") from None


def asc_jwt(material, *, now):
    return _jwt(material, now, login=False)


def apple_login_jwt(material, *, now):
    return _jwt(material, now, login=True)
