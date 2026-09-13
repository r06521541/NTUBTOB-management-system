"""One private GitHub session with an optional reviewed durable event sink.

Six PUTs are not a transaction. Owner-exclusive configuration is required; no
remote compare-and-swap exists. Caller must retain state and never restart an
uncertain operation. Deadline expiration can leave remote secrets unresolved.
"""

import secrets
import threading
import time

from tools import ios_profile_intake as primitives
from tools import ios_testflight_diagnostics as diagnostics
from tools import ios_testflight_journal as journal_module
from tools import ios_testflight_wire as wire

API = "repos/" + wire.REPO
OWNER = "r06521541"
ENV = API + "/environments/" + wire.ENVIRONMENT
SECRET = ENV + "/secrets/"
WORKFLOW = API + "/actions/workflows/" + wire.WORKFLOW
JOB = "owner_testflight"
STATES = {
    "NEW",
    "WAITING",
    "UPLOADING",
    "APPROVED",
    "STOP",
    "UNCERTAIN",
    "COMPLETED",
    "CLEANED",
}


class Rejected(Exception):
    def __init__(self, detail=None):
        super().__init__("DISPATCH_REJECTED")
        self.failure = diagnostics.sanitize(detail)


class Session:
    def __init__(
        self, signing_frame, asc_frame, *, sha, api=None, journal=None, nonce=None
    ):
        self.nonce = secrets.token_hex(32) if nonce is None else nonce
        self.sha = sha
        self.issued = int(time.time())
        try:
            wire.pack(
                signing_frame,
                asc_frame,
                wire.Binding(sha, self.nonce, "1"),
                now=self.issued,
            )
        except Exception:
            raise Rejected(
                diagnostics.failure("frame_validation", "frames", "CHECK_REJECTED")
            ) from None
        self.signing = signing_frame
        self.asc = asc_frame
        self.api = api if api is not None else primitives.GitHub()
        self.deadline = time.monotonic() + 7200
        self.requests = 0
        self.state = "NEW"
        self.run_id = None
        self.workflow_id = self.environment_id = None
        self.dispatched = self.approval_attempted = self.cancel_attempted = False
        self.attempted = []
        self.uploaded = []
        self.deleted = set()
        self.absent = set()
        self.http_uncertain = False
        self.cancel_unresolved = False
        self.job_id = None
        self.job_status = "NOT_CHECKED"
        self.lock = threading.Lock()
        self.journal = journal
        self.journal_failed = False
        self.recovery_only = False
        self.terminal_recorded = False
        self.cleanup_budget_started = False
        self.failure = self.cleanup_failure = None
        self.stage, self.check = "unknown", "unexpected"
        self.external_attempted = self.external_unknown = False

    def context(self, stage, check="unexpected"):
        self.stage, self.check = stage, check

    def checking(self, check, default_stage):
        if not diagnostics.valid(
            {"stage": self.stage, "check": check, "reason": "CHECK_REJECTED"}
        ):
            self.stage = default_stage
        self.check = check

    def remember(self, detail):
        detail = diagnostics.sanitize(detail) or diagnostics.failure(
            "unknown", "unexpected", "UNEXPECTED_INTERNAL_ERROR"
        )
        if self.failure is None:
            self.failure = detail
        if detail["stage"] == "cleanup" and self.cleanup_failure is None:
            self.cleanup_failure = detail

    def reject(self, reason="CHECK_REJECTED"):
        detail = diagnostics.failure(self.stage, self.check, reason)
        self.remember(detail)
        raise Rejected(detail)

    def http_failure(self, status):
        reason = {
            401: "HTTP_UNAUTHENTICATED",
            403: "HTTP_FORBIDDEN",
            404: "HTTP_NOT_FOUND",
            429: "HTTP_RATE_LIMITED",
        }.get(
            status,
            (
                "HTTP_SERVER_ERROR"
                if type(status) is int and 500 <= status <= 599
                else "HTTP_STATUS_REJECTED"
            ),
        )
        self.remember(diagnostics.failure(self.stage, self.check, reason))
        return reason

    def record(self, event, **data):
        if self.journal is None:
            return  # Callable adapter only; the real operator requires Journal.
        try:
            if self.journal_failed or not self.journal.intact:
                raise Rejected()
            self.journal.record(event, **data)
        except BaseException as error:
            self.journal_failed = self.http_uncertain = True
            self.external_unknown = True
            detail = diagnostics.failure(
                self.stage,
                "journal_write",
                (
                    "INTERRUPTED"
                    if isinstance(error, KeyboardInterrupt)
                    else "JOURNAL_REJECTED"
                ),
            )
            self.remember(detail)
            raise Rejected(detail) from None

    @classmethod
    def recover(cls, journal, *, api=None):
        """Never reload payloads or grant sign/approve/reupload authority."""
        events = journal_module.active_events(journal.events)
        if not events or events[0]["event"] != "START":
            raise Rejected()
        start = events[0]["data"]
        session = cls(
            b"{}",
            b"{}",
            sha=start["sha"],
            nonce=start["nonce"],
            api=api,
            journal=journal,
        )
        session.signing = session.asc = b""
        session.recovery_only = True
        session.issued = start["issued"]
        # Fresh GET/cleanup budget only; original private-ingress TTL is not extended.
        session.deadline = time.monotonic() + 1800
        session.cleanup_budget_started = True
        session.journal_failed = not journal.intact
        session.state = "UNCERTAIN"
        session.http_uncertain = not journal.intact
        confirmations = set()
        attempts = set()
        for item in events[1:]:
            event, data = item["event"], item["data"]
            if event.endswith("_ATTEMPT"):
                attempts.add((event.removesuffix("_ATTEMPT"), data.get("name")))
                session.external_attempted = True
            if event.endswith("_CONFIRMED"):
                confirmations.add((event.removesuffix("_CONFIRMED"), data.get("name")))
            if event == "DISPATCH_ATTEMPT":
                session.dispatched = True
            elif event == "DISPATCH_CONFIRMED":
                session.run_id = data["run_id"]
                session.workflow_id = data["workflow_id"]
                session.environment_id = data["environment_id"]
            elif event == "JOB_BOUND":
                session.job_id = data["job_id"]
            elif event == "SECRET_PUT_ATTEMPT":
                session.attempted.append(data["name"])
            elif event == "SECRET_PUT_CONFIRMED":
                session.uploaded.append(data["name"])
            elif event == "SECRET_DELETE_ATTEMPT":
                session.deleted.add(data["name"])
            elif event == "APPROVAL_ATTEMPT":
                session.approval_attempted = True
            elif event == "CANCEL_ATTEMPT":
                session.cancel_attempted = session.cancel_unresolved = True
            elif event == "TERMINAL":
                session.terminal_recorded = True
            elif event == "UNCERTAIN":
                session.http_uncertain = True
            elif event == "FAILURE":
                session.remember(
                    diagnostics.sanitize(data)
                    or diagnostics.failure(
                        "recovery", "unexpected", "LEGACY_REASON_UNAVAILABLE"
                    )
                )
        session.http_uncertain |= bool(attempts - confirmations)
        session.external_unknown = session.http_uncertain
        if session.failure is None and (
            session.http_uncertain or any(e["event"] == "RESULT" for e in events)
        ):
            session.remember(
                diagnostics.failure(
                    "recovery", "unexpected", "LEGACY_REASON_UNAVAILABLE"
                )
            )
        # Historical absence/terminal results are not fresh remote-state evidence.
        session.absent.clear()
        return session

    def __repr__(self):
        return "<TestFlightDispatchSession>"

    def public(self):
        return {
            "status": self.state if self.state in STATES else "UNCERTAIN",
            "run_id": self.run_id,
            "current_absence_verified": bool(self.attempted)
            and set(self.attempted) <= self.absent,
            "retention_resolved": set(self.attempted) <= self.absent
            and not self.http_uncertain,
            "http_uncertain": self.http_uncertain,
            "cancel_unresolved": self.cancel_unresolved,
            "failure": diagnostics.sanitize(self.failure),
            "cleanup_failure": diagnostics.sanitize(self.cleanup_failure),
            "external_write_state": (
                "UNKNOWN"
                if self.external_unknown or self.journal_failed
                else "ATTEMPTED" if self.external_attempted else "NOT_ATTEMPTED"
            ),
            "secret_transfer_state": (
                "UNRESOLVED"
                if self.journal_failed
                else (
                    "NOT_ATTEMPTED"
                    if not self.attempted
                    else (
                        "ABSENCE_VERIFIED"
                        if set(self.attempted) <= self.absent
                        else "UNRESOLVED"
                    )
                )
            ),
            "job_status": (
                self.job_status
                if self.job_status in {"NOT_CHECKED", "WAITING", "RUNNING", "COMPLETED"}
                else "NOT_CHECKED"
            ),
            "signing_verified": False,
            "upload_authorized": False,
            "release_authorized": False,
        }

    def call(self, method, path, body=None):
        if self.recovery_only and method != "GET":
            allowed = (
                method == "POST"
                and self.run_id is not None
                and path == API + f"/actions/runs/{self.run_id}/cancel"
            ) or (method == "DELETE" and path in {SECRET + n for n in self.attempted})
            if not allowed:
                self.reject("READ_ONLY_REQUIRED")
        if method != "GET" and (
            self.journal_failed
            or (self.journal is not None and not self.journal.intact)
        ):
            self.check = "journal_write"
            self.reject("JOURNAL_REJECTED")
        if self.requests >= 512:
            self.reject("REQUEST_BUDGET_EXHAUSTED")
        if time.monotonic() >= self.deadline:
            self.reject("DEADLINE_EXCEEDED")
        self.requests += 1
        if method != "GET":
            self.external_attempted = True
        try:
            return self.api.call(method, path, body)
        except (Exception, KeyboardInterrupt) as error:
            if method != "GET":
                self.external_unknown = self.http_uncertain = True
            if isinstance(error, KeyboardInterrupt):
                reason = "INTERRUPTED"
            elif isinstance(error, TimeoutError):
                reason = "TRANSPORT_TIMEOUT"
            elif isinstance(error, (OSError, primitives.Rejected)):
                reason = "TRANSPORT_REJECTED"
            else:
                reason = "UNEXPECTED_INTERNAL_ERROR"
            self.reject(reason)

    def restrict_to_cleanup(self):
        """Irreversible, once-only fresh budget; never extend private-ingress TTL."""
        self.signing = self.asc = b""
        self.recovery_only = True
        if not self.cleanup_budget_started:
            self.cleanup_budget_started = True
            self.deadline = time.monotonic() + 300
            self.requests = 0

    def get(self, path):
        status, value = self.call("GET", path)
        if status != 200:
            self.reject(self.http_failure(status))
        return value

    def policy(self):
        self.context("dispatch_preflight", "github_user")
        if self.get("user").get("login") != OWNER:
            self.reject()
        self.check = "repository"
        if self.get(API).get("full_name") != wire.REPO:
            self.reject()
        self.check = "main_head"
        if (
            self.get(API + "/git/ref/heads/main").get("object", {}).get("sha")
            != self.sha
        ):
            self.reject()
        self.check = "workflow"
        workflow = self.get(WORKFLOW)
        if (
            workflow.get("path") != ".github/workflows/" + wire.WORKFLOW
            or workflow.get("state") != "active"
            or type(workflow.get("id")) is not int
        ):
            self.reject()
        self.check = "environment"
        environment = self.get(ENV)
        rules = environment.get("protection_rules", [])
        reviewers = [r for r in rules if r.get("type") == "required_reviewers"]
        if (
            environment.get("name") != wire.ENVIRONMENT
            or type(environment.get("id")) is not int
        ):
            self.reject()
        self.check = "admin_bypass"
        if environment.get("can_admins_bypass") is not False:
            self.reject()
        self.check = "branch_policy"
        if environment.get("deployment_branch_policy") != {
            "protected_branches": False,
            "custom_branch_policies": True,
        }:
            self.reject()
        self.check = "reviewers"
        if (
            len(reviewers) != 1
            or reviewers[0].get("prevent_self_review") is not False
            or [
                (v.get("type"), v.get("reviewer", {}).get("login"))
                for v in reviewers[0].get("reviewers", [])
            ]
            != [("User", OWNER)]
        ):
            self.reject()
        self.check = "protection_rules"
        if any(
            r.get("type") not in {"required_reviewers", "branch_policy"} for r in rules
        ):
            self.reject()
        self.check = "branch_policy"
        branches = self.get(ENV + "/deployment-branch-policies?per_page=100")
        if branches.get("total_count") != 1 or [
            (b.get("name"), b.get("type")) for b in branches.get("branch_policies", [])
        ] != [("main", "branch")]:
            self.reject()
        self.check = "policy_identity"
        if self.workflow_id is not None and (self.workflow_id, self.environment_id) != (
            workflow["id"],
            environment["id"],
        ):
            self.reject()
        self.workflow_id, self.environment_id = workflow["id"], environment["id"]

    def listing(self):
        self.checking("secret_inventory", "dispatch_preflight")
        data = self.get(SECRET.rstrip("/") + "?per_page=100")
        values = data.get("secrets")
        if (
            type(values) is not list
            or type(data.get("total_count")) is not int
            or data["total_count"] != len(values)
            or len(values) > 100
        ):
            self.reject()
        names = [v["name"] for v in values]
        if any(type(n) is not str for n in names) or len(set(names)) != len(names):
            self.reject()
        return set(names)

    def bound(self):
        self.checking("run_binding", "observe_run")
        if type(self.run_id) is not int or self.run_id <= 0 or self.workflow_id is None:
            self.reject()
        value = self.get(API + f"/actions/runs/{self.run_id}")
        expected = {
            "id": self.run_id,
            "workflow_id": self.workflow_id,
            "path": ".github/workflows/" + wire.WORKFLOW,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": self.sha,
            "run_attempt": 1,
            "display_title": "ios-tf-" + self.nonce,
        }
        if (
            any(value.get(k) != v for k, v in expected.items())
            or value.get("repository", {}).get("full_name") != wire.REPO
            or type(value.get("run_attempt")) is not int
        ):
            self.reject()
        return value

    def pending(self):
        self.checking("pending_approval", "awaiting_job")
        values = self.get(API + f"/actions/runs/{self.run_id}/pending_deployments")
        if values == []:
            return False
        if type(values) is not list or len(values) != 1:
            self.reject()
        value = values[0]
        if (
            value.get("environment", {}).get("id") != self.environment_id
            or value.get("environment", {}).get("name") != wire.ENVIRONMENT
            or value.get("current_user_can_approve") is not True
            or [
                (v.get("type"), v.get("reviewer", {}).get("login"))
                for v in value.get("reviewers", [])
            ]
            != [("User", OWNER)]
        ):
            self.reject()
        return True

    def job(self, *, waiting=False):
        self.checking("job_status", "awaiting_job")
        if type(self.run_id) is not int or self.run_id <= 0:
            self.reject()
        data = self.get(
            API + f"/actions/runs/{self.run_id}/attempts/1/jobs?per_page=100"
        )
        jobs = data.get("jobs")
        if (
            type(jobs) is not list
            or type(data.get("total_count")) is not int
            or data["total_count"] != len(jobs)
            or not 1 <= len(jobs) <= 100
        ):
            self.reject()
        matches = [item for item in jobs if item.get("name") == JOB]
        if len(matches) != 1:
            self.reject()
        value = matches[0]
        if (
            type(value.get("id")) is not int
            or value["id"] <= 0
            or value.get("run_id") != self.run_id
            or value.get("head_sha") != self.sha
            or (self.job_id is not None and value["id"] != self.job_id)
        ):
            self.reject()
        status = value.get("status")
        if status not in {
            "queued",
            "waiting",
            "pending",
            "in_progress",
            "completed",
        } or (
            waiting
            and (
                status not in {"queued", "waiting", "pending"}
                or value.get("conclusion") is not None
            )
        ):
            self.reject()
        if self.job_id is None and not self.journal_failed:
            self.record("JOB_BOUND", job_id=value["id"])
        self.job_id = value["id"]
        self.job_status = (
            "COMPLETED"
            if status == "completed"
            else "RUNNING" if status == "in_progress" else "WAITING"
        )
        return value

    def begin(self):
        return self._step(self._begin)

    def _begin(self):
        self.context("dispatch_preflight")
        if self.recovery_only or self.dispatched or self.state != "NEW":
            raise Rejected()
        self.policy()
        self.context("dispatch_preflight", "secret_inventory")
        if set(wire.SECRETS) & self.listing():
            raise Rejected()
        for name in wire.SECRETS:
            self.check = "secret_absence"
            status = self.call("GET", SECRET + name)[0]
            if status != 404:
                self.reject(
                    self.http_failure(status) if status != 200 else "CHECK_REJECTED"
                )
        self.context("dispatch_request", "dispatch_result")
        self.dispatched = True
        self.state = "UNCERTAIN"
        self.record("DISPATCH_ATTEMPT")
        status, value = self.call(
            "POST",
            WORKFLOW + "/dispatches",
            {"ref": "main", "inputs": {"approved_sha": self.sha, "nonce": self.nonce}},
        )
        if (
            status != 200
            or type(value) is not dict
            or type(value.get("workflow_run_id")) is not int
            or not 0 < value["workflow_run_id"] < 10**20
        ):
            self.http_uncertain = True
            self.external_unknown = True
            if status != 200:
                self.reject(self.http_failure(status))
            self.reject()
        self.run_id = value["workflow_run_id"]
        self.record(
            "DISPATCH_CONFIRMED",
            run_id=self.run_id,
            workflow_id=self.workflow_id,
            environment_id=self.environment_id,
        )
        self.state = "WAITING"

    def advance(self):
        return self._step(self._advance)

    def _advance(self):
        self.context("awaiting_job")
        if (
            self.recovery_only
            or self.state not in {"WAITING", "UPLOADING"}
            or self.approval_attempted
        ):
            raise Rejected()
        run = self.bound()
        if run.get("status") not in {"queued", "waiting", "in_progress"}:
            raise Rejected()
        if not self.pending():
            if self.attempted:
                raise Rejected()
            return
        self.job(waiting=True)
        self.policy()
        self.context("secret_transfer", "secret_inventory")
        names = self.listing() & set(wire.SECRETS)
        if names != set(self.uploaded):
            raise Rejected()
        if len(self.uploaded) < len(wire.SECRETS):
            name = wire.SECRETS[len(self.uploaded)]
            self.check = "secret_absence"
            status = self.call("GET", SECRET + name)[0]
            if status != 404:
                self.reject(
                    self.http_failure(status) if status != 200 else "CHECK_REJECTED"
                )
            self.check = "secret_public_key"
            key = self.get(SECRET + "public-key")
            if type(key.get("key_id")) is not str or not key["key_id"]:
                raise Rejected()
            self.check = "frames"
            values = wire.pack(
                self.signing,
                self.asc,
                wire.Binding(self.sha, self.nonce, str(self.run_id)),
                now=self.issued,
            )
            self.check = "secret_public_key"
            encrypted = primitives.encrypt(values[name].encode("ascii"), key["key"])
            self.check = "secret_write"
            self.attempted.append(name)
            self.state = "UNCERTAIN"
            self.record("SECRET_PUT_ATTEMPT", name=name)
            status, _ = self.call(
                "PUT",
                SECRET + name,
                {"key_id": key["key_id"], "encrypted_value": encrypted},
            )
            if status != 201:
                self.http_uncertain = True
                self.external_unknown = True
                self.reject(self.http_failure(status))
            self.uploaded.append(name)
            self.record("SECRET_PUT_CONFIRMED", name=name)
            self.state = "UPLOADING"
        else:
            self.context("approval", "secret_binding")
            for name in wire.SECRETS:
                if self.get(SECRET + name).get("name") != name:
                    raise Rejected()
            self.bound()
            if not self.pending():
                raise Rejected()
            self.job(waiting=True)
            self.check = "approval_result"
            self.approval_attempted = True
            self.state = "UNCERTAIN"
            self.record("APPROVAL_ATTEMPT")
            status, _ = self.call(
                "POST",
                API + f"/actions/runs/{self.run_id}/pending_deployments",
                {
                    "environment_ids": [self.environment_id],
                    "state": "approved",
                    "comment": "IOS-TF-01 Owner-only run",
                },
            )
            if status != 200:
                self.http_uncertain = True
                self.external_unknown = True
                self.reject(self.http_failure(status))
            self.state = "APPROVED"
            self.record("APPROVAL_CONFIRMED")

    def observe(self):
        def operation():
            self.context("observe_run")
            run = self.bound()
            job = self.job()
            if run.get("status") == "completed":
                if job.get("status") != "completed":
                    raise Rejected()
                self.cancel_unresolved = False
                self.state = "COMPLETED" if not self.http_uncertain else "UNCERTAIN"
                if not self.terminal_recorded and not self.journal_failed:
                    self.record("TERMINAL", conclusion=run.get("conclusion", "unknown"))
                    self.terminal_recorded = True

        return self._step(operation)

    def recover_run(self):
        """Discover only the original public nonce-bound run; never dispatch."""

        def operation():
            self.context("recovery")
            if not self.recovery_only or not self.dispatched:
                raise Rejected()
            if self.run_id is not None:
                self.bound()
                return
            self.policy()
            self.context("recovery", "run_listing")
            result = self.get(
                WORKFLOW + "/runs?event=workflow_dispatch&branch=main&per_page=100"
            )
            values = result.get("workflow_runs")
            if (
                type(values) is not list
                or len(values) > 100
                or type(result.get("total_count")) is not int
                or result["total_count"] != len(values)
            ):
                raise Rejected()  # A truncated listing is never absence evidence.
            matches = [
                item
                for item in values
                if item.get("display_title") == "ios-tf-" + self.nonce
            ]
            if len(matches) != 1:
                raise Rejected()
            candidate = matches[0].get("id")
            if type(candidate) is not int or candidate <= 0:
                raise Rejected()
            self.run_id = candidate
            self.bound()
            if not self.journal_failed:
                self.record(
                    "DISPATCH_CONFIRMED",
                    run_id=self.run_id,
                    workflow_id=self.workflow_id,
                    environment_id=self.environment_id,
                )

        return self._step(operation)

    def logs(self):
        """Only the bound completed job's logs, never latest/run-name-only logs."""
        self.context("artifact_verification", "artifact")
        run = self.bound()
        job = self.job()
        if run.get("status") != "completed" or job.get("status") != "completed":
            raise Rejected()
        command = [
            "gh",
            "api",
            "--hostname",
            "github.com",
            "--method",
            "GET",
            API + f"/actions/jobs/{self.job_id}/logs",
        ]
        self.check = "artifact"
        try:
            code, raw = primitives.bounded_process(command)
        except (Exception, KeyboardInterrupt) as error:
            self.reject(
                "INTERRUPTED"
                if isinstance(error, KeyboardInterrupt)
                else (
                    "TRANSPORT_TIMEOUT"
                    if isinstance(error, TimeoutError)
                    else (
                        "TRANSPORT_REJECTED"
                        if isinstance(error, (OSError, primitives.Rejected))
                        else "UNEXPECTED_INTERNAL_ERROR"
                    )
                )
            )
        if code != 0:
            self.check = "artifact"
            self.reject("TRANSPORT_REJECTED")
        self.bound()
        self.job()
        return raw

    def artifact(self, *, version, build):
        from tools import ios_testflight_recovery as recovery

        self.context("artifact_verification", "artifact")
        try:
            return self._artifact(version=version, build=build)
        except (Exception, KeyboardInterrupt) as error:
            self.check = "artifact" if self.check != "journal_write" else self.check
            if isinstance(error, recovery.Rejected):
                self.reject()
            self.capture(error)
            raise Rejected(self.failure) from None

    def _artifact(self, *, version, build):
        from tools import ios_testflight_recovery as recovery

        self.context("artifact_verification", "artifact")
        if self.journal is None or self.journal_failed:
            raise Rejected()
        events = journal_module.active_events(self.journal.events)
        prior = [e["data"] for e in events if e["event"] == "CANDIDATE"]
        if prior:
            if len(prior) != 1:
                raise Rejected()
            start = events[0]["data"]
            self.bound()
            self.job()
            return recovery.fingerprint(
                {
                    "schema": 1,
                    "sha": self.sha,
                    "nonce": self.nonce,
                    "run_id": str(self.run_id),
                    "version": start["version"],
                    "build": start["build"],
                    **prior[0],
                },
                binding=wire.Binding(self.sha, self.nonce, str(self.run_id)),
                version=version,
                build=build,
            )
        raw = self.logs()
        value = recovery.from_logs(
            raw,
            binding=wire.Binding(self.sha, self.nonce, str(self.run_id)),
            version=version,
            build=build,
        )
        record = {k: value[k] for k in ("sha256", "size")}
        self.record("CANDIDATE", **record)
        return value

    def cancel(self):
        def operation():
            self.context("cancel", "cancel_result")
            if self.cancel_attempted or self.run_id is None:
                raise Rejected()
            if self.bound().get("status") == "completed":
                return
            self.check = "cancel_result"
            self.cancel_attempted = True
            self.cancel_unresolved = True
            self.state = "UNCERTAIN"
            self.record("CANCEL_ATTEMPT")
            status, _ = self.call("POST", API + f"/actions/runs/{self.run_id}/cancel")
            if status != 202:
                self.http_uncertain = True
                self.external_unknown = True
                self.reject(self.http_failure(status))
            self.record("CANCEL_CONFIRMED")

        return self._step(operation)

    def cleanup(self):
        def operation():
            self.context("cleanup", "retention")
            for name in self.attempted:
                if name not in self.deleted:
                    self.deleted.add(name)
                    try:
                        self.check = "secret_delete"
                        self.record("SECRET_DELETE_ATTEMPT", name=name)
                        status, _ = self.call("DELETE", SECRET + name)
                        if status != 204:
                            self.http_uncertain = True
                            self.external_unknown = True
                            self.http_failure(status)
                        else:
                            self.record("SECRET_DELETE_CONFIRMED", name=name)
                    except Exception as error:
                        self.http_uncertain = True
                        self.capture(error)
                try:
                    self.check = "secret_absence"
                    status, _ = self.call("GET", SECRET + name)
                    if status == 404 and name not in self.listing():
                        if name not in self.absent and not self.journal_failed:
                            self.record("SECRET_ABSENT", name=name)
                        self.absent.add(name)
                    else:
                        self.absent.discard(name)
                        self.check = "secret_absence"
                        self.remember(
                            diagnostics.failure(
                                self.stage,
                                self.check,
                                (
                                    self.http_failure(status)
                                    if status not in (200, 404)
                                    else "CHECK_REJECTED"
                                ),
                            )
                        )
                except Exception as error:
                    self.absent.discard(name)
                    self.capture(error)
            self.state = (
                "CLEANED"
                if set(self.attempted) <= self.absent
                and not self.http_uncertain
                and not self.cancel_unresolved
                else "UNCERTAIN"
            )

        return self._step(operation)

    def capture(self, error):
        detail = (
            diagnostics.sanitize(getattr(error, "failure", None))
            if isinstance(error, Rejected)
            else None
        )
        if detail is None:
            reason = (
                "CHECK_REJECTED"
                if isinstance(error, (Rejected, primitives.Rejected, wire.Rejected))
                else (
                    "INTERRUPTED"
                    if isinstance(error, KeyboardInterrupt)
                    else "UNEXPECTED_INTERNAL_ERROR"
                )
            )
            detail = diagnostics.failure(self.stage, self.check, reason)
        self.remember(detail)

    def _step(self, operation):
        if not self.lock.acquire(blocking=False):
            return self.public()
        try:
            operation()
        except (Exception, KeyboardInterrupt) as error:
            self.capture(error)
            if self.state == "UNCERTAIN":
                self.http_uncertain = True
                self.external_unknown = True
            else:
                self.state = "STOP"
        finally:
            self.lock.release()
        return self.public()
