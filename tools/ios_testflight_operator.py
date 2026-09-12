"""IOS-TF-01 Windows entry point: preflight, one sign/upload, or recovery.

Owner-only distribution is deliberately a separate transition requiring actual
staging runtime/schema postchecks; an accepted IPA does not establish them.
Private inputs stay in memory. The only durable output is the sanitized journal.
"""

import base64
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from tools import ios_certificate_preparation as preparation
from tools import ios_profile_intake as primitives
from tools import ios_testflight_dispatch as dispatch
from tools import ios_testflight_hosted as hosted
from tools import ios_testflight_intake as intake
from tools import ios_testflight_journal as journal_module
from tools import ios_testflight_recovery as recovery
from tools import ios_testflight_signing as signing
from tools import ios_testflight_staging as staging_contract
from tools import ios_testflight_wire as wire

PROJECT = "ntubtob-mobile-staging"
SERVICE = "mobile-api-staging"
REGION = "asia-east1"
VERSION = "1.0.0"
REASONS = (
    frozenset(
        {
            "PREFLIGHT_PASSED",
            "SOURCE_REJECTED",
            "STAGING_TARGET_REJECTED",
            "STAGING_OWNERSHIP_UNVERIFIED",
            "INPUT_REQUIRED",
            "INPUT_REJECTED",
            "OWNER_GROUP_REQUIRED",
            "ASC_SCOPE_REJECTED",
            "JOURNAL_REJECTED",
            "OPERATION_UNRESOLVED",
            "BUILD_VALID_UNDISTRIBUTED",
            "BUILD_PENDING",
            "UPLOAD_PENDING",
            "RECONCILIATION_UNRESOLVED",
            "RETENTION_UNRESOLVED",
            "RUN_FAILED",
            "OBSERVATION_TIMEOUT",
        }
    )
    | intake.custody.REASONS
    | intake.inputs.REASONS
)


class Rejected(Exception):
    def __init__(self, reason="OPERATION_UNRESOLVED"):
        super().__init__(reason if reason in REASONS else "OPERATION_UNRESOLVED")


@dataclass(frozen=True, repr=False)
class Staging:
    url: str
    google_web: str
    line: str
    apple_configured: bool


def emit(reason, *, run_id=None, cleanup=False, secret_absence=False):
    result = {
        "classification": reason if reason in REASONS else "OPERATION_UNRESOLVED",
        "target": "owner_testflight_staging",
        "standing_authorization": "IOS-TF-01",
        "run_id": run_id if type(run_id) is int and run_id > 0 else None,
        "cleanup_verified": cleanup is True,
        "secret_absence_verified": secret_absence is True,
        "owner_distribution_verified": False,
        "device_verified": False,
        "release_authorized": False,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return result


def cli_json(command):
    executable = shutil.which(command[0])
    if not executable:
        raise Rejected("STAGING_TARGET_REJECTED")
    code, raw = primitives.bounded_process([executable, *command[1:]])
    if code:
        raise Rejected("STAGING_TARGET_REJECTED")
    try:
        return json.loads(raw, object_pairs_hook=wire._unique)
    except Exception:
        raise Rejected("STAGING_TARGET_REJECTED") from None


def staging_scope():
    """Read service metadata only; never access a Secret version or database."""
    snapshot = {}

    def read(command):
        document = cli_json(command)
        if command[1:3] == ["projects", "describe"]:
            snapshot["project"] = document
        elif command[1:4] == ["run", "services", "describe"]:
            snapshot["service"] = document
        return document

    proof = staging_contract.verify(PROJECT, SERVICE, cli_json=read)
    if proof["ownership_verified"] is not True:
        raise Rejected("STAGING_OWNERSHIP_UNVERIFIED")
    # Use the exact final service snapshot compared by the ownership verifier.
    project, service = snapshot["project"], snapshot["service"]
    try:
        if (
            project.get("projectId") != PROJECT
            or project.get("lifecycleState") != "ACTIVE"
        ):
            raise ValueError()
        metadata, status = service["metadata"], service["status"]
        if (
            metadata["name"] != SERVICE
            or str(metadata["namespace"]) != str(project["projectNumber"])
            or not any(
                c.get("type") == "Ready" and c.get("status") == "True"
                for c in status["conditions"]
            )
        ):
            raise ValueError()
        url = status["url"]
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname.endswith(".run.app")
            or parts.netloc != parts.hostname
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
        ):
            raise ValueError()
        containers = service["spec"]["template"]["spec"]["containers"]
        if len(containers) != 1:
            raise ValueError()
        values = containers[0].get("env", [])
        env = {item["name"]: item for item in values}
        if len(env) != len(values):
            raise ValueError()
        line = env["MOBILE_API_AUDIENCE"]["value"]
        audiences = env["MOBILE_API_GOOGLE_AUDIENCES"]["value"].split(",")
        if (
            not re.fullmatch(r"[0-9]{1,20}", line)
            or len(audiences) != 1
            or not re.fullmatch(
                r"[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com", audiences[0]
            )
        ):
            raise ValueError()
        # Presence is not validity, schema readiness or a distribution receipt.
        apple = all(
            name in env
            for name in (
                "MOBILE_API_APPLE_AUDIENCE",
                "MOBILE_API_APPLE_CLIENT_SECRET",
                "MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY",
                "MOBILE_API_APPLE_NOTIFICATION_AUDIENCE",
            )
        )
        return Staging(url.rstrip("/"), audiences[0], line, apple)
    except Exception:
        raise Rejected("STAGING_TARGET_REJECTED") from None


