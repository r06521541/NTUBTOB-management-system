"""Content-only checks of decoded XML plist bytes, never CMS or signing trust.

This narrow profile supports one certificate, iOS App Store distribution and
team-equal App Identifier prefixes. Legacy prefixes are not universally invalid;
they are outside this contract. No file reader, CMS decoder or CLI is provided.
"""

import base64
import math
import plistlib
import re
from datetime import datetime, timezone
from xml.etree import ElementTree
from xml.parsers import expat

MAX_PLIST_BYTES = 262144
MAX_CERTIFICATE_BYTES = 65536
STOP_REASONS = frozenset(
    {
        "INVALID_INPUT",
        "INVALID_VERIFICATION_TIME",
        "INVALID_XML_PLIST",
        "INVALID_CERTIFICATE",
        "CERTIFICATE_MISMATCH",
        "CERTIFICATE_TIME_REJECTED",
        "PROFILE_TIME_REJECTED",
        "TEAM_PREFIX_MISMATCH",
        "APPLICATION_MISMATCH",
        "APPLE_ENTITLEMENT_MISMATCH",
        "DISTRIBUTION_PROFILE_REQUIRED",
        "PROFILE_CHECK_REJECTED",
    }
)


class _Rejected(Exception):
    pass


def _result(reason="PUBLIC_PROFILE_CONTENT_MATCH"):
    match = reason == "PUBLIC_PROFILE_CONTENT_MATCH"
    return {
        "classification": "PROFILE_CONTENT_MATCH_ONLY" if match else "STOP",
        "reason": (
            reason if match or reason in STOP_REASONS else "PROFILE_CHECK_REJECTED"
        ),
        "cms_signature_verified": False,
        "apple_trust_verified": False,
        "certificate_signature_verified": False,
        "certificate_trust_verified": False,
        "revocation_verified": False,
        "private_key_possession_verified": False,
        "pkcs12_import_verified": False,
        "signing_authorized": False,
        "upload_authorized": False,
        "release_authorized": False,
    }


def _xml_profile(data):
    # Expat enforces document completeness before plistlib sees any values.
    parser = expat.ParserCreate()
    depth = count = 0

    def reject(*_):
        raise _Rejected()

    def doctype(name, system, public, internal):
        if (
            name != "plist"
            or internal
            or system != "http://www.apple.com/DTDs/PropertyList-1.0.dtd"
            or public != "-//Apple//DTD PLIST 1.0//EN"
        ):
            reject()

    def start(*_):
        nonlocal depth, count
        depth += 1
        count += 1
        if depth > 32 or count > 8192:
            reject()

    def end(*_):
        nonlocal depth
        depth -= 1

    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.ProcessingInstructionHandler = reject
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(data, True)
    tree = ElementTree.fromstring(data)

    def shape(node):
        tag, text, children = node.tag, node.text or "", list(node)
        if (node.tail or "").strip():
            reject()
        if tag == "plist":
            if (
                node is not tree
                or node.attrib != {"version": "1.0"}
                or len(children) != 1
                or children[0].tag != "dict"
            ):
                reject()
        elif node.attrib:
            reject()
        if tag in {"plist", "dict", "array"}:
            if text.strip():
                reject()
            if tag == "dict":
                if len(children) % 2:
                    reject()
                keys = set()
                for index in range(0, len(children), 2):
                    key = children[index]
                    if (
                        key.tag != "key"
                        or key.text in keys
                        or children[index + 1].tag == "key"
                    ):
                        reject()
                    keys.add(key.text)
            elif any(child.tag == "key" for child in children):
                reject()
            for child in children:
                shape(child)
        else:
            if children:
                reject()
            if tag in {"key", "string"}:
                return
            if tag in {"true", "false"}:
                if text.strip():
                    reject()
            elif tag == "date":
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text):
                    reject()
                datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
            elif tag == "data":
                base64.b64decode(re.sub(r"[ \t\r\n]", "", text), validate=True)
            elif tag == "integer":
                if not re.fullmatch(r"-?(0|[1-9][0-9]{0,19})", text):
                    reject()
            elif tag == "real":
                if len(text) > 64 or not math.isfinite(float(text)):
                    reject()
            else:
                reject()

    if tree.tag != "plist":
        reject()
    shape(tree)
    return plistlib.loads(data, fmt=plistlib.FMT_XML)


