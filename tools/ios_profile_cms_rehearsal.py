"""No-argument fictional CMS rehearsal. Never reads real profiles or private files."""

import json
import plistlib
import sys
from datetime import datetime, timedelta, timezone

from tools import ios_profile_cms_verification as verify
from tools import ios_profile_validation

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)
TEAM = "FICTTEAM01"
BUNDLE = "invalid.fictional.app"
STAGES = frozenset(
    {
        "signature",
        "content",
        "purpose",
        "root",
        "expiry",
        "missing_intermediate",
        "test_marker",
        "production_root",
    }
)


def fixture():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs7

    keys = [
        rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(3)
    ]

    def certificate(name, key, issuer=None, signer=None, ca=False, path=None):
        subject = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, name)])
        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer.subject if issuer else subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(NOW - timedelta(days=1))
            .not_valid_after(NOW + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=path), True)
            .add_extension(
                x509.KeyUsage(not ca, False, False, False, False, ca, ca, False, False),
                True,
            )
            .sign(signer or key, hashes.SHA256())
        )

    root = certificate("fictional-root", keys[0], ca=True, path=1)
    intermediate = certificate(verify.INTERMEDIATE_CN, keys[1], root, keys[0], True, 0)
    leaf = certificate(verify.LEAF_CN, keys[2], intermediate, keys[1])
    wrong = certificate("fictional-wrong-purpose", keys[2], intermediate, keys[1])
    der = leaf.public_bytes(serialization.Encoding.DER)
    profile = plistlib.dumps(
        {
            "Name": "fictional-profile",
            "TeamIdentifier": [TEAM],
            "ApplicationIdentifierPrefix": [TEAM],
            "Platform": ["iOS"],
            "DeveloperCertificates": [der],
            "CreationDate": (NOW - timedelta(hours=1)).replace(tzinfo=None),
            "ExpirationDate": (NOW + timedelta(hours=1)).replace(tzinfo=None),
            "Entitlements": {
                "application-identifier": TEAM + "." + BUNDLE,
                "com.apple.developer.team-identifier": TEAM,
                "com.apple.developer.applesignin": ["Default"],
                "get-task-allow": False,
                "beta-reports-active": True,
            },
        }
    )

    def signed(
        cert=leaf,
        detached=False,
        multiple=False,
        include_root=True,
        include_intermediate=True,
    ):
        builder = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(profile)
            .add_signer(cert, keys[2], hashes.SHA256())
        )
        if include_root:
            builder = builder.add_certificate(root)
        if include_intermediate:
            builder = builder.add_certificate(intermediate)
        if multiple:
            builder = builder.add_signer(cert, keys[2], hashes.SHA256())
        options = [pkcs7.PKCS7Options.Binary, pkcs7.PKCS7Options.NoCapabilities]
        if detached:
            options.append(pkcs7.PKCS7Options.DetachedSignature)
        return builder.sign(serialization.Encoding.DER, options)

    cms = signed()
    return {
        "cms": cms,
        "root": root.public_bytes(serialization.Encoding.DER),
        "der": der,
        "payload": profile,
        "wrong_purpose": signed(wrong),
        "detached": signed(detached=True),
        "multiple": signed(multiple=True),
        "without_root": signed(include_root=False),
        "without_intermediate": signed(include_intermediate=False),
    }


def tampered(data, field):
    from asn1crypto import cms

    document = cms.ContentInfo.load(data)
    if field == "signature":
        signer = document["content"]["signer_infos"][0]
        value = signer["signature"].native
        signer["signature"] = value[:-1] + bytes([value[-1] ^ 1])
    elif field == "content":
        document["content"]["encap_content_info"][
            "content"
        ] = b"fictional-tampered-content"
    else:
        raise ValueError
    return document.dump(force=True)


