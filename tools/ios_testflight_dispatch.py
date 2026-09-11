"""One private GitHub session, no CLI or durable restart authority.

Six PUTs are not a transaction. Owner-exclusive configuration is required; no
remote compare-and-swap exists. Caller must retain state and never restart an
uncertain operation. Deadline expiration can leave remote secrets unresolved.
"""

import secrets
import threading
import time

from tools import ios_profile_intake as primitives
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
    def __init__(self):
        super().__init__("DISPATCH_REJECTED")


class Session:
    def __init__(self, signing_frame, asc_frame, *, sha, api=None):
        self.nonce = secrets.token_hex(32)
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
            raise Rejected() from None
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

    def __repr__(self):
        return "<TestFlightDispatchSession>"

    def public(self):
        return {
            "status": self.state if self.state in STATES else "UNCERTAIN",
            "run_id": self.run_id,
            "current_absence_verified": set(self.attempted) <= self.absent,
            "retention_resolved": set(self.attempted) <= self.absent
            and not self.http_uncertain,
            "http_uncertain": self.http_uncertain,
            "cancel_unresolved": self.cancel_unresolved,
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
        if self.requests >= 200 or time.monotonic() >= self.deadline:
            raise Rejected()
        self.requests += 1
        return self.api.call(method, path, body)

    def get(self, path):
        status, value = self.call("GET", path)
        if status != 200:
            raise Rejected()
        return value

    def policy(self):
        if (
            self.get("user").get("login") != OWNER
            or self.get(API).get("full_name") != wire.REPO
        ):
            raise Rejected()
        if (
            self.get(API + "/git/ref/heads/main").get("object", {}).get("sha")
            != self.sha
        ):
            raise Rejected()
        workflow = self.get(WORKFLOW)
        if (
            workflow.get("path") != ".github/workflows/" + wire.WORKFLOW
            or workflow.get("state") != "active"
            or type(workflow.get("id")) is not int
        ):
            raise Rejected()
        environment = self.get(ENV)
        rules = environment.get("protection_rules", [])
        reviewers = [r for r in rules if r.get("type") == "required_reviewers"]
        if (
            environment.get("name") != wire.ENVIRONMENT
            or type(environment.get("id")) is not int
            or environment.get("can_admins_bypass") is not False
            or environment.get("deployment_branch_policy")
            != {"protected_branches": False, "custom_branch_policies": True}
            or len(reviewers) != 1
            or reviewers[0].get("prevent_self_review") is not False
            or [
                (v.get("type"), v.get("reviewer", {}).get("login"))
                for v in reviewers[0].get("reviewers", [])
            ]
            != [("User", OWNER)]
            or any(
                r.get("type") not in {"required_reviewers", "branch_policy"}
                for r in rules
            )
        ):
            raise Rejected()
        branches = self.get(ENV + "/deployment-branch-policies?per_page=100")
        if branches.get("total_count") != 1 or [
            (b.get("name"), b.get("type")) for b in branches.get("branch_policies", [])
        ] != [("main", "branch")]:
            raise Rejected()
        if self.workflow_id is not None and (self.workflow_id, self.environment_id) != (
            workflow["id"],
            environment["id"],
        ):
            raise Rejected()
        self.workflow_id, self.environment_id = workflow["id"], environment["id"]

    def listing(self):
        data = self.get(SECRET.rstrip("/") + "?per_page=100")
        values = data.get("secrets")
        if (
            type(values) is not list
            or type(data.get("total_count")) is not int
            or data["total_count"] != len(values)
            or len(values) > 100
        ):
            raise Rejected()
        names = [v["name"] for v in values]
        if any(type(n) is not str for n in names) or len(set(names)) != len(names):
            raise Rejected()
        return set(names)

    def bound(self):
        if type(self.run_id) is not int or self.run_id <= 0 or self.workflow_id is None:
            raise Rejected()
        value = self.get(API + f"/actions/runs/{self.run_id}")
        expected = {
            "id": self.run_id,
            "workflow_id": self.workflow_id,
            "path": ".github/workflows/" + wire.WORKFLOW,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": self.sha,
            "run_attempt": 1,
        }
        if (
            any(value.get(k) != v for k, v in expected.items())
            or value.get("repository", {}).get("full_name") != wire.REPO
            or type(value.get("run_attempt")) is not int
        ):
            raise Rejected()
        return value

    def pending(self):
        values = self.get(API + f"/actions/runs/{self.run_id}/pending_deployments")
        if values == []:
            return False
        if type(values) is not list or len(values) != 1:
            raise Rejected()
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
            raise Rejected()
        return True

    def job(self, *, waiting=False):
        if type(self.run_id) is not int or self.run_id <= 0:
            raise Rejected()
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
            raise Rejected()
        matches = [item for item in jobs if item.get("name") == JOB]
        if len(matches) != 1:
            raise Rejected()
        value = matches[0]
        if (
            type(value.get("id")) is not int
            or value["id"] <= 0
            or value.get("run_id") != self.run_id
            or value.get("head_sha") != self.sha
            or (self.job_id is not None and value["id"] != self.job_id)
        ):
            raise Rejected()
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
            raise Rejected()
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
        if self.dispatched or self.state != "NEW":
            raise Rejected()
        self.policy()
        if set(wire.SECRETS) & self.listing():
            raise Rejected()
        for name in wire.SECRETS:
            if self.call("GET", SECRET + name)[0] != 404:
                raise Rejected()
        self.dispatched = True
        self.state = "UNCERTAIN"
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
            raise Rejected()
        self.run_id = value["workflow_run_id"]
        self.state = "WAITING"

    def advance(self):
        return self._step(self._advance)

    def _advance(self):
        if self.state not in {"WAITING", "UPLOADING"} or self.approval_attempted:
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
        names = self.listing() & set(wire.SECRETS)
        if names != set(self.uploaded):
            raise Rejected()
        if len(self.uploaded) < len(wire.SECRETS):
            name = wire.SECRETS[len(self.uploaded)]
            if self.call("GET", SECRET + name)[0] != 404:
                raise Rejected()
            key = self.get(SECRET + "public-key")
            if type(key.get("key_id")) is not str or not key["key_id"]:
                raise Rejected()
            values = wire.pack(
                self.signing,
                self.asc,
                wire.Binding(self.sha, self.nonce, str(self.run_id)),
                now=self.issued,
            )
            encrypted = primitives.encrypt(values[name].encode("ascii"), key["key"])
            self.attempted.append(name)
            self.state = "UNCERTAIN"
            status, _ = self.call(
                "PUT",
                SECRET + name,
                {"key_id": key["key_id"], "encrypted_value": encrypted},
            )
            if status != 201:
                self.http_uncertain = True
                raise Rejected()
            self.uploaded.append(name)
            self.state = "UPLOADING"
        else:
            for name in wire.SECRETS:
                if self.get(SECRET + name).get("name") != name:
                    raise Rejected()
            self.bound()
            if not self.pending():
                raise Rejected()
            self.job(waiting=True)
            self.approval_attempted = True
            self.state = "UNCERTAIN"
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
                raise Rejected()
            self.state = "APPROVED"

    def observe(self):
        def operation():
            run = self.bound()
            job = self.job()
            if run.get("status") == "completed":
                if job.get("status") != "completed":
                    raise Rejected()
                self.cancel_unresolved = False
                self.state = "COMPLETED" if not self.http_uncertain else "UNCERTAIN"

        return self._step(operation)

    def cancel(self):
        def operation():
            if self.cancel_attempted or self.run_id is None:
                raise Rejected()
            if self.bound().get("status") == "completed":
                return
            self.cancel_attempted = True
            self.cancel_unresolved = True
            self.state = "UNCERTAIN"
            status, _ = self.call("POST", API + f"/actions/runs/{self.run_id}/cancel")
            if status != 202:
                self.http_uncertain = True
                raise Rejected()

        return self._step(operation)

    def cleanup(self):
        def operation():
            for name in self.attempted:
                if name not in self.deleted:
                    self.deleted.add(name)
                    try:
                        status, _ = self.call("DELETE", SECRET + name)
                        if status != 204:
                            self.http_uncertain = True
                    except Exception:
                        self.http_uncertain = True
                try:
                    status, _ = self.call("GET", SECRET + name)
                    if status == 404 and name not in self.listing():
                        self.absent.add(name)
                    else:
                        self.absent.discard(name)
                except Exception:
                    self.absent.discard(name)
            self.state = (
                "CLEANED"
                if set(self.attempted) <= self.absent
                and not self.http_uncertain
                and not self.cancel_unresolved
                else "UNCERTAIN"
            )

        return self._step(operation)

    def _step(self, operation):
        if not self.lock.acquire(blocking=False):
            return self.public()
        try:
            operation()
        except Exception:
            if self.state == "UNCERTAIN":
                self.http_uncertain = True
            else:
                self.state = "STOP"
        finally:
            self.lock.release()
        return self.public()
