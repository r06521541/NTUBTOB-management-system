"""Entire GH lifecycle is fictional and mocked; never invoke gh or real files."""

import contextlib
import ctypes
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from nacl.public import PrivateKey, SealedBox

from tools import ios_profile_intake as intake

SHA = "a" * 40
NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


class GitHubFixture:
    def __init__(self):
        self.calls, self.present, self.uploaded = [], False, False
        self.dispatch_error = self.put_error = self.delete_error = None
        self.delete_status = 204
        self.run_changes, self.env_changes = {}, {}
        self.run_status = None
        self.job_success = True
        self.key = PrivateKey.generate()
        self.received = None
        self.cancelled = False

    def call(self, method, path, body=None):
        import base64

        self.calls.append((method, path, body))
        if method == "POST" and path.endswith("/cancel"):
            self.cancelled = True
            return 202, None
        if method == "POST":
            if self.dispatch_error:
                raise self.dispatch_error
            return 200, {"workflow_run_id": 42}
        if method == "PUT":
            self.present = self.uploaded = True
            self.received = json.loads(
                SealedBox(self.key).decrypt(base64.b64decode(body["encrypted_value"]))
            )
            if self.put_error:
                raise self.put_error
            return 201, None
        if method == "DELETE":
            self.present = False
            if self.delete_error:
                raise self.delete_error
            return self.delete_status, None
        if path == "user":
            return 200, {"login": intake.OWNER}
        if path == intake.API:
            return 200, {"full_name": intake.REPO, "id": 1}
        if path.endswith("/git/ref/heads/main"):
            return 200, {"object": {"sha": SHA}}
        if path.endswith("/actions/workflows/" + intake.WORKFLOW):
            return 200, {
                "path": ".github/workflows/" + intake.WORKFLOW,
                "state": "active",
                "id": 2,
            }
        if path.endswith("/environments/" + intake.ENVIRONMENT):
            return 200, {
                "name": intake.ENVIRONMENT,
                "id": 3,
                "can_admins_bypass": False,
                "deployment_branch_policy": {
                    "protected_branches": False,
                    "custom_branch_policies": True,
                },
                "protection_rules": [
                    {
                        "type": "required_reviewers",
                        "prevent_self_review": False,
                        "reviewers": [
                            {"type": "User", "reviewer": {"login": intake.OWNER}}
                        ],
                    }
                ],
                **self.env_changes,
            }
        if "deployment-branch-policies" in path:
            return 200, {
                "total_count": 1,
                "branch_policies": [{"name": "main", "type": "branch"}],
            }
        if path.endswith("/public-key"):
            return 200, {
                "key_id": "123",
                "key": base64.b64encode(bytes(self.key.public_key)).decode(),
            }
        if path.endswith("/secrets?per_page=100"):
            values = [{"name": intake.SECRET}] if self.present else []
            return 200, {"total_count": len(values), "secrets": values}
        if path.endswith("/secrets/" + intake.SECRET):
            return (200, {"name": intake.SECRET}) if self.present else (404, None)
        if path.endswith("/pending_deployments"):
            return 200, [
                {
                    "environment": {"id": 3, "name": intake.ENVIRONMENT},
                    "current_user_can_approve": True,
                    "reviewers": [
                        {"type": "User", "reviewer": {"login": intake.OWNER}}
                    ],
                }
            ]
        if path.endswith("/attempts/1/jobs?per_page=100"):
            return 200, {
                "total_count": 1,
                "jobs": [
                    {
                        "name": intake.JOB,
                        "run_id": 42,
                        "status": "completed",
                        "conclusion": "success" if self.job_success else "failure",
                    }
                ],
            }
        if path.endswith("/actions/runs/42"):
            return 200, {
                "id": 42,
                "repository": {"full_name": intake.REPO},
                "workflow_id": 2,
                "path": ".github/workflows/" + intake.WORKFLOW,
                "event": "workflow_dispatch",
                "head_branch": "main",
                "head_sha": SHA,
                "run_attempt": 1,
                "status": (
                    "completed"
                    if self.cancelled
                    else self.run_status
                    or ("completed" if self.uploaded else "waiting")
                ),
                "conclusion": "success",
                **self.run_changes,
            }
        raise AssertionError("unexpected fictional endpoint")


