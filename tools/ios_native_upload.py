"""ASC credential syntax and secret-free native tool probe, NOT an uploader.

Do not infer the API role, App binding, build availability or upload permission
from an offline EC key check. Actual upload argv awaits the pinned tool probe.
"""

import argparse
import base64
import json
import platform
import re
from pathlib import Path, PurePosixPath

from tools import ios_native_signing as signing

Failure = signing.Failure
require = signing.require
MAX_CREDENTIAL = 48000
OPTIONS = {
    "upload_app": "--upload-app",
    "upload_package": "--upload-package",
    "api_key_camel": "--apiKey",
    "api_issuer_camel": "--apiIssuer",
    "api_key_kebab": "--api-key",
    "api_issuer_kebab": "--api-issuer",
    "p8_file_path": "--p8-file-path",
    "output_format": "--output-format",
    "show_progress": "--show-progress",
    "log_file": "--log-file",
    "private_key_directory_env": "API_PRIVATE_KEYS_DIR",
}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def credential(raw):
    """Validate an in-memory package using the already-reviewed key parser."""
    from tools import ios_testflight_inputs as inputs

    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_CREDENTIAL:
            raise ValueError()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if type(value) is not dict or set(value) != {
            "key_id",
            "issuer_id",
            "p8_base64",
        }:
            raise ValueError()
        inputs._identifier(value["key_id"])
        inputs._issuer(value["issuer_id"])
        pem = base64.b64decode(value["p8_base64"], validate=True)
        if base64.b64encode(pem).decode("ascii") != value["p8_base64"]:
            raise ValueError()
        inputs._key(pem)
        return {key: value[key] for key in ("key_id", "issuer_id")}, pem
    except Exception:
        raise Failure("asc_input", "ASC_CREDENTIAL_REJECTED") from None


def probe(*, run=signing.command):
    """Only --version/--help, no private inputs, Apple login, or upload."""
    root = Path(__file__).resolve().parents[1]
    require(
        run("xcode_version", [signing.XCODE, "-version"], root).strip()
        == b"Xcode 26.3\nBuild version 17C529",
        "xcode_version",
        "TOOLCHAIN_DRIFT",
    )
    path = run("altool_location", ["/usr/bin/xcrun", "--find", "altool"], root).strip()
    try:
        location = PurePosixPath(path.decode("utf-8"))
        bundle = PurePosixPath(signing.DEVELOPER).parent
        under_bundle = (
            location.is_absolute()
            and ".." not in location.parts
            and bundle in location.parents
            and location.name == "altool"
            and str(location).encode("utf-8") == path
        )
    except (UnicodeError, TypeError):
        under_bundle = False
    require(
        under_bundle,
        "altool_location",
        "TOOLCHAIN_DRIFT",
    )
    raw = run("altool_help", ["/usr/bin/xcrun", "altool", "--help"], root)
    require(
        type(raw) is bytes and 1 <= len(raw) <= 1048576,
        "altool_help",
        "HELP_OUTPUT_REJECTED",
    )
    # Fixed booleans only, not raw help or an assumed Apple response schema.
    return {
        "classification": "TOOL_PROBED",
        "xcode": "26.3/17C529",
        "altool_under_pinned_xcode": True,
        "options": {
            name: bool(
                re.search(
                    rb"(?<![\w-])" + re.escape(token.encode()) + rb"(?![\w-])", raw
                )
            )
            for name, token in OPTIONS.items()
        },
        "upload_attempted": False,
        "upload_authorized": False,
        "secret_input_read": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("probe",))
    parser.parse_args(argv)
    try:
        require(platform.system() == "Darwin", "probe", "HOST_REJECTED")
        result = probe()
    except Failure as failure:
        result = {
            "classification": "STOP",
            "failure": failure.public(),
            "upload_attempted": False,
            "next_action": "READ_ONLY_REVIEW",
        }
    except Exception:
        result = {
            "classification": "STOP",
            "failure": {"stage": "probe", "reason": "UNEXPECTED_LOCAL_FAILURE"},
            "upload_attempted": False,
            "next_action": "READ_ONLY_REVIEW",
        }
    print(json.dumps(result, sort_keys=True))
    return 1 if result["classification"] == "STOP" else 0


if __name__ == "__main__":
    raise SystemExit(main())
