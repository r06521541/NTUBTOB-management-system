"""Owner-only, one-field GitHub Secret setup; no signing or local relay controller.

Official gh owns encryption/HTTP. No value readback, overwrite, deletion, retry,
clipboard, password file or new journal. CLI success is not signing evidence.
The absence recheck is NOT atomic create-if-absent: Owner must serialize setup.
Python/gh memory is not isolated from same-user/admin malware or guaranteed wiped.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = "r06521541/NTUBTOB-management-system"
OWNER = "r06521541"
ENVIRONMENT = "ios-native-signing"
ROOT = Path(__file__).resolve().parents[1]
GH = r"C:\Program Files\GitHub CLI\gh.exe"
GIT = r"C:\Program Files\Git\cmd\git.exe"
FIELDS = {
    "p12": "IOS_DISTRIBUTION_P12_BASE64",
    "profile": "IOS_DISTRIBUTION_PROFILE_BASE64",
    "password": "IOS_DISTRIBUTION_P12_PASSWORD",
    "asc": "IOS_ASC_UPLOAD_CREDENTIAL",
}
API = f"repos/{REPO}/environments/{ENVIRONMENT}"
MAX_RAW = 36 * 1024
REASONS = frozenset(
    {
        "ARGS_REJECTED",
        "SOURCE_REJECTED",
        "IDENTITY_REJECTED",
        "POLICY_REJECTED",
        "SCHEMA_REJECTED",
        "FIELD_BECAME_PRESENT",
        "APPROVAL_REJECTED",
        "INPUT_REJECTED",
        "INPUT_TOO_LARGE",
        "PATH_REJECTED",
        "ACL_REJECTED",
        "HANDLE_REJECTED",
        "METADATA_REJECTED",
        "INPUT_CHANGED",
        "READ_REJECTED",
        "CUSTODY_CLOSE_UNRESOLVED",
        "INTERRUPTED",
        "UNEXPECTED_FAILURE",
        "CLI_FAILED",
        "CLI_LAUNCH_FAILED",
        "CLI_VERSION_REJECTED",
        "TIMEOUT",
        "PROCESS_UNRESOLVED",
        "DNS_FAILURE",
        "TLS_FAILURE",
        "CONNECTION_FAILURE",
        "HTTP_401",
        "HTTP_403",
        "HTTP_404",
        "HTTP_409",
        "HTTP_413",
        "HTTP_422",
        "HTTP_429",
        "HTTP_500",
        "HTTP_502",
        "HTTP_503",
        "HTTP_504",
        "PRESENCE_UNCONFIRMED",
        "UNSUPPORTED_HOST",
        "DEBUG_ENV_REJECTED",
        "TERMINAL_ESCAPE_GUARD",
        "ASC_CREDENTIAL_REJECTED",
        "SAVED_SETTINGS_REJECTED",
    }
)


class Failure(Exception):
    def __init__(
        self,
        stage,
        reason,
        exit_code=None,
        *,
        started=True,
        cleanup=None,
        confirmed=False,
    ):
        super().__init__("Secret setup stopped")
        self.stage = stage
        self.reason = reason if reason in REASONS else "UNEXPECTED_FAILURE"
        self.exit_code = exit_code
        self.started = started
        self.cleanup = cleanup
        self.confirmed = confirmed

    def public(self):
        return {"stage": self.stage, "reason": self.reason, "exit_code": self.exit_code}


def require(condition, stage, reason):
    if not condition:
        raise Failure(stage, reason)


def cli_reason(raw):
    for code in (401, 403, 404, 409, 413, 422, 429, 500, 502, 503, 504):
        if re.search(rb"HTTP " + str(code).encode() + rb"\b", raw):
            return "HTTP_" + str(code)
    for marker, reason in (
        (
            b"the response contains terminal escape sequences; pass --allow-escape-sequences",
            "TERMINAL_ESCAPE_GUARD",
        ),
        (b"no such host", "DNS_FAILURE"),
        (b"certificate signed by unknown authority", "TLS_FAILURE"),
        (b"connection refused", "CONNECTION_FAILURE"),
    ):
        if marker in raw:
            return reason
    return "CLI_FAILED"


def child_env():
    # gh uses the existing OS/user credential store, not a copied token env var.
    allowed = {
        "SYSTEMROOT",
        "WINDIR",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "TEMP",
        "TMP",
        "PATH",
        "OS",
    }
    result = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    result.update(GH_HOST="github.com", GH_PROMPT_DISABLED="1", GH_PAGER="cat")
    return result


def command(stage, args, payload=None):
    """In-memory pipes only. Never echo args, child output or exception text."""
    child = None
    failure = None
    confirmed = False
    out = b""
    try:
        child = subprocess.Popen(
            args,
            cwd=ROOT,
            env=child_env(),
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            out, err = child.communicate(input=payload, timeout=60)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            reason = (
                "TIMEOUT"
                if isinstance(error, subprocess.TimeoutExpired)
                else "INTERRUPTED"
            )
            raise Failure(stage, reason) from None
        confirmed = child.returncode == 0
        require(len(out) + len(err) <= 1024 * 1024, stage, "SCHEMA_REJECTED")
        if child.returncode:
            raise Failure(stage, cli_reason(err), child.returncode)
    except OSError:
        failure = Failure(stage, "CLI_LAUNCH_FAILED", started=child is not None)
    except BaseException as error:
        failure = (
            error
            if isinstance(error, Failure)
            else Failure(
                stage,
                (
                    "INTERRUPTED"
                    if isinstance(error, KeyboardInterrupt)
                    else "UNEXPECTED_FAILURE"
                ),
            )
        )
    finally:
        if child is not None:
            cleanup_failed = False
            try:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)
            except BaseException:
                cleanup_failed = True
            for pipe in (child.stdin, child.stdout, child.stderr):
                try:
                    if pipe is not None:
                        pipe.close()
                except BaseException:
                    cleanup_failed = True
            if cleanup_failed:
                failure = failure or Failure(stage, "PROCESS_UNRESOLVED")
                failure.cleanup = "PROCESS_UNRESOLVED"
    if failure is not None:
        failure.confirmed = confirmed
        raise failure
    return out


def api(run, stage, path):
    try:
        return json.loads(run(stage, [GH, "api", "--hostname", "github.com", path]))
    except (ValueError, TypeError):
        raise Failure(stage, "SCHEMA_REJECTED") from None


def presence(run, stage):
    value = api(run, stage, API + "/secrets?per_page=100")
    try:
        records = value["secrets"]
        require(
            type(records) is list and value["total_count"] == len(records) <= 100,
            stage,
            "SCHEMA_REJECTED",
        )
        names = [record["name"] for record in records]
        require(
            all(type(n) is str and re.fullmatch(r"[A-Z0-9_]+", n) for n in names)
            and len(names) == len(set(names)),
            stage,
            "SCHEMA_REJECTED",
        )
        return names
    except (KeyError, TypeError):
        raise Failure(stage, "SCHEMA_REJECTED") from None


def preflight(run, sha):
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "source", "SOURCE_REJECTED")
    require(
        run("source_head", [GIT, "rev-parse", "HEAD"]).decode().strip() == sha,
        "source",
        "SOURCE_REJECTED",
    )
    require(
        run("source_branch", [GIT, "branch", "--show-current"]).strip() == b"main",
        "source",
        "SOURCE_REJECTED",
    )
    require(
        not run("source_clean", [GIT, "status", "--porcelain"]),
        "source",
        "SOURCE_REJECTED",
    )
    stage = "identity"
    try:
        require(
            api(run, "identity", "user")["login"] == OWNER,
            "identity",
            "IDENTITY_REJECTED",
        )
        stage = "remote_head"
        require(
            api(run, "remote_head", f"repos/{REPO}/git/ref/heads/main")["object"]["sha"]
            == sha,
            "remote_head",
            "SOURCE_REJECTED",
        )
        stage = "environment"
        env = api(run, "environment", API)
        required = [
            p for p in env["protection_rules"] if p["type"] == "required_reviewers"
        ]
        require(
            env["name"] == ENVIRONMENT
            and env["can_admins_bypass"] is False
            and env["deployment_branch_policy"]
            == {"protected_branches": False, "custom_branch_policies": True}
            and len(required) == 1
            and required[0]["prevent_self_review"] is False
            and [(p["type"], p["reviewer"]["login"]) for p in required[0]["reviewers"]]
            == [("User", OWNER)],
            "environment",
            "POLICY_REJECTED",
        )
        stage = "branches"
        branches = api(
            run, "branches", API + "/deployment-branch-policies?per_page=100"
        )
        require(
            branches["total_count"] == 1
            and [(p["name"], p["type"]) for p in branches["branch_policies"]]
            == [("main", "branch")],
            "branches",
            "POLICY_REJECTED",
        )
    except (KeyError, TypeError):
        raise Failure(stage, "SCHEMA_REJECTED") from None
    return presence(run, "presence")


def hidden(field):
    from tools.ios_certificate_preparation import hidden as existing_hidden

    prompts = {
        "approval": "Type the displayed SET phrase (hidden): ",
        "password": "Existing P12 password (hidden): ",
        "p12": "Existing distribution.p12 full path (hidden; no quotes): ",
        "profile": "Existing .mobileprovision full path (hidden; no quotes): ",
    }
    return existing_hidden(prompts[field])


def read_file(value, kind):
    from tools import ios_certificate_custody as custody
    from tools import ios_testflight_key_custody as existing

    path = Path(value)
    suffix = {"p12": ".p12", "profile": ".mobileprovision", "asc": ".p8"}[kind]
    require(
        path.is_absolute() and path.suffix.lower() == suffix and ".." not in path.parts,
        "input",
        "PATH_REJECTED",
    )
    session = existing.Session(existing.Native())
    failure = None
    raw = None
    try:
        session.directory(path.parent)
        record = session.file(path, limit=MAX_RAW)
        raw = session.read(record)
        session.verify()
    except (custody.CustodyError, existing.Rejected) as error:
        failure = Failure("input", str(error))
    except BaseException as error:
        failure = Failure(
            "input",
            "INTERRUPTED" if isinstance(error, KeyboardInterrupt) else "INPUT_REJECTED",
        )
    finally:
        try:
            session.close()
        except BaseException:
            if failure is None:
                failure = Failure("input", "CUSTODY_CLOSE_UNRESOLVED")
            failure.cleanup = "CUSTODY_CLOSE_UNRESOLVED"
    if failure is not None:
        raise failure
    return raw


def saved_asc(*, reader_factory=None, root=None):
    """Owner only after SET asc: reuse existing private metadata; never resave it.

    Key syntax cannot establish ASC role or distinguish Apple service keys.
    The saved ASC selection is Owner-provided; actual Apple auth remains unverified.
    """
    from tools import ios_certificate_custody as custody
    from tools import ios_certificate_preparation as preparation
    from tools import ios_native_upload as upload
    from tools import ios_testflight_intake as intake
    from tools import ios_testflight_settings as settings

    reader = None
    failure = None
    payload = None
    stage = "asc_settings"
    try:
        root = root or preparation.local_app_data() / preparation.DIRECTORY
        reader = (reader_factory or intake.Reader)()
        reader.directory(root)
        # One held snapshot spans metadata selection and key read. Do not call
        # settings.load: its close may replace the primary diagnostic.
        value = settings.parse(
            reader.file(root / settings.FILENAME, 65536), google_web=None
        )
        stage = "asc_input"
        path = Path(value["asc_p8_path"])
        reader.directory(path.parent)
        raw = reader.file(path, 4096)
        payload = json.dumps(
            {
                "key_id": value["asc_key_id"],
                "issuer_id": value["asc_issuer_id"],
                "p8_base64": base64.b64encode(raw).decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("ascii")
        upload.credential(payload)
        stage = "asc_verify"
        reader.verify()
    except (custody.CustodyError, intake.Rejected) as error:
        failure = Failure(stage, str(error))
    except settings.Rejected:
        failure = Failure(stage, "SAVED_SETTINGS_REJECTED")
    except upload.Failure:
        failure = Failure(stage, "ASC_CREDENTIAL_REJECTED")
    except BaseException as error:
        failure = Failure(
            stage,
            "INTERRUPTED" if isinstance(error, KeyboardInterrupt) else "INPUT_REJECTED",
        )
    finally:
        if reader is not None:
            try:
                reader.close()
            except BaseException:
                failure = failure or Failure("asc_close", "CUSTODY_CLOSE_UNRESOLVED")
                failure.cleanup = "CUSTODY_CLOSE_UNRESOLVED"
    if failure is not None:
        raise failure
    return payload


def perform(
    kind, sha, *, execute=False, run=command, prompt=hidden, read=None, emit=print
):
    result = {
        "target": ENVIRONMENT,
        "field": FIELDS[kind],
        "classification": "STOP",
        "failure": None,
        "cleanup_failure": None,
        "write_state": "NOT_ATTEMPTED",
        "next_action": "READ_ONLY_REVIEW",
        "retry_authorized": False,
        "signing_verified": False,
        "upload_attempted": False,
    }
    stage = "preflight"
    payload = value = None
    try:
        if FIELDS[kind] in preflight(run, sha):
            result.update(classification="ALREADY_PRESENT", next_action="NEXT_FIELD")
            return result
        emit(
            f"target={REPO}/{ENVIRONMENT} field={FIELDS[kind]} mutation_count=1 approval=SET {kind}"
        )
        if not execute:
            result.update(
                classification="READY", next_action="OWNER_SET_SELECTED_FIELD"
            )
            return result
        stage = "approval"
        require(prompt("approval") == "SET " + kind, stage, "APPROVAL_REJECTED")
        stage = "input"
        if kind == "asc":
            payload = saved_asc()
        else:
            value = prompt(kind)
        if kind == "password":
            require(
                type(value) is str
                and 1 <= len(value.encode("utf-8")) <= 1024
                and not any(ord(c) < 32 or ord(c) == 127 for c in value),
                stage,
                "INPUT_REJECTED",
            )
            payload = value.encode("utf-8")
        elif kind != "asc":
            raw = read(value) if read else read_file(value, kind)
            require(
                type(raw) is bytes and 1 <= len(raw) <= MAX_RAW,
                stage,
                "INPUT_TOO_LARGE",
            )
            payload = base64.b64encode(raw)
            raw = None
        stage = "preflight_recheck"
        require(
            FIELDS[kind] not in preflight(run, sha), "presence", "FIELD_BECAME_PRESENT"
        )
        stage = "store"
        result["write_state"] = "ATTEMPTED_UNKNOWN"
        run(
            stage,
            [
                GH,
                "secret",
                "set",
                FIELDS[kind],
                "--env",
                ENVIRONMENT,
                "--repo",
                "github.com/" + REPO,
                "--app",
                "actions",
            ],
            payload,
        )
        result["write_state"] = "CONFIRMED"
        stage = "postcheck"
        require(FIELDS[kind] in presence(run, stage), stage, "PRESENCE_UNCONFIRMED")
        result.update(
            classification="STORED_METADATA_CONFIRMED", next_action="NEXT_FIELD"
        )
    except BaseException as error:
        failure = (
            error
            if isinstance(error, Failure)
            else Failure(
                stage,
                (
                    "INTERRUPTED"
                    if isinstance(error, (KeyboardInterrupt, EOFError))
                    else "UNEXPECTED_FAILURE"
                ),
            )
        )
        if stage == "store" and not failure.started:
            result["write_state"] = "NOT_ATTEMPTED"
        elif stage == "store" and failure.confirmed:
            result["write_state"] = "CONFIRMED"
        result["failure"] = failure.public()
        result["cleanup_failure"] = failure.cleanup
        if stage == "input" and not failure.cleanup:
            result["next_action"] = "CORRECT_SELECTED_INPUT"
    finally:
        payload = value = None  # Reference release, NOT guaranteed zeroization.
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Failure("entry", "ARGS_REJECTED")


def main(argv=None):
    kind = None
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("field", choices=tuple(FIELDS))
        parser.add_argument("--expected-commit", required=True)
        parser.add_argument("--execute", action="store_true")
        args = parser.parse_args(argv)
        kind = args.field
        require(sys.platform == "win32", "entry", "UNSUPPORTED_HOST")
        require(not os.environ.get("GH_DEBUG"), "entry", "DEBUG_ENV_REJECTED")
        require(
            command("version", [GH, "--version"]).startswith(b"gh version 2.97.0 "),
            "entry",
            "CLI_VERSION_REJECTED",
        )
        result = perform(args.field, args.expected_commit, execute=args.execute)
    except Failure as failure:
        result = {
            "classification": "STOP",
            "failure": failure.public(),
            "cleanup_failure": failure.cleanup,
            "field": FIELDS.get(kind),
            "write_state": "NOT_ATTEMPTED",
            "next_action": "READ_ONLY_REVIEW",
        }
    except (Exception, KeyboardInterrupt):
        result = {
            "classification": "STOP",
            "cleanup_failure": None,
            "field": FIELDS.get(kind),
            "failure": {
                "stage": "entry",
                "reason": "UNEXPECTED_FAILURE",
                "exit_code": None,
            },
            "write_state": "NOT_ATTEMPTED",
            "next_action": "READ_ONLY_REVIEW",
        }
    print(json.dumps(result, sort_keys=True))
    return 1 if result["classification"] == "STOP" else 0


if __name__ == "__main__":
    raise SystemExit(main())