def preflight(*, recovery_only=False):
    if os.name != "nt":
        raise Rejected("SOURCE_REJECTED")
    sha = preparation.git("rev-parse", "HEAD")
    primitives.repository(sha)
    if (
        preparation.git("branch", "--show-current") != "main"
        or hosted.LIVE_CONTROLLER_READY is not True
    ):
        raise Rejected("SOURCE_REJECTED")
    if not recovery_only:
        probe = dispatch.Session(b"{}", b"{}", sha=sha)
        probe.policy()
        repository = probe.get(dispatch.API)
        if repository.get("private") is not False:
            raise Rejected(
                "SOURCE_REJECTED"
            )  # Standard public runners, no paid/storage exports.
        if set(wire.SECRETS) & probe.listing():
            raise Rejected("RETENTION_UNRESOLVED")
        for name in wire.SECRETS:
            if probe.call("GET", dispatch.SECRET + name)[0] != 404:
                raise Rejected("RETENTION_UNRESOLVED")
    return sha, staging_scope() if not recovery_only else None


def metadata(staging, *, prompt=preparation.hidden):
    """One visible batch; known staging URL/LINE/Web audience are not re-requested."""
    team = prompt("Apple Team ID (10 characters, hidden): ")
    asc_key = prompt("ASC API key ID (10 characters, hidden): ")
    issuer = prompt("ASC API issuer ID (UUID, hidden): ")
    login_key = "NOTUSED000"  # No Apple Login key requested/read by sign/upload.
    ios_client = prompt("Existing Google iOS client ID (hidden): ")
    email = prompt("Owner Apple account email (hidden): ")
    config = intake.Config(
        team,
        asc_key,
        issuer,
        login_key,
        staging.url,
        ios_client,
        staging.google_web,
        staging.line,
        VERSION,
        1,
    )
    intake._config(config)
    if type(email) is not str or not re.fullmatch(
        r"[^\s@]{1,128}@[^\s@]{1,128}\.[^\s@]{1,64}", email
    ):
        raise Rejected("INPUT_REJECTED")
    return config, email


def frames(materials, config, target):
    sign = signing.frame(
        **(materials.signing | {"version": config.version, "build": config.build})
    )
    raw = {
        "pem": base64.b64encode(materials.asc.pem).decode("ascii"),
        "key_id": config.asc_key_id,
        "issuer_id": config.asc_issuer_id,
        **target.upload_target(),
        "version": config.version,
        "build": config.build,
        "previous_build": target.previous_build,
    }
    asc = json.dumps(raw, separators=(",", ":")).encode("ascii")
    hosted.asc_fields(asc)
    return sign, asc


def settle(session, *, sleep=time.sleep):
    """Observe exact run; remove transfer secrets once the bound job starts."""
    cleaned = False
    for _ in range(115):
        snapshot = session.observe()
        if not cleaned and snapshot["job_status"] in {"RUNNING", "COMPLETED"}:
            session.cleanup()
            cleaned = True
        if snapshot["job_status"] == "COMPLETED":
            return
        if time.monotonic() >= session.deadline or session.journal_failed:
            raise Rejected("OBSERVATION_TIMEOUT")
        print("stage=waiting_for_exact_run", flush=True)
        sleep(60)
    raise Rejected("OBSERVATION_TIMEOUT")


