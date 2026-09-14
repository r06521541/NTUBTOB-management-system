import unittest
from unittest import mock

from tools import ios_testflight_dispatch as dispatch


class DispatchTests(unittest.TestCase):
    def test_raw_run_states_keep_binding_and_wait_without_mutation(self):
        for status in ("requested", "pending", "queued", "waiting"):
            with self.subTest(status=status):
                api = mock.Mock()
                session = dispatch.Session(b"{}", b"{}", sha="a" * 40, api=api)
                session.run_id, session.workflow_id = 123, 7
                session.state = "WAITING"
                before = session.deadline
                run = {
                    "id": 123,
                    "workflow_id": 7,
                    "path": ".github/workflows/" + dispatch.wire.WORKFLOW,
                    "event": "workflow_dispatch",
                    "head_branch": "main",
                    "head_sha": session.sha,
                    "run_attempt": 1,
                    "display_title": "ios-tf-" + session.nonce,
                    "repository": {"full_name": dispatch.wire.REPO},
                    "status": status,
                }
                api.call.side_effect = [(200, run), (200, [])]
                result = session.advance()
                self.assertEqual(result["status"], "WAITING")
                self.assertIsNone(result["failure"])
                self.assertEqual(session.deadline, before)
                self.assertEqual(
                    api.call.call_count, 1 if status in {"requested", "pending"} else 2
                )
                self.assertTrue(
                    all(c.args[0] == "GET" for c in api.call.call_args_list)
                )
                self.assertEqual(result["secret_transfer_state"], "NOT_ATTEMPTED")

    def test_raw_run_rejection_reports_the_check_that_actually_failed(self):
        for status, wrong_binding in (
            (None, False),
            ([], False),
            ("private-sentinel", False),
            ("completed", False),
            ("pending", True),
        ):
            with self.subTest(status=status, wrong_binding=wrong_binding):
                api = mock.Mock()
                session = dispatch.Session(b"{}", b"{}", sha="a" * 40, api=api)
                session.run_id, session.workflow_id = 123, 7
                session.state = "WAITING"
                api.call.return_value = (
                    200,
                    {
                        "id": 123,
                        "workflow_id": 7,
                        "path": ".github/workflows/" + dispatch.wire.WORKFLOW,
                        "event": "workflow_dispatch",
                        "head_branch": "main",
                        "head_sha": "c" * 40 if wrong_binding else session.sha,
                        "run_attempt": 1,
                        "display_title": "ios-tf-" + session.nonce,
                        "repository": {"full_name": dispatch.wire.REPO},
                        "status": status,
                    },
                )
                result = session.advance()
                self.assertEqual(result["status"], "STOP")
                self.assertEqual(
                    result["failure"],
                    {
                        "stage": "awaiting_job",
                        "check": "run_binding" if wrong_binding else "job_status",
                        "reason": "CHECK_REJECTED",
                    },
                )
                self.assertNotIn("private-sentinel", repr(result))
                self.assertEqual(api.call.call_count, 1)
                self.assertEqual(api.call.call_args.args[0], "GET")

    def test_recovery_and_candidate_use_successor_not_physical_start(self):
        from tools.tests.test_ios_testflight_journal import JournalTests

        helper = JournalTests()
        value, native = helper.stopped()
        successor = helper.successor(value.unsent_snapshot()) | {
            "build": 2,
            "previous_build": 1,
        }
        value.record("UNSENT_SUCCESSOR", **successor)
        api = mock.Mock()
        session = dispatch.Session.recover(value, api=api)
        self.assertEqual(
            (session.sha, session.nonce, session.issued), ("c" * 40, "d" * 64, 200)
        )
        self.assertIsNone(session.failure)  # legacy RESULT not this attempt
        self.assertFalse(session.attempted)
        self.assertFalse(session.public()["current_absence_verified"])
        self.assertTrue(session.recovery_only)
        self.assertEqual(session.signing, b"")
        api.call.assert_not_called()
        detail = dispatch.diagnostics.failure(
            "dispatch_preflight", "repository", "CHECK_REJECTED"
        )
        value.record("FAILURE", **detail)
        value.record("DISPATCH_ATTEMPT")
        value.record(
            "DISPATCH_CONFIRMED", run_id=123, workflow_id=12, environment_id=34
        )
        value.record("CANDIDATE", sha256="e" * 64, size=1234)
        session = dispatch.Session.recover(value, api=api)
        self.assertEqual(session.failure, detail)
        with mock.patch.object(session, "bound"), mock.patch.object(session, "job"):
            candidate = session.artifact(version="1.0.0", build=2)
        self.assertEqual(candidate["build"], 2)
        self.assertEqual(candidate["nonce"], "d" * 64)
        self.assertEqual(value.events[0]["data"]["build"], 1)
        value.close()

    def test_zero_put_is_not_observed_absence(self):
        result = self.session().public()
        self.assertFalse(result["current_absence_verified"])
        self.assertTrue(result["retention_resolved"])
        self.assertEqual(result["secret_transfer_state"], "NOT_ATTEMPTED")

    def test_step_keeps_fixed_failure_without_private_exception(self):
        session = self.session()
        session.policy.side_effect = RuntimeError("private-sentinel")
        result = session.begin()
        self.assertEqual(
            result["failure"],
            {
                "stage": "dispatch_preflight",
                "check": "unexpected",
                "reason": "UNEXPECTED_INTERNAL_ERROR",
            },
        )
        self.assertNotIn("private-sentinel", repr(result))

    def test_http_and_transport_fixed_reasons_and_no_external_write(self):
        for status, reason in (
            (401, "HTTP_UNAUTHENTICATED"),
            (403, "HTTP_FORBIDDEN"),
            (404, "HTTP_NOT_FOUND"),
            (429, "HTTP_RATE_LIMITED"),
            (503, "HTTP_SERVER_ERROR"),
            (302, "HTTP_STATUS_REJECTED"),
        ):
            session = self.session()
            session.api.call.side_effect = lambda *args: (
                status,
                {"private": "sentinel"},
            )
            result = session.begin()
            self.assertEqual(result["failure"]["reason"], reason)
            self.assertEqual(result["external_write_state"], "NOT_ATTEMPTED")
            self.assertFalse(result["current_absence_verified"])
        for error, reason in (
            (TimeoutError("private-sentinel"), "TRANSPORT_TIMEOUT"),
            (OSError("private-sentinel"), "TRANSPORT_REJECTED"),
            (RuntimeError("private-sentinel"), "UNEXPECTED_INTERNAL_ERROR"),
        ):
            session = self.session()
            session.api.call.side_effect = error
            result = session.begin()
            self.assertEqual(result["failure"]["reason"], reason)
            self.assertNotIn("private-sentinel", repr(result))

    def test_budget_deadline_and_journal_failure_are_separate(self):
        for field, value, reason in (
            ("requests", 512, "REQUEST_BUDGET_EXHAUSTED"),
            ("deadline", 0, "DEADLINE_EXCEEDED"),
        ):
            session = self.session()
            setattr(session, field, value)
            self.assertEqual(session.begin()["failure"]["reason"], reason)
            self.assertFalse(session.api.call.called)
        session = self.session()
        session.journal = mock.Mock(intact=True)
        session.journal.record.side_effect = OSError("private-sentinel")
        result = session.begin()
        self.assertEqual(result["failure"]["reason"], "JOURNAL_REJECTED")
        self.assertEqual(result["external_write_state"], "UNKNOWN")
        self.assertTrue(
            all(c.args[0] == "GET" for c in session.api.call.call_args_list)
        )

    def test_cleanup_secondary_failure_preserves_primary(self):
        session = self.session()
        session.begin()
        session.bound.side_effect = dispatch.Rejected()
        first = session.advance()["failure"]
        session.attempted.append(dispatch.wire.SECRETS[0])
        session.api.call.side_effect = lambda *args: (503, {})
        result = session.cleanup()
        self.assertEqual(result["failure"], first)
        self.assertEqual(result["cleanup_failure"]["stage"], "cleanup")
        self.assertEqual(result["cleanup_failure"]["reason"], "HTTP_SERVER_ERROR")
        self.assertEqual(result["secret_transfer_state"], "UNRESOLVED")

    def test_interrupt_before_and_during_external_write(self):
        session = self.session()
        session.policy.side_effect = KeyboardInterrupt()
        result = session.begin()
        self.assertEqual(result["failure"]["reason"], "INTERRUPTED")
        self.assertEqual(result["external_write_state"], "NOT_ATTEMPTED")
        session = self.session()
        original = session.api.call.side_effect

        def call(method, path, body=None):
            if method == "POST":
                raise KeyboardInterrupt()
            return original(method, path, body)

        session.api.call.side_effect = call
        result = session.begin()
        self.assertEqual(result["failure"]["reason"], "INTERRUPTED")
        self.assertEqual(result["external_write_state"], "UNKNOWN")
        self.assertTrue(result["http_uncertain"])
        session.begin()
        self.assertEqual(
            sum(c.args[0] == "POST" for c in session.api.call.call_args_list), 1
        )

    def test_recovery_failure_legacy_and_attempt_state(self):
        start = {"event": "START", "data": dict(sha="a" * 40, nonce="b" * 64, issued=1)}
        journal = mock.Mock(intact=True)
        journal.events = [start, {"event": "RESULT", "data": {}}]
        recovered = dispatch.Session.recover(journal, api=self.api())
        self.assertEqual(recovered.public()["external_write_state"], "NOT_ATTEMPTED")
        self.assertFalse(recovered.public()["current_absence_verified"])
        self.assertEqual(
            recovered.public()["failure"]["reason"], "LEGACY_REASON_UNAVAILABLE"
        )
        expected = dispatch.diagnostics.failure(
            "dispatch_request", "dispatch_result", "HTTP_FORBIDDEN"
        )
        journal.events = [
            start,
            {"event": "FAILURE", "data": expected},
            {"event": "DISPATCH_ATTEMPT", "data": {}},
        ]
        recovered = dispatch.Session.recover(journal, api=self.api())
        self.assertEqual(recovered.public()["failure"], expected)
        self.assertEqual(recovered.public()["external_write_state"], "UNKNOWN")
        self.assertFalse(recovered.api.call.called)

    def test_expired_session_gets_one_cleanup_only_budget(self):
        session = self.session()
        session.deadline = 0
        session.requests = 512
        session.signing = session.asc = b"fictional-private"
        with mock.patch.object(dispatch.time, "monotonic", return_value=100):
            session.restrict_to_cleanup()
        self.assertEqual(session.deadline, 400)
        self.assertEqual(session.requests, 0)
        self.assertTrue(session.recovery_only)
        self.assertEqual(session.signing, b"")
        with mock.patch.object(dispatch.time, "monotonic", return_value=200):
            session.restrict_to_cleanup()
        self.assertEqual(session.deadline, 400)
        for method, path in (
            ("POST", dispatch.WORKFLOW + "/dispatches"),
            ("PUT", dispatch.SECRET + dispatch.wire.SECRETS[0]),
            ("POST", dispatch.API + "/actions/runs/999/pending_deployments"),
            ("DELETE", dispatch.SECRET + "FOREIGN"),
        ):
            with self.subTest(path=path), self.assertRaises(dispatch.Rejected):
                session.call(method, path)
        session.begin()
        session.advance()
        self.assertFalse(session.api.call.called)

    def test_durable_attempt_precedes_mutation_and_failed_flush_blocks_call(self):
        session = self.session()
        sink = mock.Mock()
        session.journal = sink
        original = session.api.call.side_effect

        def call(method, path, body=None):
            if method == "POST":
                self.assertIn(mock.call("DISPATCH_ATTEMPT"), sink.record.call_args_list)
            return original(method, path, body)

        session.api.call.side_effect = call
        session.begin()
        sink.record.assert_any_call(
            "DISPATCH_CONFIRMED", run_id=123, workflow_id=7, environment_id=8
        )
        fresh = self.session()
        fresh.journal = mock.Mock()
        fresh.journal.record.side_effect = OSError("private-sentinel")
        result = fresh.begin()
        self.assertTrue(all(c.args[0] == "GET" for c in fresh.api.call.call_args_list))
        self.assertNotIn("private-sentinel", repr(result))

    def test_restart_never_dispatches_or_reuploads_and_rechecks_absence(self):
        journal = mock.Mock()
        journal.intact = True
        journal.events = [
            {
                "event": "START",
                "data": {
                    "sha": "a" * 40,
                    "nonce": "b" * 64,
                    "issued": 1,
                    "expires": 7201,
                    "version": "1.0.0",
                    "build": 1,
                    "previous_build": 0,
                },
            },
            {"event": "DISPATCH_ATTEMPT", "data": {}},
            {
                "event": "DISPATCH_CONFIRMED",
                "data": {
                    "run_id": 123,
                    "workflow_id": 7,
                    "environment_id": 8,
                },
            },
            {"event": "SECRET_PUT_ATTEMPT", "data": {"name": dispatch.wire.SECRETS[0]}},
            {
                "event": "SECRET_DELETE_ATTEMPT",
                "data": {"name": dispatch.wire.SECRETS[0]},
            },
            {"event": "SECRET_ABSENT", "data": {"name": dispatch.wire.SECRETS[0]}},
        ]
        api = self.api()
        session = dispatch.Session.recover(journal, api=api)
        self.assertFalse(session.absent)
        session.begin()
        session.advance()
        session.cleanup()
        self.assertTrue(all(c.args[0] == "GET" for c in api.call.call_args_list))
        self.assertTrue(session.public()["current_absence_verified"])
        self.assertFalse(session.public()["retention_resolved"])

    def test_torn_recovery_journal_prohibits_even_cleanup_mutation(self):
        journal = mock.Mock(intact=False)
        journal.events = [
            {
                "event": "START",
                "data": {
                    "sha": "a" * 40,
                    "nonce": "b" * 64,
                    "issued": 1,
                    "expires": 7201,
                    "version": "1.0.0",
                    "build": 1,
                    "previous_build": 0,
                },
            },
            {"event": "SECRET_PUT_ATTEMPT", "data": {"name": dispatch.wire.SECRETS[0]}},
        ]
        api = self.api()
        session = dispatch.Session.recover(journal, api=api)
        session.cleanup()
        self.assertTrue(all(c.args[0] == "GET" for c in api.call.call_args_list))

    def test_unknown_run_recovery_requires_unique_exact_nonce_and_get_only(self):
        session = self.session()
        session.recovery_only = session.dispatched = True
        session.nonce = "b" * 64
        values = [{"id": 123, "display_title": "ios-tf-" + session.nonce}]
        session.api.call.side_effect = lambda *args: (
            200,
            {"total_count": len(values), "workflow_runs": values},
        )
        session.recover_run()
        self.assertEqual(session.run_id, 123)
        self.assertTrue(
            all(c.args[0] == "GET" for c in session.api.call.call_args_list)
        )
        for changed in ([], values * 2, [{"id": 124, "display_title": "latest"}]):
            session.run_id = None
            session.api.call.side_effect = lambda *args: (
                200,
                {"total_count": len(changed), "workflow_runs": changed},
            )
            session.recover_run()
            self.assertIsNone(session.run_id)

    def test_artifact_uses_bound_job_and_saves_before_return(self):
        import json

        session = self.session()
        session.run_id, session.job_id = 123, 456
        session.bound.return_value = {"status": "completed"}
        session.job.return_value = {"status": "completed"}
        session.journal = mock.Mock(intact=True)
        session.journal.events = []
        fingerprint = dict(
            schema=1,
            sha=session.sha,
            nonce=session.nonce,
            run_id="123",
            version="1.2.3",
            build=123,
            sha256="a" * 64,
            size=4,
        )
        raw = ("IOS_TF_FINGERPRINT " + json.dumps(fingerprint)).encode()
        with mock.patch.object(
            dispatch.primitives, "bounded_process", return_value=(0, raw)
        ) as process:
            self.assertEqual(session.artifact(version="1.2.3", build=123), fingerprint)
        self.assertTrue(
            process.call_args.args[0][-1].endswith("/actions/jobs/456/logs")
        )
        session.journal.record.assert_called_once_with(
            "CANDIDATE", sha256="a" * 64, size=4
        )
        session.journal.record.side_effect = OSError()
        with mock.patch.object(
            dispatch.primitives, "bounded_process", return_value=(0, raw)
        ):
            with self.assertRaises(dispatch.Rejected):
                session.artifact(version="1.2.3", build=123)

    def test_policy_missing_or_wrong_protection_rejects(self):
        session = dispatch.Session(b"{}", b"{}", sha="a" * 40, api=mock.Mock())
        reviewer = {
            "type": "required_reviewers",
            "prevent_self_review": False,
            "reviewers": [{"type": "User", "reviewer": {"login": dispatch.OWNER}}],
        }
        env = {
            "id": 8,
            "name": dispatch.wire.ENVIRONMENT,
            "can_admins_bypass": False,
            "deployment_branch_policy": {
                "protected_branches": False,
                "custom_branch_policies": True,
            },
            "protection_rules": [reviewer],
        }
        values = {
            "user": {"login": dispatch.OWNER},
            dispatch.API: {"full_name": dispatch.wire.REPO},
            dispatch.API + "/git/ref/heads/main": {"object": {"sha": "a" * 40}},
            dispatch.WORKFLOW: {
                "id": 7,
                "path": ".github/workflows/" + dispatch.wire.WORKFLOW,
                "state": "active",
            },
            dispatch.ENV: env,
            dispatch.ENV
            + "/deployment-branch-policies?per_page=100": {
                "total_count": 1,
                "branch_policies": [{"name": "main", "type": "branch"}],
            },
        }
        session.api.call.side_effect = lambda method, path, body=None: (
            200,
            values[path],
        )
        session.policy()
        for value in (True, None):
            env["can_admins_bypass"] = value
            with self.assertRaises(dispatch.Rejected):
                session.policy()
        env["can_admins_bypass"] = False
        branches = values[dispatch.ENV + "/deployment-branch-policies?per_page=100"]
        for target, field, changed, check in (
            (values["user"], "login", "private-sentinel", "github_user"),
            (values[dispatch.API], "full_name", "private-sentinel", "repository"),
            (values[dispatch.API + "/git/ref/heads/main"], "object", {}, "main_head"),
            (values[dispatch.WORKFLOW], "state", "disabled", "workflow"),
            (env, "name", "private-sentinel", "environment"),
            (env, "deployment_branch_policy", {}, "branch_policy"),
            (reviewer, "prevent_self_review", True, "reviewers"),
            (
                env,
                "protection_rules",
                [reviewer, {"type": "unknown"}],
                "protection_rules",
            ),
            (branches, "total_count", 2, "branch_policy"),
            (values[dispatch.WORKFLOW], "id", 99, "policy_identity"),
        ):
            with self.subTest(check=check), mock.patch.dict(target, {field: changed}):
                with self.assertRaises(dispatch.Rejected) as error:
                    session.policy()
                self.assertEqual(error.exception.failure["check"], check)
                self.assertEqual(error.exception.args, ("DISPATCH_REJECTED",))
                self.assertNotIn("private-sentinel", repr(error.exception.failure))

    def test_approval_timeout_not_repeated(self):
        session = self.session()
        session.begin()
        with mock.patch.object(
            dispatch.primitives, "encrypt", return_value="fictional"
        ):
            for _ in range(6):
                session.advance()
        original = session.api.call.side_effect

        def timeout(method, path, body=None):
            if method == "POST":
                raise TimeoutError()
            return original(method, path, body)

        session.api.call.side_effect = timeout
        self.assertEqual(session.advance()["status"], "UNCERTAIN")
        session.advance()
        self.assertEqual(
            sum(c.args[0] == "POST" for c in session.api.call.call_args_list), 2
        )
        self.assertTrue(session.http_uncertain)

    def api(self):
        api = mock.Mock()
        api.names = set()

        def call(method, path, body=None):
            if method == "POST" and path.endswith("/dispatches"):
                return 200, {"workflow_run_id": 123}
            if method == "POST":
                return 200, []
            if method == "PUT":
                api.names.add(path.rsplit("/", 1)[1])
                return 201, None
            if method == "DELETE":
                api.names.discard(path.rsplit("/", 1)[1])
                return 204, None
            if path.endswith("public-key"):
                return 200, {"key_id": "fictional", "key": "fictional"}
            if "secrets?" in path:
                return 200, {
                    "total_count": len(api.names),
                    "secrets": [{"name": n} for n in api.names],
                }
            if "/secrets/" in path:
                name = path.rsplit("/", 1)[1]
                return (200, {"name": name}) if name in api.names else (404, None)
            raise AssertionError(path)

        api.call.side_effect = call
        return api

    def session(self):
        session = dispatch.Session(
            b'{"fictional":"sign"}',
            b'{"fictional":"asc"}',
            sha="a" * 40,
            api=self.api(),
        )
        session.policy = mock.Mock()
        session.workflow_id = 7
        session.environment_id = 8
        session.bound = mock.Mock(return_value={"status": "waiting"})
        session.pending = mock.Mock(return_value=True)
        session.job = mock.Mock(return_value={"status": "waiting"})
        return session

    def test_job_exact_binding_and_waiting_negatives(self):
        session = dispatch.Session(b"{}", b"{}", sha="a" * 40, api=mock.Mock())
        session.run_id = 123
        value = {
            "id": 456,
            "name": "owner_testflight",
            "run_id": 123,
            "head_sha": "a" * 40,
            "status": "waiting",
            "conclusion": None,
        }
        session.api.call.return_value = (200, {"total_count": 1, "jobs": [value]})
        session.job(waiting=True)
        self.assertEqual(session.job_id, 456)
        self.assertTrue(
            session.api.call.call_args.args[1].endswith("/attempts/1/jobs?per_page=100")
        )
        for key, changed in (
            ("id", 789),
            ("name", "other"),
            ("run_id", 124),
            ("head_sha", "b" * 40),
            ("status", "in_progress"),
            ("conclusion", "success"),
        ):
            session.api.call.return_value = (
                200,
                {"total_count": 1, "jobs": [value | {key: changed}]},
            )
            with self.subTest(key=key), self.assertRaises(dispatch.Rejected):
                session.job(waiting=True)
        session.api.call.return_value = (
            200,
            {"total_count": 2, "jobs": [value, value]},
        )
        with self.assertRaises(dispatch.Rejected):
            session.job()

    def test_observe_requires_same_job_completion(self):
        session = self.session()
        session.run_id = 123
        session.bound.return_value = {"status": "completed"}
        self.assertEqual(session.observe()["status"], "STOP")
        session.job.return_value = {"status": "completed"}
        self.assertEqual(session.observe()["status"], "COMPLETED")

    def test_bad_frames_before_network(self):
        with self.assertRaises(dispatch.Rejected):
            dispatch.Session(b"\x00", b"{}", sha="a" * 40, api=object())

    def test_six_put_then_approve_once_and_cleanup(self):
        session = self.session()
        self.assertEqual(session.begin()["status"], "WAITING")
        with mock.patch.object(
            dispatch.primitives, "encrypt", return_value="fictional-cipher"
        ):
            for _ in range(6):
                self.assertEqual(session.advance()["status"], "UPLOADING")
            self.assertEqual(session.advance()["status"], "APPROVED")
            session.advance()
        calls = session.api.call.call_args_list
        self.assertEqual(sum(c.args[0] == "PUT" for c in calls), 6)
        self.assertEqual(
            sum(
                c.args[0] == "POST" and c.args[1].endswith("pending_deployments")
                for c in calls
            ),
            1,
        )
        self.assertEqual(session.cleanup()["status"], "CLEANED")
        session.cleanup()
        self.assertEqual(
            sum(c.args[0] == "DELETE" for c in session.api.call.call_args_list), 6
        )
        self.assertNotIn("fictional", repr(session))

    def test_partial_put_never_approves_and_only_attempted_deleted(self):
        session = self.session()
        session.begin()
        original = session.api.call.side_effect

        def fail(method, path, body=None):
            if method == "PUT":
                raise TimeoutError("private-sentinel")
            return original(method, path, body)

        session.api.call.side_effect = fail
        with mock.patch.object(
            dispatch.primitives, "encrypt", return_value="fictional"
        ):
            result = session.advance()
            session.advance()
        self.assertTrue(result["http_uncertain"])
        self.assertNotIn("private-sentinel", repr(result))
        result = session.cleanup()
        self.assertTrue(result["current_absence_verified"])
        self.assertFalse(result["retention_resolved"])
        self.assertEqual(result["status"], "UNCERTAIN")
        deletes = [
            c.args[1] for c in session.api.call.call_args_list if c.args[0] == "DELETE"
        ]
        self.assertEqual(deletes, [dispatch.SECRET + dispatch.wire.SECRETS[0]])

    def test_delete_timeout_keeps_retention_unresolved_after_absence(self):
        session = self.session()
        session.begin()
        session.attempted.append(dispatch.wire.SECRETS[0])
        original = session.api.call.side_effect

        def fail(method, path, body=None):
            if method == "DELETE":
                raise TimeoutError("private-sentinel")
            return original(method, path, body)

        session.api.call.side_effect = fail
        result = session.cleanup()
        self.assertTrue(result["current_absence_verified"])
        self.assertFalse(result["retention_resolved"])
        self.assertTrue(result["http_uncertain"])
        self.assertEqual(result["status"], "UNCERTAIN")

    def test_existing_secret_no_dispatch_or_delete(self):
        session = self.session()
        session.api.names.add(dispatch.wire.SECRETS[2])
        self.assertEqual(session.begin()["status"], "STOP")
        session.cleanup()
        self.assertTrue(
            all(c.args[0] == "GET" for c in session.api.call.call_args_list)
        )

    def test_run_mismatch_and_missing_absence(self):
        session = self.session()
        session.begin()
        session.bound.side_effect = dispatch.Rejected()
        session.advance()
        self.assertFalse(session.attempted)
        session.attempted.append(dispatch.wire.SECRETS[0])
        session.api.call.side_effect = lambda *a: (500, {})
        result = session.cleanup()
        self.assertFalse(result["retention_resolved"])
        self.assertTrue(result["http_uncertain"])

    def test_unknown_dispatch_no_resend(self):
        session = self.session()
        original = session.api.call.side_effect
        session.api.call.side_effect = lambda method, path, body=None: (
            (204, None) if method == "POST" else original(method, path, body)
        )
        session.begin()
        session.begin()
        self.assertIsNone(session.run_id)
        self.assertEqual(
            sum(c.args[0] == "POST" for c in session.api.call.call_args_list), 1
        )


if __name__ == "__main__":
    unittest.main()