def run():
    values = fixture()
    parsed = verify.preflight(values["cms"])
    with verify._compile_native(_fictional_root=values["root"]) as binary:
        payload = verify._native_verified(
            parsed, NOW, binary, _test_root=values["root"]
        )
        if (
            verify._native_verified(
                verify.preflight(values["without_root"]),
                NOW,
                binary,
                _test_root=values["root"],
            )
            != payload
        ):
            raise verify.Rejected("REHEARSAL_CASE_FAILED")
        if (
            ios_profile_validation.validate_profile(
                payload,
                expected_bundle=BUNDLE,
                expected_team=TEAM,
                expected_certificate_der=values["der"],
                now=NOW,
            )["classification"]
            != "PROFILE_CONTENT_MATCH_ONLY"
        ):
            raise verify.Rejected("PROFILE_CONTENT_REJECTED")
        other = fixture()
        for stage, data, instant, expected in [
            (
                "signature",
                tampered(values["cms"], "signature"),
                NOW,
                {"CMS_SIGNATURE_REJECTED"},
            ),
            (
                "content",
                tampered(values["cms"], "content"),
                NOW,
                {"CMS_SIGNATURE_REJECTED"},
            ),
            ("purpose", values["wrong_purpose"], NOW, {"CMS_PURPOSE_REJECTED"}),
            ("root", other["cms"], NOW, {"CMS_TRUST_REJECTED"}),
            ("expiry", values["cms"], NOW + timedelta(days=2), {"CMS_TRUST_REJECTED"}),
            # A cached intermediate may complete native trust, but membership
            # must still reject it. Neither path may become successful evidence.
            (
                "missing_intermediate",
                values["without_intermediate"],
                NOW,
                {"CMS_TRUST_REJECTED", "CMS_BINDING_REJECTED"},
            ),
        ]:
            try:
                verify._native_verified(
                    verify.preflight(data), instant, binary, _test_root=values["root"]
                )
            except verify.Rejected as error:
                if len(error.args) != 1 or error.args[0] not in expected:
                    raise verify.Rejected("REHEARSAL_CASE_FAILED", stage) from None
            else:
                raise verify.Rejected("REHEARSAL_CASE_FAILED", stage)
        # The fictional build may NEVER be consumed as production evidence.
        try:
            verify._native_verified(parsed, NOW, binary)
        except verify.Rejected as error:
            if error.args != ("TEST_BUILD_REJECTED",):
                raise verify.Rejected("REHEARSAL_CASE_FAILED", "test_marker") from None
        else:
            raise verify.Rejected("REHEARSAL_CASE_FAILED", "test_marker")
    with verify._compile_native() as production:
        try:
            verify._native_verified(parsed, NOW, production)
        except verify.Rejected as error:
            if error.args != ("CMS_TRUST_REJECTED",):
                raise verify.Rejected(
                    "REHEARSAL_CASE_FAILED", "production_root"
                ) from None
        else:
            raise verify.Rejected("REHEARSAL_CASE_FAILED", "production_root")
    return "FICTIONAL_CMS_REHEARSAL_VERIFIED"


def main(argv=None):
    stage = "preflight"
    try:
        reason = (
            "ARGUMENTS_REJECTED" if (sys.argv[1:] if argv is None else argv) else run()
        )
    except verify.Rejected as error:
        if len(error.args) == 2 and error.args[1] in STAGES:
            stage = error.args[1]
        reason = (
            error.args[0]
            if error.args
            and error.args[0] in verify.REASONS | {"REHEARSAL_CASE_FAILED"}
            else "REHEARSAL_REJECTED"
        )
    except Exception:
        reason = "REHEARSAL_REJECTED"
    print(
        json.dumps(
            {
                "classification": reason,
                "stage": (
                    "completed"
                    if reason == "FICTIONAL_CMS_REHEARSAL_VERIFIED"
                    else stage
                ),
                "real_assets_verified": False,
                "production_cms_verified": False,
                "revocation_verified": False,
                "signing_authorized": False,
                "upload_authorized": False,
                "release_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0 if reason == "FICTIONAL_CMS_REHEARSAL_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