def validate_profile(
    decoded_plist, *, expected_bundle, expected_team, expected_certificate_der, now
):
    """Check explicit content expectations at an injected aware time.

    The certificate is parsed and compared, not signature/trust verified. Success
    cannot approve any downloaded CMS profile, P12 import or signing operation.
    """
    try:
        if (
            type(decoded_plist) is not bytes
            or not 0 < len(decoded_plist) <= MAX_PLIST_BYTES
            or type(expected_certificate_der) is not bytes
            or not 0 < len(expected_certificate_der) <= MAX_CERTIFICATE_BYTES
            or type(expected_bundle) is not str
            or len(expected_bundle) > 255
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+",
                expected_bundle,
            )
            or type(expected_team) is not str
            or not re.fullmatch(r"[A-Z0-9]{10}", expected_team)
        ):
            return _result("INVALID_INPUT")
        try:
            if type(now) is not datetime or now.utcoffset() is None:
                return _result("INVALID_VERIFICATION_TIME")
            instant = now.astimezone(timezone.utc)
        except Exception:
            return _result("INVALID_VERIFICATION_TIME")
        try:
            profile = _xml_profile(decoded_plist)
        except Exception:
            return _result("INVALID_XML_PLIST")
        try:
            import cryptography
            from cryptography import x509
            from cryptography.hazmat.primitives import serialization

            if cryptography.__version__ != "50.0.0":
                return _result("INVALID_CERTIFICATE")
            certificate = x509.load_der_x509_certificate(expected_certificate_der)
            if (
                certificate.public_bytes(serialization.Encoding.DER)
                != expected_certificate_der
            ):
                return _result("INVALID_CERTIFICATE")
            if certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value.ca:
                return _result("INVALID_CERTIFICATE")
        except Exception:
            return _result("INVALID_CERTIFICATE")
        certificates = profile.get("DeveloperCertificates")
        if (
            type(certificates) is not list
            or len(certificates) != 1
            or type(certificates[0]) is not bytes
            or certificates[0] != expected_certificate_der
        ):
            return _result("CERTIFICATE_MISMATCH")
        if (
            not certificate.not_valid_before_utc
            <= instant
            <= certificate.not_valid_after_utc
        ):
            return _result("CERTIFICATE_TIME_REJECTED")
        created, expires = profile.get("CreationDate"), profile.get("ExpirationDate")
        if (
            type(created) is not datetime
            or type(expires) is not datetime
            or not created.replace(tzinfo=timezone.utc)
            <= instant
            < expires.replace(tzinfo=timezone.utc)
        ):
            return _result("PROFILE_TIME_REJECTED")
        entitlements = profile.get("Entitlements")
        if (
            type(entitlements) is not dict
            or profile.get("TeamIdentifier") != [expected_team]
            or profile.get("ApplicationIdentifierPrefix") != [expected_team]
            or entitlements.get("com.apple.developer.team-identifier") != expected_team
        ):
            return _result("TEAM_PREFIX_MISMATCH")
        if (
            entitlements.get("application-identifier")
            != expected_team + "." + expected_bundle
        ):
            return _result("APPLICATION_MISMATCH")
        if entitlements.get("com.apple.developer.applesignin") != ["Default"]:
            return _result("APPLE_ENTITLEMENT_MISMATCH")
        if (
            profile.get("Platform") != ["iOS"]
            or entitlements.get("get-task-allow") is not False
            or entitlements.get("beta-reports-active") is not True
            or "ProvisionedDevices" in profile
            or profile.get("ProvisionsAllDevices", False) is not False
        ):
            return _result("DISTRIBUTION_PROFILE_REQUIRED")
        return _result()
    except Exception:
        return _result("PROFILE_CHECK_REJECTED")
