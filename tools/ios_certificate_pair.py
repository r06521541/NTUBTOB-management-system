"""Bounded public certificate/CSR correspondence, never signing authorization.

Inputs are already in memory. No real-file reader or private-key operation is
provided. Certificate signatures, Apple chains, revocation, team and purpose
are deliberately not verified, even when public keys match.
"""

from datetime import datetime, timezone

try:
    import cryptography
    from cryptography import x509
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    _DEPENDENCY_AVAILABLE = False
else:
    _DEPENDENCY_AVAILABLE = True

MAX_INPUT_BYTES = 65536
STOP_REASONS = frozenset(
    {
        "DEPENDENCY_UNAVAILABLE",
        "INVALID_INPUT_TYPE",
        "INVALID_INPUT_SIZE",
        "INVALID_VERIFICATION_TIME",
        "INVALID_CERTIFICATE_ENCODING",
        "INVALID_CSR_ENCODING",
        "UNSUPPORTED_CSR_ALGORITHM",
        "INVALID_CSR_SIGNATURE",
        "CERTIFICATE_NOT_YET_VALID",
        "CERTIFICATE_EXPIRED",
        "PUBLIC_KEY_MISMATCH",
        "CA_CERTIFICATE_REJECTED",
        "PAIR_CHECK_REJECTED",
    }
)


def _result(
    match: bool = False,
    ca_status: str = "unchecked",
    reason: str = "PAIR_CHECK_REJECTED",
) -> dict:
    return {
        "classification": "PAIR_MATCH_ONLY" if match else "STOP",
        "reason": (
            "PUBLIC_PAIR_CHECKS_PASSED"
            if match
            else reason if reason in STOP_REASONS else "PAIR_CHECK_REJECTED"
        ),
        "ca_status": ca_status,
        "private_key_possession_verified": False,
        "certificate_signature_verified": False,
        "certificate_trust_verified": False,
        "apple_chain_verified": False,
        "revocation_verified": False,
        "team_verified": False,
        "certificate_purpose_verified": False,
        "app_profile_capability_verified": False,
        "signing_authorized": False,
        "upload_authorized": False,
        "release_authorized": False,
    }


def _parse(data: bytes, *, certificate: bool):
    pem_loader = (
        x509.load_pem_x509_certificate if certificate else x509.load_pem_x509_csr
    )
    der_loader = (
        x509.load_der_x509_certificate if certificate else x509.load_der_x509_csr
    )
    if data.startswith(b"-----BEGIN "):
        value = pem_loader(data)
        canonical = value.public_bytes(serialization.Encoding.PEM)
        normalized = data.replace(b"\r\n", b"\n")
        if normalized not in (canonical, canonical[:-1]):
            raise ValueError()
    else:
        value = der_loader(data)
        if value.public_bytes(serialization.Encoding.DER) != data:
            raise ValueError()
    return value


def check_pair(certificate_bytes: bytes, csr_bytes: bytes, *, now: datetime) -> dict:
    """Check public correspondence at an explicit aware time; return fixed data.

    Missing BasicConstraints permits correspondence with CA status unknown;
    it does not qualify the certificate for any purpose. Even self-signed or
    untrusted certificates can match. Every authority/trust field remains false.
    """
    try:
        if not _DEPENDENCY_AVAILABLE or cryptography.__version__ != "50.0.0":
            return _result(reason="DEPENDENCY_UNAVAILABLE")
        if type(certificate_bytes) is not bytes or type(csr_bytes) is not bytes:
            return _result(reason="INVALID_INPUT_TYPE")
        if (
            not 0 < len(certificate_bytes) <= MAX_INPUT_BYTES
            or not 0 < len(csr_bytes) <= MAX_INPUT_BYTES
        ):
            return _result(reason="INVALID_INPUT_SIZE")
        try:
            if type(now) is not datetime or now.utcoffset() is None:
                return _result(reason="INVALID_VERIFICATION_TIME")
            instant = now.astimezone(timezone.utc)
        except Exception:
            return _result(reason="INVALID_VERIFICATION_TIME")
        try:
            certificate = _parse(certificate_bytes, certificate=True)
        except ValueError:
            return _result(reason="INVALID_CERTIFICATE_ENCODING")
        try:
            csr = _parse(csr_bytes, certificate=False)
        except ValueError:
            return _result(reason="INVALID_CSR_ENCODING")
        public_key = csr.public_key()
        try:
            algorithm = csr.signature_hash_algorithm
        except UnsupportedAlgorithm:
            return _result(reason="UNSUPPORTED_CSR_ALGORITHM")
        if (
            not isinstance(public_key, rsa.RSAPublicKey)
            or public_key.key_size != 2048
            or not isinstance(algorithm, hashes.SHA256)
        ):
            return _result(reason="UNSUPPORTED_CSR_ALGORITHM")
        if not csr.is_signature_valid:
            return _result(reason="INVALID_CSR_SIGNATURE")
        if instant < certificate.not_valid_before_utc:
            return _result(reason="CERTIFICATE_NOT_YET_VALID")
        if instant > certificate.not_valid_after_utc:
            return _result(reason="CERTIFICATE_EXPIRED")
        if public_key.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ) != certificate.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ):
            return _result(reason="PUBLIC_KEY_MISMATCH")
        try:
            constraints = certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value
        except x509.ExtensionNotFound:
            ca_status = "unknown"
        else:
            if constraints.ca:
                return _result(reason="CA_CERTIFICATE_REJECTED")
            ca_status = "not_ca"
        return _result(True, ca_status)
    except Exception:
        # No parser, crypto, caller input, identity or exception data escapes.
        return _result()
