import unittest
from unittest import mock

from tools import ios_testflight_dispatch as dispatch


class DispatchTests(unittest.TestCase):
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