class IntakeTests(unittest.TestCase):
    def test_diagnose_independent_matrix_and_no_external_actions(self):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.read.side_effect = [self.material["cms"], self.material["der"]]
        with (
            patch.object(intake, "repository"),
            patch.object(intake, "Inputs", return_value=session),
            patch.object(
                intake.preparation, "local_app_data", return_value=Path("fictional")
            ),
            patch.object(
                intake.preparation,
                "hidden",
                side_effect=["DIAGNOSE PROFILE " + SHA, "private-invalid-team"],
            ),
            patch.object(
                intake, "GitHub", side_effect=AssertionError("network")
            ) as github,
            patch.object(intake, "lifecycle", side_effect=AssertionError("mutation")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            result = intake.diagnose_input(SHA)
        self.assertEqual(result["checks"]["team"], "TEAM_FORMAT_REJECTED")
        self.assertEqual(result["checks"]["cms"], "CMS_STRUCTURE_PASS")
        self.assertEqual(
            {
                key
                for key, value in result["cms_predicates"].items()
                if value == "NOT_CHECKED"
            },
            {"smime_capabilities_value", "algorithm_protection_value"},
        )
        self.assertNotIn("REJECTED", result["cms_predicates"].values())
        self.assertEqual(result["checks"]["envelope_size"], "ENVELOPE_SIZE_PASS")
        self.assertNotIn("private-invalid-team", output.getvalue() + repr(result))
        session.lock.assert_not_called()
        github.assert_not_called()

    def test_diagnose_rejection_before_reads_leaves_not_checked(self):
        for failure in ["confirmation", "read"]:
            session = Mock()
            session.__enter__ = Mock(return_value=session)
            session.__exit__ = Mock(return_value=False)
            session.read.side_effect = intake.custody.CustodyError("READ_REJECTED")
            answers = (
                ["cancel"]
                if failure == "confirmation"
                else ["DIAGNOSE PROFILE " + SHA, "FICTTEAM01"]
            )
            with (
                patch.object(intake, "repository"),
                patch.object(intake, "Inputs", return_value=session),
                patch.object(
                    intake.preparation, "local_app_data", return_value=Path("fictional")
                ),
                patch.object(intake.preparation, "hidden", side_effect=answers),
                patch.object(intake, "GitHub", side_effect=AssertionError("network")),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = intake.diagnose_input(SHA)
            self.assertEqual(set(result["checks"].values()), {"NOT_CHECKED"})
            self.assertEqual(set(result["cms_predicates"].values()), {"NOT_CHECKED"})
            session.lock.assert_not_called()
            if failure == "confirmation":
                session.read.assert_not_called()

    def test_diagnose_malformed_independent_checks_and_no_io(self):
        from tools import ios_profile_cms_verification as cms

        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.read.side_effect = [b"private-profile", b"private-certificate"]
        with (
            patch.object(intake, "repository"),
            patch.object(intake, "Inputs", return_value=session),
            patch.object(
                intake.preparation, "local_app_data", return_value=Path("fictional")
            ),
            patch.object(
                intake.preparation,
                "hidden",
                side_effect=["DIAGNOSE PROFILE " + SHA, "FICTTEAM01"],
            ),
            patch.object(
                intake, "remote_preflight", side_effect=AssertionError("network")
            ),
            patch.object(intake, "lifecycle", side_effect=AssertionError("mutation")),
            patch.object(cms, "_compile_native", side_effect=AssertionError("native")),
            patch("builtins.open", side_effect=AssertionError("file")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            result = intake.diagnose_input(SHA)
        self.assertEqual(
            result["checks"],
            {
                "team": "TEAM_FORMAT_PASS",
                "cms": "CMS_DECODE_REJECTED",
                "certificate_der": "CERTIFICATE_DER_REJECTED",
                "certificate_basic_constraints": "NOT_CHECKED",
                "envelope_size": "ENVELOPE_SIZE_PASS",
            },
        )
        self.assertNotIn("private-profile", repr(result) + output.getvalue())
        self.assertNotIn("private-certificate", repr(result) + output.getvalue())
        self.assertTrue(
            all(
                value is False
                for key, value in result.items()
                if key.endswith(("_verified", "_authorized"))
            )
        )

    def test_diagnose_helper_output_is_allowlisted_and_called_once(self):
        from tools import ios_profile_cms_verification as cms

        valid = cms.diagnose_predicates(self.material["cms"])
        for invalid in (
            {**valid, "stage": "private-sentinel"},
            {**valid, "predicates": {"private-sentinel": "PASS"}},
            {
                **valid,
                "predicates": dict.fromkeys(cms.PREDICATE_KEYS, "private-sentinel"),
            },
            {**valid, "extra": "private-sentinel"},
            None,
        ):
            session = Mock()
            session.__enter__ = Mock(return_value=session)
            session.__exit__ = Mock(return_value=False)
            session.read.side_effect = [self.material["cms"], self.material["der"]]
            with (
                patch.object(intake, "repository"),
                patch.object(intake, "Inputs", return_value=session),
                patch.object(
                    intake.preparation, "local_app_data", return_value=Path("fictional")
                ),
                patch.object(
                    intake.preparation,
                    "hidden",
                    side_effect=["DIAGNOSE PROFILE " + SHA, "FICTTEAM01"],
                ),
                patch.object(
                    cms, "diagnose_predicates", return_value=invalid
                ) as diagnose,
                patch.object(intake, "GitHub", side_effect=AssertionError("network")),
                patch.object(
                    intake, "lifecycle", side_effect=AssertionError("mutation")
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                result = intake.diagnose_input(SHA)
            diagnose.assert_called_once_with(self.material["cms"])
            session.lock.assert_not_called()
            self.assertEqual(result["checks"]["cms"], "CMS_UNKNOWN_REJECTED")
            self.assertEqual(set(result["cms_predicates"].values()), {"NOT_CHECKED"})
            self.assertNotIn("private-sentinel", repr(result) + output.getvalue())

    def test_diagnose_cli_mutually_exclusive_and_explicit_routing(self):
        with (
            patch.object(
                intake,
                "diagnose_input",
                return_value={"classification": "DIAGNOSTIC_COMPLETED"},
            ) as diagnose,
            patch.object(intake, "operate") as operate,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                intake.main(["--expected-commit", SHA, "--diagnose-input"]), 0
            )
            diagnose.assert_called_once_with(SHA)
            operate.assert_not_called()
        with (
            patch.object(intake, "diagnose_input") as diagnose,
            patch.object(intake, "operate") as operate,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                intake.main(
                    ["--expected-commit", SHA, "--diagnose-input", "--execute"]
                ),
                1,
            )
            diagnose.assert_not_called()
            operate.assert_not_called()

    @classmethod
    def setUpClass(cls):
        from tools import ios_profile_cms_rehearsal

        cls.material = ios_profile_cms_rehearsal.fixture()

    def execute(self, api):
        session = Mock()
        session.read.side_effect = [self.material["cms"], self.material["der"]]
        ticks = [0]

        def sleep(seconds):
            ticks[0] += seconds

        with (
            patch.object(intake.preparation, "hidden", return_value="FICTTEAM01"),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            result = intake.lifecycle(
                api,
                session,
                SHA,
                (
                    2,
                    3,
                    intake.API
                    + "/environments/"
                    + intake.ENVIRONMENT
                    + "/secrets/"
                    + intake.SECRET,
                ),
                sleep=sleep,
                clock=lambda: ticks[0],
                now=lambda: NOW,
            )
        self.assertNotIn("FICTTEAM01", output.getvalue())
        self.assertNotIn("fictional-profile", output.getvalue())
        return result

    def test_complete_single_dispatch_upload_delete_and_bound_envelope(self):
        api = GitHubFixture()
        intake.remote_preflight(api, SHA)
        result = self.execute(api)
        self.assertEqual(result["classification"], "confirmed_success")
        mutations = [method for method, _, _ in api.calls if method != "GET"]
        self.assertEqual(mutations, ["POST", "PUT", "DELETE"])
        self.assertEqual(api.received["run_id"], "42")
        self.assertEqual(api.received["sha"], SHA)
        self.assertEqual(api.received["expires_at"] - api.received["issued_at"], 3600)
        dispatch = next(body for method, _, body in api.calls if method == "POST")
        self.assertEqual(dispatch["inputs"]["nonce"], api.received["nonce"])
        self.assertFalse(api.present)
        self.assertIs(result["signing_authorized"], False)

    def test_content_digest_rejection_precedes_all_api_calls(self):
        from tools import ios_profile_cms_rehearsal as rehearsal

        api = GitHubFixture()
        material = {
            **self.material,
            "cms": rehearsal.tampered(self.material["cms"], "content"),
        }
        with patch.object(self, "material", material):
            result = self.execute(api)
        self.assertEqual(result["reason"], "INPUT_REJECTED")
        self.assertEqual(api.calls, [])
        self.assertIsNone(result["run_id"])

    def test_dispatch_unknown_never_put_or_delete(self):
        for error in [TimeoutError("private-error"), KeyboardInterrupt()]:
            api = GitHubFixture()
            api.dispatch_error = error
            self.assertEqual(self.execute(api)["reason"], "DISPATCH_UNCERTAIN")
            self.assertEqual(
                [method for method, _, _ in api.calls if method != "GET"], ["POST"]
            )
        for response in [(204, None), (200, {}), (200, {"workflow_run_id": True})]:
            api = GitHubFixture()
            original = api.call

            def call(method, path, body=None):
                return response if method == "POST" else original(method, path, body)

            api.call = call
            self.assertEqual(self.execute(api)["reason"], "DISPATCH_UNCERTAIN")
            self.assertFalse(api.uploaded)

    def test_wrong_binding_or_early_approval_never_upload(self):
        for changes in [
            {"head_sha": "b" * 40},
            {"run_attempt": 2},
            {"workflow_id": 99},
            {"head_branch": "other"},
            {"event": "push"},
            {"repository": {"full_name": "other/repo"}},
            {"status": "in_progress"},
            {"status": "completed"},
        ]:
            api = GitHubFixture()
            api.run_changes = changes
            self.assertIn(
                self.execute(api)["reason"], {"RUN_BINDING_REJECTED", "RUN_NOT_WAITING"}
            )
            self.assertFalse(api.uploaded)

    def test_put_unknown_and_delete_unknown_stay_retention_unresolved(self):
        for place in ["put_error", "delete_error"]:
            for error in [TimeoutError("private-error"), KeyboardInterrupt()]:
                api = GitHubFixture()
                setattr(api, place, error)
                result = self.execute(api)
                self.assertEqual(result["classification"], "retention_unresolved")
                self.assertEqual(sum(method == "PUT" for method, _, _ in api.calls), 1)
                self.assertEqual(
                    sum(method == "DELETE" for method, _, _ in api.calls), 1
                )
                deletion = next(
                    index
                    for index, (method, _, _) in enumerate(api.calls)
                    if method == "DELETE"
                )
                self.assertTrue(
                    any(
                        method == "GET" and path.endswith("/secrets/" + intake.SECRET)
                        for method, path, _ in api.calls[deletion + 1 :]
                    )
                )
        api = GitHubFixture()
        api.delete_status = 404
        self.assertEqual(self.execute(api)["reason"], "RETENTION_UNRESOLVED")

    def test_job_failure_and_timeout_still_remove_once(self):
        api = GitHubFixture()
        api.job_success = False
        self.assertEqual(self.execute(api)["reason"], "RUN_FAILED")
        self.assertFalse(api.present)
        api = GitHubFixture()
        api.run_status = "waiting"
        self.assertEqual(self.execute(api)["reason"], "OBSERVATION_TIMEOUT")
        self.assertEqual(sum(method == "DELETE" for method, _, _ in api.calls), 1)

    def test_cancel_uncertainty_does_not_prevent_secret_cleanup(self):
        api = GitHubFixture()
        api.run_status = "waiting"
        original = api.call

        def call(method, path, body=None):
            if path.endswith("/cancel"):
                api.calls.append((method, path, body))
                raise TimeoutError("private-error")
            return original(method, path, body)

        api.call = call
        result = self.execute(api)
        self.assertIs(result["cancel_unresolved"], True)
        self.assertIs(result["secret_absence_confirmed"], True)
        self.assertFalse(api.present)
        self.assertEqual(sum(path.endswith("/cancel") for _, path, _ in api.calls), 1)
        self.assertEqual(sum(method == "DELETE" for method, _, _ in api.calls), 1)

    def test_changed_main_or_new_secret_before_put_never_overwrites_or_deletes(self):
        for change in ["main", "secret", "reviewer"]:
            api = GitHubFixture()
            original = api.call

            def call(method, path, body=None):
                if path.endswith("/public-key"):
                    if change == "secret":
                        api.present = True
                    elif change == "reviewer":
                        api.env_changes = {"protection_rules": []}
                if (
                    change == "main"
                    and any(p.endswith("/public-key") for _, p, _ in api.calls)
                    and path.endswith("/git/ref/heads/main")
                ):
                    return 200, {"object": {"sha": "c" * 40}}
                return original(method, path, body)

            api.call = call
            self.assertNotEqual(
                self.execute(api)["classification"], "confirmed_success"
            )
            self.assertFalse(
                any(method in {"PUT", "DELETE"} for method, _, _ in api.calls)
            )

    @unittest.skipUnless(sys.platform == "win32", "Native Windows custody fixture")
    def test_native_only_public_handles_lock_exclusion_and_same_handle_read(self):
        with tempfile.TemporaryDirectory(
            prefix="fictional-profile-intake-"
        ) as temporary:
            root = Path(temporary).resolve(strict=True)
            intake.preparation.secure_acl(root, establish=True)
            native = intake.custody.Native()
            for name in intake.INPUTS:
                handle = native.open_handle(root / name, create=True)
                try:
                    data = b"fictional-public-input"
                    count = intake.w.DWORD()
                    self.assertTrue(
                        native.write(
                            handle,
                            ctypes.create_string_buffer(data),
                            len(data),
                            ctypes.byref(count),
                            None,
                        )
                    )
                    self.assertEqual(count.value, len(data))
                    self.assertTrue(native.flush(handle))
                finally:
                    native.close(handle)
            with intake.Inputs(root) as first:
                self.assertEqual(set(first.files), set(intake.INPUTS))
                first.lock()
                with intake.Inputs(root) as second:
                    with self.assertRaisesRegex(intake.Rejected, "LOCAL_LOCK_REJECTED"):
                        second.lock()
                self.assertEqual(
                    first.read(intake.INPUTS[0]), b"fictional-public-input"
                )
                with self.assertRaises(OSError):
                    (root / intake.INPUTS[0]).rename(root / "fictional-renamed")
            self.assertFalse((root / "profile-verification.lock").exists())
            self.assertFalse((root / "distribution-private-key.pem").exists())

    def test_environment_unknown_or_existing_secret_rejected(self):
        for change in [
            {"can_admins_bypass": True},
            {"protection_rules": []},
            {"deployment_branch_policy": None},
        ]:
            api = GitHubFixture()
            api.env_changes = change
            with self.assertRaisesRegex(intake.Rejected, "PROTECTION_REJECTED"):
                intake.remote_preflight(api, SHA)
        api = GitHubFixture()
        api.present = True
        with self.assertRaisesRegex(intake.Rejected, "SECRET_EXISTS"):
            intake.remote_preflight(api, SHA)

    def test_default_and_cancel_never_read_payload(self):
        for execute in [False, True]:
            session = Mock()
            session.__enter__ = Mock(return_value=session)
            session.__exit__ = Mock(return_value=False)
            with (
                patch.object(intake, "repository"),
                patch.object(intake, "GitHub", return_value=GitHubFixture()),
                patch.object(intake, "Inputs", return_value=session),
                patch.object(
                    intake.preparation,
                    "local_app_data",
                    return_value=__import__("pathlib").Path("fictional"),
                ),
                patch.object(intake.preparation, "hidden", return_value="cancel"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = intake.operate(SHA, execute=execute)
            self.assertEqual(
                result["reason"],
                "CONFIRMATION_REJECTED" if execute else "PREFLIGHT_PASSED",
            )
            session.read.assert_not_called()
            session.lock.assert_not_called()

    def test_envelope_cap_and_fixed_file_names(self):
        self.assertEqual(
            intake.INPUTS, ("distribution.cer", "distribution.mobileprovision")
        )
        with self.assertRaisesRegex(intake.Rejected, "INPUT_REJECTED"):
            intake.envelope(
                b"x" * 40000, b"y" * 10000, "FICTTEAM01", SHA, 42, "b" * 64, NOW
            )
        with (
            patch.object(
                intake,
                "bounded_process",
                return_value=(
                    1,
                    b"HTTP/2.0 404 Not Found\r\ncontent-type: application/json\r\n\r\n{}",
                ),
            ),
            patch.object(intake.shutil, "which", return_value="fictional-gh"),
        ):
            self.assertEqual(intake.GitHub().call("GET", "fictional"), (404, {}))

    def test_child_environment_drops_debug_tokens_and_private_input(self):
        process = Mock(
            stdin=Mock(), stdout=io.BytesIO(b"fictional-public-response"), returncode=0
        )
        process.poll.return_value = 0
        with (
            patch.dict(
                os.environ,
                {
                    "GH_DEBUG": "api",
                    "GH_TOKEN": "fictional-token",
                    intake.SECRET: "fictional-private",
                    "HTTPS_PROXY": "fictional-proxy",
                },
            ),
            patch.object(intake.subprocess, "Popen", return_value=process) as popen,
        ):
            self.assertEqual(
                intake.bounded_process(
                    ["fictional-gh"], b"fictional-encrypted-envelope"
                ),
                (0, b"fictional-public-response"),
            )
        child = popen.call_args.kwargs["env"]
        for key in ["GH_DEBUG", "GH_TOKEN", intake.SECRET, "HTTPS_PROXY"]:
            self.assertNotIn(key, child)
        self.assertNotIn(b"fictional-encrypted-envelope", popen.call_args.args[0])
        self.assertEqual(child["GH_PROMPT_DISABLED"], "1")


if __name__ == "__main__":
    unittest.main()