def result_record(journal, reason, *, cleanup, absent):
    if journal is not None and journal.intact:
        journal.record(
            "RESULT",
            classification=(
                reason if reason in journal_module.CLASSIFICATIONS else "UNRESOLVED"
            ),
            cleanup_verified=cleanup,
            secret_absence_verified=absent,
            owner_distribution_verified=False,
        )


def finalize_session(session, *, sleep=time.sleep):
    """Cancel once, clean attempted secrets even on cancel failure, observe fresh."""
    session.signing = session.asc = b""
    session.restrict_to_cleanup()
    try:
        if (
            session.run_id
            and session.job_status != "COMPLETED"
            and session.journal is not None
            and session.journal.intact
            and not session.journal_failed
            and not session.cancel_attempted
        ):
            session.cancel()
    except (KeyboardInterrupt, Exception):
        session.cancel_unresolved = session.http_uncertain = True
    finally:
        # Dispatch enforces intact journal / exact attempted names for DELETE.
        # This must run even if the cancellation transport itself raises.
        if session.attempted:
            try:
                session.cleanup()
            except (KeyboardInterrupt, Exception):
                session.http_uncertain = True
                session.absent.clear()
    # A 202 response is an acknowledgment, not evidence that the job stopped.
    # Bounded fresh GET observations share the cleanup-only budget, not input TTL.
    for _ in range(12):
        if not session.run_id or session.job_status == "COMPLETED":
            break
        try:
            session.observe()
            if session.job_status == "COMPLETED":
                break
            if time.monotonic() >= session.deadline:
                break
            sleep(15)
        except (KeyboardInterrupt, Exception):
            break
    return session.public()


def execute(
    sha,
    staging,
    config,
    email,
    *,
    collect=intake.collect_upload,
    journal_factory=journal_module.Journal.open,
    session_factory=dispatch.Session,
    owner_factory=None,
    sleep=time.sleep,
):
    from tools import ios_testflight_owner as owner

    session = journal = materials = None
    cleanup = absent = False
    reason = "OPERATION_UNRESOLVED"
    try:
        if (
            config.api_base_url,
            config.google_web_client_id,
            config.line_channel_id,
        ) != (staging.url, staging.google_web, staging.line):
            raise Rejected("STAGING_TARGET_REJECTED")
        materials = collect(config)
        owner_session = (owner_factory or owner.OwnerSession)(
            materials.asc.material, owner_email=email
        )
        target = owner_session.inventory()
        config = replace(config, build=target.planned_build)
        sign, asc = frames(materials, config, target)
        session = session_factory(sign, asc, sha=sha)
        # Full wire bound, ASC scope and input checks precede durable intent/mutation.
        journal = journal_factory(create=True)
        journal.record(
            "START",
            sha=sha,
            nonce=session.nonce,
            version=config.version,
            build=config.build,
            previous_build=target.previous_build,
            issued=session.issued,
            expires=session.issued + wire.TTL,
        )
        session.journal = journal
        if session.begin()["status"] != "WAITING":
            raise Rejected()
        for _ in range(40):
            status = session.advance()["status"]
            if status == "APPROVED":
                break
            if status not in {"WAITING", "UPLOADING"}:
                raise Rejected()
            if status == "WAITING":
                sleep(15)
        else:
            raise Rejected("OBSERVATION_TIMEOUT")
        settle(session, sleep=sleep)
        state = session.public()
        absent = state["current_absence_verified"]
        if not state["retention_resolved"] or state["cancel_unresolved"]:
            raise Rejected("RETENTION_UNRESOLVED")
        artifact = session.artifact(version=config.version, build=config.build)
        # Run success alone is not signing cleanup or Apple processing evidence.
        recovered_result = recovery.result_from_logs(session.logs())
        cleanup = recovered_result["cleanup_verified"]
        outcome, _ = recovery.rediscover(
            materials.asc.material,
            target=target.upload_target(),
            artifact=artifact,
            binding=wire.Binding(sha, session.nonce, str(session.run_id)),
            version=config.version,
            build=config.build,
        )
        reason = outcome.classification
    except (KeyboardInterrupt, Exception) as error:
        if type(error) in {Rejected, intake.Rejected} or (
            type(error).__module__ == owner.__name__
        ):
            code = error.args[0] if len(error.args) == 1 else "OPERATION_UNRESOLVED"
            reason = code if code in REASONS else "OPERATION_UNRESOLVED"
    finally:
        if session is not None:
            state = finalize_session(session, sleep=sleep)
            absent = state["current_absence_verified"]
            if not state["retention_resolved"]:
                reason = "RETENTION_UNRESOLVED"
            if session.run_id and session.job_status != "COMPLETED":
                reason = "OPERATION_UNRESOLVED"
        materials = None
        try:
            result_record(journal, reason, cleanup=cleanup, absent=absent)
        finally:
            if journal is not None:
                journal.close()
    return emit(
        reason,
        run_id=session.run_id if session else None,
        cleanup=cleanup,
        secret_absence=absent,
    )


