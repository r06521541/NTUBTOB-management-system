"""Owner-only one-shot profile verification controller; no signing key intake.

GitHub custody is not field masking or end-to-end encryption. No remote CAS:
Owner must exclude other writers/manual edits. Process death can retain a Secret;
expiry blocks validation but never deletes it. Unknown outcomes are not retried.
"""

import base64
import ctypes as c
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from ctypes import wintypes as w
from datetime import datetime, timedelta, timezone

from tools import ios_certificate_custody as custody
from tools import ios_certificate_preparation as preparation

REPO = "r06521541/NTUBTOB-management-system"
OWNER = "r06521541"
ENVIRONMENT = "ios-profile-verification"
SECRET = "IOS_PROFILE_VERIFICATION_INPUT"
WORKFLOW = "ios-profile-verification.yml"
JOB = "Native profile verification"
BUNDLE = "tw.org.ntubtob.portal"
INPUTS = ("distribution.cer", "distribution.mobileprovision")
MAX_ENVELOPE = 48 * 1024
API = "repos/" + REPO
REASONS = (
    frozenset(
        {
            "PREFLIGHT_PASSED",
            "VERIFIED_AND_REMOVED",
            "REPOSITORY_REJECTED",
            "PROTECTION_REJECTED",
            "SECRET_EXISTS",
            "LOCAL_LOCK_REJECTED",
            "INPUT_REJECTED",
            "CONFIRMATION_REJECTED",
            "API_REJECTED",
            "DISPATCH_UNCERTAIN",
            "RUN_BINDING_REJECTED",
            "RUN_NOT_WAITING",
            "UPLOAD_UNCERTAIN",
            "RUN_FAILED",
            "OBSERVATION_TIMEOUT",
            "RETENTION_UNRESOLVED",
            "INTAKE_REJECTED",
        }
    )
    | custody.REASONS
)


class Rejected(Exception):
    pass


def bounded_process(command, data=None):
    """One invocation, bounded stdin/stdout, discarded stderr, no shell/retry."""
    if data is not None and (type(data) is not bytes or len(data) > 100000):
        raise Rejected("API_REJECTED")
    process = None
    output, errors, workers = [], [], []
    try:
        # Existing gh credential-store login only; no token/debug/proxy/config
        # overrides or request logging variables are forwarded to the child.
        environment = {
            key: os.environ[key]
            for key in (
                "SystemRoot",
                "WINDIR",
                "PATH",
                "USERPROFILE",
                "APPDATA",
                "LOCALAPPDATA",
                "TEMP",
                "TMP",
                "HOME",
            )
            if key in os.environ
        }
        environment.update(
            {
                "GH_PROMPT_DISABLED": "1",
                "GH_NO_UPDATE_NOTIFIER": "1",
                "GH_NO_EXTENSION_UPDATE_NOTIFIER": "1",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
        )

        def write():
            try:
                if data:
                    process.stdin.write(data)
                process.stdin.close()
            except Exception:
                errors.append(True)

        def read():
            try:
                output.append(process.stdout.read(1048577))
                if len(output[0]) > 1048576:
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
            errors
            or any(worker.is_alive() for worker in workers)
            or not output
            or len(output[0]) > 1048576
        ):
            raise ValueError
        return process.returncode, output[0]
    except Exception:
        raise Rejected("API_REJECTED") from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for worker in workers:
                worker.join(timeout=1)
            process.stdin.close()
            process.stdout.close()


class GitHub:
    def __init__(self):
        self.executable = shutil.which("gh")
        if not self.executable:
            raise Rejected("API_REJECTED")

    def call(self, method, path, body=None):
        command = [
            self.executable,
            "api",
            "--hostname",
            "github.com",
            "--include",
            "--method",
            method,
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2026-03-10",
            path,
        ]
        data = None
        if body is not None:
            command += ["--input", "-"]
            data = json.dumps(body, separators=(",", ":")).encode("ascii")
        code, raw = bounded_process(command, data)
        try:
            header, payload = raw.replace(b"\r\n", b"\n").split(b"\n\n", 1)
            match = re.fullmatch(
                rb"HTTP/[^ ]+ ([0-9]{3})(?: [^\n]*)?", header.split(b"\n", 1)[0]
            )
            status = int(match[1])
            if code and status < 400:
                raise ValueError
            return status, json.loads(payload) if payload.strip() else None
        except Exception:
            raise Rejected("API_REJECTED") from None


