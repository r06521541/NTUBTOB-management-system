"""IOS-TF-01 Windows entry point: preflight, one sign/upload, or recovery.

Owner-only distribution is deliberately a separate transition requiring actual
staging runtime/schema postchecks; an accepted IPA does not establish them.
Secrets stay in memory. Optional Owner-edited JSON persists metadata, not authority.
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
from tools import ios_testflight_diagnostics as diagnostics
from tools import ios_testflight_dispatch as dispatch
from tools import ios_testflight_hosted as hosted
from tools import ios_testflight_intake as intake
from tools import ios_testflight_journal as journal_module
from tools import ios_testflight_key_custody as key_custody
from tools import ios_testflight_owner as owner
from tools import ios_testflight_recovery as recovery
from tools import ios_testflight_settings as settings
from tools import ios_testflight_signing as signing
from tools import ios_testflight_staging as staging_contract
from tools import ios_testflight_unsent as unsent
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
            "ASC_PREFLIGHT_PASSED",
            "JOURNAL_REJECTED",
            "EXISTING_OPERATION",
            "READ_ONLY_STATUS",
            "UNSENT_READY",
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
    | settings.REASONS
    | key_custody.REASONS
    | owner.REQUEST_REASONS
    | unsent.REASONS
)


class Rejected(Exception):
    def __init__(
        self,
        reason="OPERATION_UNRESOLVED",
        *,
        stage=None,
        failure=None,
        cleanup_failure=None,
    ):
        super().__init__(
            reason
            if type(reason) is str and reason in REASONS
            else "OPERATION_UNRESOLVED"
        )
        self.stage = (
            stage if type(stage) is str and stage in owner.INVENTORY_STAGES else None
        )
        self.failure = diagnostics.sanitize(failure)
        self.cleanup_failure = diagnostics.sanitize(cleanup_failure)


@dataclass(frozen=True, repr=False)
class Staging:
    url: str
    google_web: str
    line: str
    apple_configured: bool


def emit(
    reason,
    *,
    run_id=None,
    cleanup=False,
    secret_absence=False,
    stage=None,
    failure=None,
    cleanup_failure=None,
    external_write_state="UNKNOWN",
    secret_transfer_state="UNRESOLVED",
    observation=None,
):
    result = {
        "classification": (
            reason
            if type(reason) is str and reason in REASONS
            else "OPERATION_UNRESOLVED"
        ),
        "target": "owner_testflight_staging",
        "standing_authorization": "IOS-TF-01",
        "run_id": run_id if type(run_id) is int and run_id > 0 else None,
        "cleanup_verified": cleanup is True,
        "secret_absence_verified": secret_absence is True,
        "owner_distribution_verified": False,
        "device_verified": False,
        "release_authorized": False,
        "failure": diagnostics.sanitize(failure),
        "cleanup_failure": diagnostics.sanitize(cleanup_failure),
        "external_write_state": (
            external_write_state
            if type(external_write_state) is str
            and external_write_state in {"NOT_ATTEMPTED", "ATTEMPTED", "UNKNOWN"}
            else "UNKNOWN"
        ),
        "secret_transfer_state": (
            secret_transfer_state
            if type(secret_transfer_state) is str
            and secret_transfer_state
            in {"NOT_ATTEMPTED", "ABSENCE_VERIFIED", "UNRESOLVED"}
            else "UNRESOLVED"
        ),
        "retry_authorized": False,
        "next_action": "READ_ONLY_REVIEW" if diagnostics.valid(failure) else "NONE",
    }
    if result["classification"] in {
        "OPERATION_UNRESOLVED",
        "RETENTION_UNRESOLVED",
        "RECONCILIATION_UNRESOLVED",
    }:
        result["next_action"] = "READ_ONLY_REVIEW"
    if type(observation) is dict:
        state = observation.get("journal_state")
        if type(state) is str and state in {"INTACT", "DAMAGED"}:
            result["journal_state"] = state
        if type(observation.get("source_matches")) is bool:
            result["source_matches"] = observation["source_matches"]
        attempt = observation.get("attempt_number")
        if type(attempt) is int and attempt in {1, 2}:
            result["attempt_number"] = attempt
    if type(stage) is str and stage in owner.INVENTORY_STAGES:
        result["stage"] = stage
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return result


def failure_for(error, stage, check):
    """Only known exception types affect fixed codes; never stringify an error."""
    if (
        type(error) in {Rejected, dispatch.Rejected, unsent.Rejected}
        and error.failure is not None
    ):
        return error.failure
    if isinstance(error, KeyboardInterrupt):
        reason = "INTERRUPTED"
    elif type(error) is journal_module.Rejected:
        reason = "JOURNAL_REJECTED"
    elif type(error) in {
        Rejected,
        intake.Rejected,
        owner.Rejected,
        settings.Rejected,
        key_custody.Rejected,
        unsent.Rejected,
        intake.inputs.InputError,
    }:
        reason = "CHECK_REJECTED"
    else:
        reason = "UNEXPECTED_INTERNAL_ERROR"
    return diagnostics.failure(stage, check, reason)


def ensure_new_operation():
    try:
        state = journal_module.new_operation_preflight()
    except (KeyboardInterrupt, Exception) as error:
        raise Rejected(
            "JOURNAL_REJECTED",
            failure=failure_for(error, "journal_preflight", "journal_path"),
        ) from None
    if state == "EXISTING_OPERATION":
        raise Rejected(
            "EXISTING_OPERATION",
            failure=diagnostics.failure(
                "journal_preflight", "existing_journal", "EXISTING_OPERATION"
            ),
        )
    if state not in {"READY_NO_JOURNAL", "READY_ROOT_NOT_CREATED"}:
        raise Rejected(
            "JOURNAL_REJECTED",
            failure=diagnostics.failure(
                "journal_preflight", "journal_path", "JOURNAL_REJECTED"
            ),
        )


def readonly_status(sha):
    """Observe the original journal without recovery, inputs or external calls."""
    value = journal_module.Journal.open(create=False, readonly=True)
    try:
        observed = journal_module.summary(value, sha)
    finally:
        value.close()
    return emit(
        "READ_ONLY_STATUS",
        failure=observed["failure"],
        external_write_state=observed["external_write_state"],
        secret_transfer_state=observed["secret_transfer_state"],
        secret_absence=observed["secret_absence_verified"],
        observation=observed,
    )


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
        try:
            probe.policy()
            probe.context("dispatch_preflight", "repository")
            repository = probe.get(dispatch.API)
            if repository.get("private") is not False:
                raise Rejected(
                    "SOURCE_REJECTED"
                )  # Standard public runners, no paid/storage exports.
            if set(wire.SECRETS) & probe.listing():
                raise Rejected("RETENTION_UNRESOLVED")
            for name in wire.SECRETS:
                probe.context("dispatch_preflight", "secret_absence")
                if probe.call("GET", dispatch.SECRET + name)[0] != 404:
                    raise Rejected("RETENTION_UNRESOLVED")
        except (KeyboardInterrupt, Exception) as error:
            detail = diagnostics.sanitize(probe.public().get("failure")) or failure_for(
                error, probe.stage, probe.check
            )
            reason = (
                error.args[0] if type(error) is Rejected else "OPERATION_UNRESOLVED"
            )
            raise Rejected(reason, failure=detail) from None
    return sha, staging_scope() if not recovery_only else None


def metadata(staging, *, prompt=preparation.hidden):
    """One visible batch; known staging URL/LINE/Web audience are not re-requested."""
    team = intake.read_field("APPLE_TEAM", prompt=prompt)
    asc_key = intake.read_field("ASC_KEY_ID", prompt=prompt)
    issuer = intake.read_field("ASC_ISSUER", prompt=prompt)
    login_key = "NOTUSED000"  # No Apple Login key requested/read by sign/upload.
    ios_client = intake.read_field(
        "GOOGLE_IOS", prompt=prompt, google_web=staging.google_web
    )
    email = intake.read_field("OWNER_EMAIL", prompt=prompt)
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


def settings_metadata(staging):
    values = settings.load(google_web=staging.google_web)
    config = intake.Config(
        values["apple_team_id"],
        values["asc_key_id"],
        values["asc_issuer_id"],
        "NOTUSED000",
        staging.url,
        values["google_ios_client_id"],
        staging.google_web,
        staging.line,
        VERSION,
        1,
        asc_path=values["asc_p8_path"],
    )
    intake.check_custody(config)
    return config, values["owner_email"]


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


def failure_record(journal, failure):
    if (
        journal is not None
        and journal.intact
        and diagnostics.valid(failure)
        and not any(
            row["event"] == "FAILURE"
            for row in journal_module.active_events(journal.events)
        )
    ):
        journal.record("FAILURE", **failure)


def result_record(journal, reason, *, cleanup, absent, failure=None):
    if journal is not None and journal.intact:
        failure_record(journal, failure)
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
    successor_journal=None,
    unsent_verify=None,
):
    session = materials = None
    journal = successor_journal
    successor_started = False
    verifier = unsent_verify or unsent.verify
    cleanup = absent = False
    reason = "OPERATION_UNRESOLVED"
    failure = cleanup_failure = None
    stage, check = "journal_preflight", "journal_path"
    state = {}
    external, transferred = "UNKNOWN", "UNRESOLVED"
    try:
        if successor_journal is None:
            ensure_new_operation()
        else:
            stage, check = "recovery", "journal_integrity"
            verifier(journal, sha)
        external, transferred = "NOT_ATTEMPTED", "NOT_ATTEMPTED"
        stage, check = "saved_inputs", "settings"
        if (
            config.api_base_url,
            config.google_web_client_id,
            config.line_channel_id,
        ) != (staging.url, staging.google_web, staging.line):
            raise Rejected("STAGING_TARGET_REJECTED")
        stage, check = "signing_input", "signing_material"
        materials = collect(config)
        stage, check = "asc_preflight", "asc_scope"
        owner_session = (owner_factory or owner.OwnerSession)(
            materials.asc.material, owner_email=email
        )
        target = owner_session.inventory()
        config = replace(config, build=target.planned_build)
        stage, check = "frame_validation", "frames"
        sign, asc = frames(materials, config, target)
        session = session_factory(sign, asc, sha=sha)
        # Full wire bound, ASC scope and input checks precede durable intent/mutation.
        stage, check = "journal_open", "journal_path"
        parent = {}
        if successor_journal is None:
            journal = journal_factory(create=True)
        else:
            # Fresh GET proof after every private prompt, with the same exclusive
            # handle held. A prior check-mode or pre-input proof is never reused.
            stage, check = "recovery", "journal_integrity"
            proof = verifier(journal, sha)
            parent = {"parent_sha256": proof.consume(journal, sha)}
        stage, check = "journal_start", "journal_write"
        journal.record(
            "START" if successor_journal is None else "UNSENT_SUCCESSOR",
            sha=sha,
            nonce=session.nonce,
            version=config.version,
            build=config.build,
            previous_build=target.previous_build,
            issued=session.issued,
            expires=session.issued + wire.TTL,
            **parent,
        )
        successor_started = successor_journal is not None
        session.journal = journal
        stage, check = "dispatch_preflight", "dispatch_result"
        if session.begin()["status"] != "WAITING":
            raise Rejected()
        for _ in range(40):
            stage, check = "awaiting_job", "job_status"
            status = session.advance()["status"]
            if status == "APPROVED":
                break
            if status not in {"WAITING", "UPLOADING"}:
                raise Rejected()
            if status == "WAITING":
                sleep(15)
        else:
            raise Rejected("OBSERVATION_TIMEOUT")
        stage, check = "observe_run", "job_status"
        settle(session, sleep=sleep)
        state = session.public()
        absent = state["current_absence_verified"]
        if not state["retention_resolved"] or state["cancel_unresolved"]:
            raise Rejected("RETENTION_UNRESOLVED")
        stage, check = "artifact_verification", "artifact"
        artifact = session.artifact(version=config.version, build=config.build)
        # Run success alone is not signing cleanup or Apple processing evidence.
        recovered_result = recovery.result_from_logs(session.logs())
        cleanup = recovered_result["cleanup_verified"]
        stage, check = "apple_reconcile", "apple_result"
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
        if session is not None:
            try:
                failure = diagnostics.sanitize(session.public().get("failure"))
            except (KeyboardInterrupt, Exception):
                pass
        failure = failure or failure_for(error, stage, check)
        if type(error) in {
            Rejected,
            intake.Rejected,
            owner.Rejected,
            journal_module.Rejected,
            unsent.Rejected,
        }:
            code = error.args[0] if len(error.args) == 1 else "OPERATION_UNRESOLVED"
            if type(error) is owner.Rejected and code == "OWNER_SCOPE_REJECTED":
                code = "ASC_SCOPE_REJECTED"
            reason = code if code in REASONS else "OPERATION_UNRESOLVED"
        try:
            if successor_journal is None or successor_started:
                failure_record(journal, failure)
        except (KeyboardInterrupt, Exception):
            if journal is not None:
                journal.intact = False
            cleanup_failure = diagnostics.failure(
                "cleanup", "journal_write", "JOURNAL_REJECTED"
            )
    finally:
        if session is not None and (successor_journal is None or successor_started):
            try:
                state = finalize_session(session, sleep=sleep)
                failure = failure or diagnostics.sanitize(state.get("failure"))
                cleanup_failure = cleanup_failure or diagnostics.sanitize(
                    state.get("cleanup_failure")
                )
                absent = state["current_absence_verified"] is True
                external = state.get("external_write_state", "UNKNOWN")
                transferred = state.get("secret_transfer_state", "UNRESOLVED")
                if not state["retention_resolved"]:
                    reason = "RETENTION_UNRESOLVED"
                if session.run_id and session.job_status != "COMPLETED":
                    reason = "OPERATION_UNRESOLVED"
            except (KeyboardInterrupt, Exception) as error:
                cleanup_failure = failure_for(error, "cleanup", "retention")
                absent, external, transferred = False, "UNKNOWN", "UNRESOLVED"
                reason = "RETENTION_UNRESOLVED"
        elif session is not None:
            # No successor was acknowledged: do not finalize against the old
            # attempt or perform remote cleanup. Drop the new private frames.
            session.signing = session.asc = b""
        materials = None
        if journal is not None and not journal.intact:
            reason = "JOURNAL_REJECTED"
            absent, external, transferred = False, "UNKNOWN", "UNRESOLVED"
        try:
            if successor_journal is None or successor_started:
                result_record(
                    journal, reason, cleanup=cleanup, absent=absent, failure=failure
                )
        except (KeyboardInterrupt, Exception):
            cleanup_failure = cleanup_failure or diagnostics.failure(
                "cleanup", "journal_write", "JOURNAL_REJECTED"
            )
            reason = "JOURNAL_REJECTED"
            absent, external, transferred = False, "UNKNOWN", "UNRESOLVED"
        finally:
            if journal is not None:
                try:
                    journal.close()
                except (KeyboardInterrupt, Exception):
                    cleanup_failure = cleanup_failure or diagnostics.failure(
                        "cleanup", "journal_write", "JOURNAL_REJECTED"
                    )
                    reason = "JOURNAL_REJECTED"
        failure = failure or cleanup_failure
    return emit(
        reason,
        run_id=session.run_id if session else None,
        cleanup=cleanup,
        secret_absence=absent,
        failure=failure,
        cleanup_failure=cleanup_failure,
        external_write_state=external,
        secret_transfer_state=transferred,
    )


def asc_preflight(config, email, *, reader_factory=intake.Reader, owner_factory=None):
    """GET-only inventory using saved ASC custody; no P12 or mutation calls.

    This ephemeral check is not dispatch authority. Execution recollects materials
    and rechecks remote scope, so an earlier PASS cannot skip either check.
    """
    reader = lookup = None
    try:
        intake._config(config)
        path = intake.validate_field("ASC_PATH", config.asc_path)
        reader = reader_factory()
        reader.directory(path.parent)
        pem = reader.file(path, 4096)
        asc = intake.inputs.load_asc_key(
            pem, key_id=config.asc_key_id, issuer_id=config.asc_issuer_id
        )
        reader.verify()
        lookup = (owner_factory or owner.OwnerSession)(asc, owner_email=email)
        lookup.inventory(version=config.version)
    except (Exception, KeyboardInterrupt) as error:
        reason = "ASC_SCOPE_REJECTED"
        if type(error) in {
            intake.Rejected,
            intake.inputs.InputError,
            intake.custody.CustodyError,
            owner.Rejected,
        }:
            code = error.args[0] if len(error.args) == 1 else None
            if type(code) is str and code in REASONS:
                reason = code
        raise Rejected(
            reason, stage=lookup.stage if lookup is not None else "asc_input"
        ) from None
    finally:
        if reader is not None:
            try:
                reader.close()
            except (Exception, KeyboardInterrupt):
                raise Rejected("CLOSE_UNRESOLVED", stage="asc_input") from None


def asc_recovery_input(*, prompt=preparation.hidden, reader_factory=intake.Reader):
    """Fresh ASC-only custody: no P12/profile/Apple Login read on recovery."""
    key_id = intake.read_field("ASC_KEY_ID", prompt=prompt)
    issuer = intake.read_field("ASC_ISSUER", prompt=prompt)
    email = intake.read_field("OWNER_EMAIL", prompt=prompt)
    path = intake.read_field("ASC_PATH", prompt=prompt)
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
    session = None
    state = {}
    failure = cleanup_failure = None
    reason = "OPERATION_UNRESOLVED"
    cleanup = False
    durability_failed = False
    stage, check = "recovery", "journal_integrity"
    try:
        session = dispatch.Session.recover(journal)
        session.recover_run()
        if session.run_id:
            session.observe()
        stage, check = "cleanup", "retention"
        state = finalize_session(session)
        if (
            journal.intact
            and session.run_id
            and session.job_status == "COMPLETED"
            and state["current_absence_verified"]
        ):
            stage, check = "artifact_verification", "artifact"
            start = journal_module.active_events(journal.events)[0]["data"]
            artifact = session.artifact(version=start["version"], build=start["build"])
            public = recovery.result_from_logs(session.logs())
            cleanup = public["cleanup_verified"]
            stage, check = "apple_reconcile", "apple_result"
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
    except (KeyboardInterrupt, Exception) as error:
        failure = failure_for(error, stage, check)
        if stage == "cleanup":
            cleanup_failure = failure
    finally:
        # Preserve observed facts and the primary cause across output/close faults.
        # This projection never initiates another cancel, transfer or upload.
        if session is not None:
            state = session.public()
            failure = diagnostics.sanitize(state.get("failure")) or failure
            cleanup_failure = (
                diagnostics.sanitize(state.get("cleanup_failure")) or cleanup_failure
            )
        try:
            result_record(
                journal,
                reason,
                cleanup=cleanup,
                absent=state.get("current_absence_verified") is True,
                failure=failure,
            )
        except (KeyboardInterrupt, Exception) as error:
            durability_failed = True
            reason = "JOURNAL_REJECTED"
            cleanup_failure = cleanup_failure or failure_for(
                error, "cleanup", "journal_write"
            )
        try:
            journal.close()
        except (KeyboardInterrupt, Exception) as error:
            durability_failed = True
            reason = "JOURNAL_REJECTED"
            cleanup_failure = cleanup_failure or failure_for(
                error, "cleanup", "journal_write"
            )
    uncertain_journal = durability_failed or not journal.intact
    return emit(
        reason,
        run_id=session.run_id if session is not None else None,
        cleanup=cleanup and not uncertain_journal,
        secret_absence=state.get("current_absence_verified") is True
        and not uncertain_journal,
        failure=failure or cleanup_failure,
        cleanup_failure=cleanup_failure,
        external_write_state=(
            "UNKNOWN"
            if uncertain_journal
            else state.get("external_write_state", "UNKNOWN")
        ),
        secret_transfer_state=(
            "UNRESOLVED"
            if uncertain_journal
            else state.get("secret_transfer_state", "UNRESOLVED")
        ),
    )


def _unsent_preparation(sha, staging, *, execute_requested):
    """Own one exclusive handle through preparation and transfer it to execute."""
    journal = None
    rejected = None
    result = None
    stage, check = "recovery", "journal_integrity"
    try:
        journal = journal_module.Journal.open(
            **(
                {"create": False}
                if execute_requested
                else {"create": False, "readonly": True}
            )
        )
        unsent.verify(journal, sha)
        if execute_requested:
            print(
                "scope=IOS-TF-01 action=confirmed_unsent_successor target=owner_staging distribution=none",
                flush=True,
            )
            stage, check = "saved_inputs", "settings"
            config, email = settings_metadata(staging)
            stage, check = "asc_preflight", "asc_scope"
            asc_preflight(config, email)
            result = execute(sha, staging, config, email, successor_journal=journal)
            journal = None  # execute owns close, including failure paths
    except (KeyboardInterrupt, Exception) as error:
        reason = (
            error.args[0]
            if type(error)
            in {
                Rejected,
                unsent.Rejected,
                journal_module.Rejected,
                settings.Rejected,
                intake.Rejected,
            }
            and len(error.args) == 1
            else "OPERATION_UNRESOLVED"
        )
        rejected = Rejected(reason, failure=failure_for(error, stage, check))
    finally:
        if journal is not None:
            try:
                journal.close()
            except (KeyboardInterrupt, Exception) as error:
                detail = failure_for(error, "cleanup", "journal_write")
                if rejected is None:
                    rejected = Rejected("JOURNAL_REJECTED", failure=detail)
                else:
                    rejected.cleanup_failure = detail
    if rejected is not None:
        raise rejected from None
    return (
        result
        if execute_requested
        else emit(
            "UNSENT_READY",
            external_write_state="NOT_ATTEMPTED",
            secret_transfer_state="NOT_ATTEMPTED",
        )
    )


def check_unsent(sha):
    """Fresh GET-only readiness; no settings, private inputs or durable proof."""
    return _unsent_preparation(sha, None, execute_requested=False)


def execute_unsent(sha, staging):
    """Explicit one-successor path; never called by ordinary execute or status."""
    return _unsent_preparation(sha, staging, execute_requested=True)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    stage, check = "source_preflight", "source"
    try:
        if args not in (
            ["--preflight"],
            ["--execute"],
            ["--recover"],
            ["--status"],
            ["--check-unsent"],
            ["--execute-unsent", "--settings"],
            ["--prepare-inputs"],
            ["--check-inputs"],
            ["--check-asc"],
            ["--check-key-import"],
            ["--import-asc-key"],
            ["--execute", "--settings"],
        ):
            raise Rejected("SOURCE_REJECTED")
        sha, staging = preflight(recovery_only=args in (["--recover"], ["--status"]))
        if args == ["--check-unsent"]:
            check_unsent(sha)
            return 0
        if args == ["--execute-unsent", "--settings"]:
            result = execute_unsent(sha, staging)
            return 0 if result["classification"] == "BUILD_VALID_UNDISTRIBUTED" else 2
        if args == ["--status"]:
            stage, check = "recovery", "journal_integrity"
            readonly_status(sha)
            return 0
        if args == ["--preflight"]:
            emit("PREFLIGHT_PASSED")
            return 0
        if args == ["--prepare-inputs"]:
            stage, check = "saved_inputs", "settings"
            settings.prepare()
            emit("SETTINGS_TEMPLATE_CREATED")
            return 0
        if args == ["--check-inputs"]:
            stage, check = "saved_inputs", "settings"
            settings_metadata(staging)
            # Syntax and file custody only, not key validity or execution approval.
            emit("SETTINGS_READY")
            return 0
        if args == ["--check-asc"]:
            stage, check = "saved_inputs", "settings"
            config, email = settings_metadata(staging)
            stage, check = "asc_preflight", "asc_scope"
            asc_preflight(config, email)
            emit("ASC_PREFLIGHT_PASSED", stage="asc_complete")
            return 0
        if args in (["--check-key-import"], ["--import-asc-key"]):
            stage, check = "saved_inputs", "settings"
            action = (
                key_custody.check_import
                if args == ["--check-key-import"]
                else key_custody.import_key
            )
            classification = action(google_web=staging.google_web)
            emit(classification)
            return (
                0
                if classification in {"ASC_IMPORT_READY", "ASC_IMPORT_COMPLETE"}
                else 2
            )
        if args == ["--recover"]:
            stage, check = "recovery", "journal_integrity"
            recover_operation()
            return 2  # Cleanup/recovery does not imply delivery acceptance.
        stage, check = "journal_preflight", "journal_path"
        ensure_new_operation()
        print(
            "scope=IOS-TF-01 action=sign_inspect_upload target=owner_staging distribution=none",
            flush=True,
        )
        stage, check = "saved_inputs", "settings"
        config, email = (
            settings_metadata(staging)
            if args == ["--execute", "--settings"]
            else metadata(staging)
        )
        if config.asc_path is None:
            config = replace(config, asc_path=str(intake.read_field("ASC_PATH")))
        stage, check = "asc_preflight", "asc_scope"
        asc_preflight(config, email)
        result = execute(sha, staging, config, email)
        return 0 if result["classification"] == "BUILD_VALID_UNDISTRIBUTED" else 2
    except BaseException as error:
        reason = (
            error.args[0]
            if type(error)
            in {
                Rejected,
                intake.Rejected,
                intake.inputs.InputError,
                settings.Rejected,
                key_custody.Rejected,
                journal_module.Rejected,
                unsent.Rejected,
            }
            and len(error.args) == 1
            else "OPERATION_UNRESOLVED"
        )
        emit(
            reason,
            stage=error.stage if type(error) is Rejected else None,
            failure=failure_for(error, stage, check),
            cleanup_failure=error.cleanup_failure if type(error) is Rejected else None,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