def asc_recovery_input(*, prompt=preparation.hidden, reader_factory=intake.Reader):
    """Fresh ASC-only custody: no P12/profile/Apple Login read on recovery."""
    key_id = prompt("ASC API key ID (10 characters, hidden): ")
    issuer = prompt("ASC API issuer ID (UUID, hidden): ")
    email = prompt("Owner Apple account email (hidden): ")
    path = intake._path(prompt("Existing ASC p8 absolute path (hidden): "))
    reader = reader_factory()
    try:
        intake.inputs._identifier(key_id)
        intake.inputs._issuer(issuer)
        reader.directory(path.parent)
        pem = reader.file(path, 4096)
        asc = intake.inputs.load_asc_key(pem, key_id=key_id, issuer_id=issuer)
        reader.verify()
        return asc, email
    finally:
        reader.close()


def recover_operation(
    *, journal_factory=journal_module.Journal.open, asc_input=asc_recovery_input
):
    """Original GitHub cleanup, then ASC GET only after optional fresh ASC input."""
    from tools import ios_testflight_owner as owner

    journal = journal_factory(create=False)
    try:
        session = dispatch.Session.recover(journal)
        session.recover_run()
        if session.run_id:
            session.observe()
        state = finalize_session(session)
        reason = "OPERATION_UNRESOLVED"
        cleanup = False
        if (
            journal.intact
            and session.run_id
            and session.job_status == "COMPLETED"
            and state["current_absence_verified"]
        ):
            start = journal.events[0]["data"]
            artifact = session.artifact(version=start["version"], build=start["build"])
            public = recovery.result_from_logs(session.logs())
            cleanup = public["cleanup_verified"]
            asc, email = asc_input()
            target = owner.OwnerSession(asc, owner_email=email).inventory(
                version=start["version"]
            )
            outcome, _ = recovery.rediscover(
                asc,
                target=target.upload_target(),
                artifact=artifact,
                binding=wire.Binding(start["sha"], start["nonce"], str(session.run_id)),
                version=start["version"],
                build=start["build"],
            )
            reason = (
                outcome.classification
                if state["retention_resolved"]
                else "RETENTION_UNRESOLVED"
            )
        result_record(
            journal, reason, cleanup=cleanup, absent=state["current_absence_verified"]
        )
        return emit(
            reason,
            run_id=session.run_id,
            cleanup=cleanup,
            secret_absence=state["current_absence_verified"],
        )
    finally:
        journal.close()


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if args not in (["--preflight"], ["--execute"], ["--recover"]):
            raise Rejected("SOURCE_REJECTED")
        sha, staging = preflight(recovery_only=args == ["--recover"])
        if args == ["--preflight"]:
            emit("PREFLIGHT_PASSED")
            return 0
        if args == ["--recover"]:
            recover_operation()
            return 2  # Cleanup/recovery does not imply delivery acceptance.
        print(
            "scope=IOS-TF-01 action=sign_inspect_upload target=owner_staging distribution=none",
            flush=True,
        )
        config, email = metadata(staging)
        result = execute(sha, staging, config, email)
        return 0 if result["classification"] == "BUILD_VALID_UNDISTRIBUTED" else 2
    except BaseException as error:
        reason = (
            error.args[0]
            if type(error) is Rejected and len(error.args) == 1
            else "OPERATION_UNRESOLVED"
        )
        emit(reason)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