def get(api, path):
    status, value = api.call("GET", path)
    if status != 200:
        raise Rejected("API_REJECTED")
    return value


def repository(sha):
    preparation.dependencies()
    from tools import ios_profile_cms_verification

    ios_profile_cms_verification._dependencies()
    import nacl

    if (
        nacl.__version__ != "1.6.2"
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
        or preparation.git("rev-parse", "HEAD") != sha
        or preparation.git("status", "--porcelain", "--untracked-files=all")
        or preparation.git("remote", "get-url", "origin")
        not in {
            "https://github.com/" + REPO + ".git",
            "git@github.com:" + REPO + ".git",
        }
    ):
        raise Rejected("REPOSITORY_REJECTED")


class Inputs:
    """Open ONLY the two public-input files, never packaging.Custody's inputs."""

    def __init__(self, directory):
        self.directory, self.native = directory, custody.Native()
        self.handles, self.files = [], {}

    def __enter__(self):
        try:
            preparation.safe_directory(self.directory, fresh=False)
            for path in (*reversed(self.directory.parents), self.directory):
                handle = self.native.open_handle(
                    path, directory=True, ancestor=path != self.directory
                )
                self.handles.append(handle)
                self.native.metadata(handle, path, directory=True)
                if path == self.directory:
                    self.native.acl(handle, directory=True)
            for name in INPUTS:
                handle = self.native.open_handle(self.directory / name)
                self.handles.append(handle)
                self.files[name] = (
                    handle,
                    self.native.metadata(handle, self.directory / name),
                )
                self.native.acl(handle)
            # Conservative base64/JSON envelope bound before payload reads.
            if (
                sum(4 * ((metadata[3] + 2) // 3) for _, metadata in self.files.values())
                + 2048
                > MAX_ENVELOPE
            ):
                raise Rejected("INPUT_REJECTED")
            return self
        except BaseException:
            self.__exit__()
            raise

    def lock(self):
        path = self.directory / "profile-verification.lock"
        security = self.native.creation_security()
        handle = self.native.open(
            str(path), 0xC0030000, 0, c.byref(security[0]), 1, 0x04200080, None
        )
        if handle == c.c_void_p(-1).value:
            raise Rejected("LOCAL_LOCK_REJECTED")
        self.handles.append(handle)
        self.native.metadata(handle, path, allow_empty=True)
        self.native.acl(handle)

    def read(self, name):
        handle, metadata = self.files[name]
        if self.native.metadata(handle, self.directory / name) != metadata:
            raise custody.CustodyError("INPUT_CHANGED")
        self.native.acl(handle)
        size = metadata[3]
        buffer, count = c.create_string_buffer(size), w.DWORD()
        if (
            not self.native.seek(handle, 0, None, 0)
            or not self.native.read(handle, buffer, size, c.byref(count), None)
            or count.value != size
            or self.native.metadata(handle, self.directory / name) != metadata
        ):
            raise custody.CustodyError("READ_REJECTED")
        return buffer.raw[:size]

    def __exit__(self, *_):
        for handle in reversed(self.handles):
            self.native.close(handle)
        self.handles.clear()


def absent(api, secret_path):
    status, _ = api.call("GET", secret_path)
    if status == 200:
        raise Rejected("SECRET_EXISTS")
    if status != 404:
        raise Rejected("API_REJECTED")
    listing = get(api, secret_path.rsplit("/", 1)[0] + "?per_page=100")
    values = listing.get("secrets")
    if (
        type(values) is not list
        or type(listing.get("total_count")) is not int
        or listing["total_count"] != len(values)
        or len(values) > 100
    ):
        raise Rejected("API_REJECTED")
    if any(item.get("name") == SECRET for item in values):
        raise Rejected("SECRET_EXISTS")


def remote_preflight(api, sha):
    if get(api, "user").get("login") != OWNER:
        raise Rejected("PROTECTION_REJECTED")
    repo = get(api, API)
    if repo.get("full_name") != REPO or type(repo.get("id")) is not int:
        raise Rejected("REPOSITORY_REJECTED")
    if get(api, API + "/git/ref/heads/main").get("object", {}).get("sha") != sha:
        raise Rejected("REPOSITORY_REJECTED")
    workflow = get(api, API + "/actions/workflows/" + WORKFLOW)
    if (
        workflow.get("path") != ".github/workflows/" + WORKFLOW
        or workflow.get("state") != "active"
        or type(workflow.get("id")) is not int
    ):
        raise Rejected("REPOSITORY_REJECTED")
    environment = get(api, API + "/environments/" + ENVIRONMENT)
    rules = environment.get("protection_rules", [])
    reviewer = [rule for rule in rules if rule.get("type") == "required_reviewers"]
    if (
        environment.get("name") != ENVIRONMENT
        or type(environment.get("id")) is not int
        or environment.get("can_admins_bypass") is not False
        or environment.get("deployment_branch_policy")
        != {"protected_branches": False, "custom_branch_policies": True}
        or len(reviewer) != 1
        or reviewer[0].get("prevent_self_review") is not False
        or [
            (item.get("type"), item.get("reviewer", {}).get("login"))
            for item in reviewer[0].get("reviewers", [])
        ]
        != [("User", OWNER)]
        or any(
            rule.get("type") not in {"required_reviewers", "branch_policy"}
            for rule in rules
        )
    ):
        raise Rejected("PROTECTION_REJECTED")
    branches = get(
        api,
        API
        + "/environments/"
        + ENVIRONMENT
        + "/deployment-branch-policies?per_page=100",
    )
    if branches.get("total_count") != 1 or [
        (item.get("name"), item.get("type"))
        for item in branches.get("branch_policies", [])
    ] != [("main", "branch")]:
        raise Rejected("PROTECTION_REJECTED")
    secret_path = API + f"/environments/{ENVIRONMENT}/secrets/{SECRET}"
    absent(api, secret_path)
    return workflow["id"], environment["id"], secret_path


def bound_run(api, run_id, workflow_id, sha):
    run = get(api, API + f"/actions/runs/{run_id}")
    if (
        run.get("id") != run_id
        or run.get("repository", {}).get("full_name") != REPO
        or run.get("workflow_id") != workflow_id
        or run.get("path") != ".github/workflows/" + WORKFLOW
        or run.get("event") != "workflow_dispatch"
        or run.get("head_branch") != "main"
        or run.get("head_sha") != sha
        or run.get("run_attempt") != 1
    ):
        raise Rejected("RUN_BINDING_REJECTED")
    return run


def pending_review(api, run_id, environment_id):
    pending = get(api, API + f"/actions/runs/{run_id}/pending_deployments")
    if pending == []:
        return False
    if (
        type(pending) is not list
        or len(pending) != 1
        or pending[0].get("environment", {}).get("id") != environment_id
        or pending[0].get("environment", {}).get("name") != ENVIRONMENT
        or pending[0].get("current_user_can_approve") is not True
        or [
            (item.get("type"), item.get("reviewer", {}).get("login"))
            for item in pending[0].get("reviewers", [])
        ]
        != [("User", OWNER)]
    ):
        raise Rejected("RUN_NOT_WAITING")
    return True


def envelope(profile, certificate, team, sha, run_id, nonce, now):
    if (
        type(team) is not str
        or not re.fullmatch(r"[A-Z0-9]{10}", team)
        or type(profile) is not bytes
        or type(certificate) is not bytes
    ):
        raise Rejected("INPUT_REJECTED")
    value = {
        "version": 1,
        "profile": base64.b64encode(profile).decode(),
        "certificate": base64.b64encode(certificate).decode(),
        "team": team,
        "sha": sha,
        "run_id": str(run_id),
        "nonce": nonce,
        "issued_at": int(now.timestamp()),
        "expires_at": int((now + timedelta(minutes=60)).timestamp()),
    }
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")
    if len(encoded) > MAX_ENVELOPE:
        raise Rejected("INPUT_REJECTED")
    return encoded


def encrypt(value, public_key):
    from nacl.public import PublicKey, SealedBox

    key = base64.b64decode(public_key, validate=True)
    if len(key) != 32:
        raise Rejected("API_REJECTED")
    return base64.b64encode(SealedBox(PublicKey(key)).encrypt(value)).decode("ascii")


def lifecycle(
    api,
    session,
    sha,
    metadata,
    *,
    sleep=time.sleep,
    clock=time.monotonic,
    now=lambda: datetime.now(timezone.utc),
):
    workflow_id, environment_id, secret_path = metadata
    attempted = uncertain = known_run = cancel_unresolved = cleaned = False
    reason, stage, run_id = "INTAKE_REJECTED", "input", None
    try:
        from tools import ios_profile_cms_verification as cms

        team = preparation.hidden("Expected Team identifier (hidden): ")
        if not re.fullmatch(r"[A-Z0-9]{10}", team):
            raise Rejected("INPUT_REJECTED")
        profile, certificate = session.read(INPUTS[1]), session.read(INPUTS[0])
        try:
            cms.preflight(profile)
            _, x509, serialization = cms._dependencies()
            parsed_certificate = x509.load_der_x509_certificate(certificate)
            if (
                parsed_certificate.public_bytes(serialization.Encoding.DER)
                != certificate
                or parsed_certificate.extensions.get_extension_for_class(
                    x509.BasicConstraints
                ).value.ca
            ):
                raise ValueError
            envelope(profile, certificate, team, sha, 1, "a" * 64, now())
        except Exception:
            raise Rejected("INPUT_REJECTED") from None
        if remote_preflight(api, sha) != metadata:
            raise Rejected("PROTECTION_REJECTED")
        stage = "dispatch"
        nonce = secrets.token_hex(32)
        try:
            status, response = api.call(
                "POST",
                API + "/actions/workflows/" + WORKFLOW + "/dispatches",
                {"ref": "main", "inputs": {"approved_sha": sha, "nonce": nonce}},
            )
            if (
                status != 200
                or type(response) is not dict
                or type(response.get("workflow_run_id")) is not int
                or not 0 < response["workflow_run_id"] < 10**20
            ):
                raise ValueError
            run_id = response["workflow_run_id"]
        except (Exception, KeyboardInterrupt):
            raise Rejected("DISPATCH_UNCERTAIN") from None
        stage = "waiting"
        deadline = clock() + 120
        while True:
            run = bound_run(api, run_id, workflow_id, sha)
            known_run = True
            if run.get("status") == "waiting":
                if pending_review(api, run_id, environment_id):
                    break
            if (
                run.get("status") not in {"queued", "requested", "pending", "waiting"}
                or clock() >= deadline
            ):
                raise Rejected("RUN_NOT_WAITING")
            sleep(5)
        value = envelope(
            profile,
            certificate,
            team,
            sha,
            run_id,
            nonce,
            now(),
        )
        public = get(api, secret_path.rsplit("/", 1)[0] + "/public-key")
        encrypted = encrypt(value, public["key"])
        # Recheck protections, exact SHA and no existing value before the one PUT.
        if (
            remote_preflight(api, sha) != metadata
            or bound_run(api, run_id, workflow_id, sha).get("status") != "waiting"
            or not pending_review(api, run_id, environment_id)
        ):
            raise Rejected("RUN_NOT_WAITING")
        stage = "upload"
        attempted = True
        try:
            status, _ = api.call(
                "PUT",
                secret_path,
                {"encrypted_value": encrypted, "key_id": public["key_id"]},
            )
            if status != 201:
                raise ValueError
        except (Exception, KeyboardInterrupt):
            uncertain = True
            raise Rejected("UPLOAD_UNCERTAIN") from None
        print("UPLOAD_CONFIRMED approve_only_exact_run=" + str(run_id))
        stage = "observe"
        deadline = clock() + 45 * 60
        while clock() < deadline:
            run = bound_run(api, run_id, workflow_id, sha)
            if run.get("status") == "completed":
                jobs = get(
                    api, API + f"/actions/runs/{run_id}/attempts/1/jobs?per_page=100"
                )
                matches = [
                    job for job in jobs.get("jobs", []) if job.get("name") == JOB
                ]
                if (
                    run.get("conclusion") != "success"
                    or jobs.get("total_count") != 1
                    or len(matches) != 1
                    or matches[0].get("conclusion") != "success"
                    or matches[0].get("status") != "completed"
                    or matches[0].get("run_id") != run_id
                ):
                    raise Rejected("RUN_FAILED")
                reason = "VERIFIED_AND_REMOVED"
                break
            sleep(10)
        else:
            raise Rejected("OBSERVATION_TIMEOUT")
    except (Exception, KeyboardInterrupt) as error:
        reason = (
            error.args[0]
            if isinstance(error, (Rejected, custody.CustodyError))
            and error.args
            and error.args[0] in REASONS
            else "INTAKE_REJECTED"
        )
    finally:
        if reason != "VERIFIED_AND_REMOVED" and known_run:
            try:
                current = bound_run(api, run_id, workflow_id, sha)
                if current.get("status") != "completed":
                    try:
                        status, _ = api.call(
                            "POST", API + f"/actions/runs/{run_id}/cancel"
                        )
                        if status != 202:
                            cancel_unresolved = True
                    except (Exception, KeyboardInterrupt):
                        cancel_unresolved = True
                    deadline = clock() + 60
                    while clock() < deadline:
                        if (
                            bound_run(api, run_id, workflow_id, sha).get("status")
                            == "completed"
                        ):
                            break
                        sleep(5)
                    else:
                        cancel_unresolved = True
            except (Exception, KeyboardInterrupt):
                cancel_unresolved = True
        if attempted:
            stage = "cleanup"
            status = None
            try:
                status, _ = api.call("DELETE", secret_path)
                # Even 404 on DELETE is ambiguous; absence GET cannot repair it.
                if status != 204:
                    uncertain = True
            except (Exception, KeyboardInterrupt):
                uncertain = True
            try:
                # Always attempt metadata reconciliation even after an unknown
                # DELETE outcome; it never converts that uncertainty to success.
                absent(api, secret_path)
                cleaned = status == 204 and not uncertain
            except (Exception, KeyboardInterrupt):
                uncertain = True
            if uncertain:
                reason = "RETENTION_UNRESOLVED"
    return result(
        reason, stage, run_id, cancel_unresolved=cancel_unresolved, cleaned=cleaned
    )


def result(
    reason, stage="preflight", run_id=None, *, cancel_unresolved=False, cleaned=False
):
    return {
        "classification": (
            "confirmed_success"
            if reason == "VERIFIED_AND_REMOVED"
            else (
                "preflight_passed"
                if reason == "PREFLIGHT_PASSED"
                else (
                    "retention_unresolved"
                    if reason == "RETENTION_UNRESOLVED"
                    else "STOP"
                )
            )
        ),
        "reason": reason if reason in REASONS else "INTAKE_REJECTED",
        "stage": stage,
        "run_id": run_id,
        "cancel_unresolved": cancel_unresolved,
        "secret_absence_confirmed": cleaned,
        "signing_authorized": False,
        "upload_authorized": False,
        "release_authorized": False,
    }


def operate(sha, *, execute=False):
    try:
        repository(sha)
        api = GitHub()
        with Inputs(preparation.local_app_data() / preparation.DIRECTORY) as session:
            metadata = remote_preflight(api, sha)
            if not execute:
                return result("PREFLIGHT_PASSED")
            print(
                "ACTION dispatch_once upload_one_private_environment_envelope observe cancel_once_on_failure delete_once"
            )
            print(
                "TARGET repository="
                + REPO
                + " environment="
                + ENVIRONMENT
                + " secret="
                + SECRET
                + " ref=main inputs=distribution.cer,distribution.mobileprovision"
            )
            print(
                "RETENTION_RISK hard_kill_may_retain_secret expiry_does_not_delete no_remote_CAS single_writer_required"
            )
            print("commit=" + sha)
            if (
                preparation.hidden(
                    "Type VERIFY PROFILE followed by space and exact commit (hidden): "
                )
                != "VERIFY PROFILE " + sha
            ):
                raise Rejected("CONFIRMATION_REJECTED")
            repository(sha)
            session.lock()
            if remote_preflight(api, sha) != metadata:
                raise Rejected("PROTECTION_REJECTED")
            return lifecycle(api, session, sha, metadata)
    except (Exception, KeyboardInterrupt) as error:
        reason = (
            error.args[0]
            if isinstance(error, (Rejected, custody.CustodyError))
            and error.args
            and error.args[0] in REASONS
            else "INTAKE_REJECTED"
        )
        return result(reason)


def main(argv=None):
    parser = preparation.SafeParser(add_help=False, exit_on_error=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--execute", action="store_true")
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown:
            raise ValueError
        response = operate(args.expected_commit, execute=args.execute)
    except (Exception, KeyboardInterrupt, SystemExit):
        response = result("INTAKE_REJECTED")
    print(json.dumps(response, sort_keys=True))
    return (
        0
        if response["classification"] in {"confirmed_success", "preflight_passed"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
