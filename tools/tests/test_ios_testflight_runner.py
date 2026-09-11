import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import ios_testflight_runner as runner


class RunnerTests(unittest.TestCase):
    def candidate(self):
        prepared = runner.signing.PreparedSigning(
            Path("fictional"),
            Path("fictional/task-198-unit"),
            "a" * 40,
            "b" * 64,
            (1, 2),
            "c" * 64,
        )
        return runner.BoundCandidate(
            prepared, "d" * 64, 3, (1, 2, 0o100600, 7), "1.0.0", 1
        )

    def test_unknown_signing_is_unresolved(self):
        result = runner.sign_phase(None, {}, previous_build=0, now=None)
        self.assertEqual(result.public()["classification"], "UNRESOLVED")
        self.assertFalse(result.public()["upload_authorized"])

    def test_phase_order_and_original_material(self):
        candidate = self.candidate()
        material = dict(
            certificate_der=b"approved-cert",
            profile=b"approved-original",
            team="FICTTEAM01",
            version="1.0.0",
            build=1,
        )
        info = mock.Mock(st_dev=1, st_ino=2, st_mode=0o100600, st_uid=7, st_size=3)
        order = []
        with (
            mock.patch.object(runner, "_root"),
            mock.patch.object(
                runner.signing,
                "sign",
                side_effect=lambda *a, **k: order.append("sign")
                or {
                    "cleanup": "VERIFIED",
                    "classification": "EXPORTED_UNINSPECTED",
                    "operation": "EXPORTED",
                    "stage": "complete",
                    "artifact_relative": "candidate.ipa",
                    "artifact_sha256": "d" * 64,
                },
            ),
            mock.patch.object(
                runner.inspection,
                "inspect",
                side_effect=lambda *a, **k: order.append("inspect")
                or {"cleanup_verified": True, "classification": "ARTIFACT_BOUND"},
            ) as inspect,
            mock.patch.object(
                runner.signing, "_private_digest", return_value=("d" * 64, info)
            ),
            mock.patch.object(
                runner, "_cleanup", side_effect=lambda *a, **k: order.append("cleanup")
            ),
            mock.patch.object(runner, "_bound"),
            mock.patch.object(runner.upload, "UploadSession") as api,
        ):
            result = runner.sign_phase(
                candidate.prepared, material, previous_build=0, now="fictional-clock"
            )
        self.assertEqual(order, ["sign", "inspect", "cleanup"])
        self.assertEqual(result.classification, "CANDIDATE_BOUND")
        self.assertEqual(inspect.call_args.kwargs["profile"], b"approved-original")
        self.assertEqual(inspect.call_args.kwargs["certificate_der"], b"approved-cert")
        api.assert_not_called()

    def test_uncertain_custody_never_inspects_or_deletes(self):
        with (
            mock.patch.object(runner, "_root"),
            mock.patch.object(
                runner.signing, "sign", return_value={"cleanup": "UNRESOLVED"}
            ),
            mock.patch.object(runner.inspection, "inspect") as inspect,
            mock.patch.object(runner, "_cleanup") as clean,
        ):
            self.assertEqual(
                runner.sign_phase(None, {}, previous_build=0, now=None).classification,
                "UNRESOLVED",
            )
        inspect.assert_not_called()
        clean.assert_not_called()

    def test_one_upload_and_same_receipt_reconcile(self):
        candidate = self.candidate()
        session = mock.Mock()
        kwargs = dict(
            app_id="1",
            owner_group_id="2",
            owner_tester_id="3",
            version="1.0.0",
            build=1,
        )
        with (
            mock.patch.object(runner, "_bound", return_value=candidate.prepared.root),
            mock.patch.object(
                runner.upload, "UploadSession", return_value=session
            ) as factory,
        ):
            progress = runner.upload_phase(candidate, "fictional-asc", **kwargs)
            self.assertIs(progress.outcome, session.upload_once.return_value)
            runner.reconcile(progress)
            with self.assertRaises(runner.Rejected):
                runner.upload_phase(candidate, "fictional-asc", **kwargs)
            candidate.closed = True
            runner.reconcile(progress)
        factory.assert_called_once()
        session.upload_once.assert_called_once()
        self.assertEqual(session.reconcile.call_count, 2)

    def test_version_mismatch_and_active_lock_prevent_api(self):
        for locked in (False, True):
            candidate = self.candidate()
            if locked:
                candidate.lock.acquire()
            with (
                mock.patch.object(runner.upload, "UploadSession") as api,
                self.assertRaises(runner.Rejected),
            ):
                runner.upload_phase(
                    candidate,
                    None,
                    app_id="1",
                    owner_group_id="2",
                    owner_tester_id="3",
                    version="2.0.0",
                    build=1,
                )
            api.assert_not_called()
            if locked:
                self.assertEqual(
                    runner.final_cleanup(candidate).classification, "UNRESOLVED"
                )
                candidate.lock.release()

    def test_cleanup_hash_drift_or_failure_not_cleaned(self):
        for failed in ("_bound", "_cleanup"):
            candidate = self.candidate()
            with (
                mock.patch.object(runner, "_bound"),
                mock.patch.object(runner, "_cleanup"),
                mock.patch.object(
                    runner, failed, side_effect=OSError("private-sentinel")
                ),
            ):
                result = runner.final_cleanup(candidate)
            self.assertEqual(result.classification, "UNRESOLVED")
            self.assertNotIn("private-sentinel", repr(result.public()))

    def test_bound_digest_drift_and_root_escape(self):
        candidate = self.candidate()
        with (
            mock.patch.object(
                runner, "_root", return_value=(candidate.prepared.root, None)
            ),
            mock.patch.object(
                runner.signing, "_private_digest", return_value=("e" * 64, mock.Mock())
            ),
        ):
            with self.assertRaises(runner.Rejected):
                runner._bound(candidate)
        with (
            mock.patch.object(runner.signing, "_safe"),
            mock.patch.object(
                runner.signing.feasibility,
                "os_temp_root",
                return_value=Path("C:/approved"),
            ),
        ):
            with self.assertRaises(runner.Rejected):
                runner._root(candidate.prepared)

    def test_exception_keeps_private_receipt_but_prohibits_cleanup(self):
        candidate = self.candidate()
        session = mock.Mock()
        session.upload_once.side_effect = OSError("private-sentinel")
        with (
            mock.patch.object(runner, "_bound", return_value=candidate.prepared.root),
            mock.patch.object(runner.upload, "UploadSession", return_value=session),
        ):
            progress = runner.upload_phase(
                candidate,
                None,
                app_id="1",
                owner_group_id="2",
                owner_tester_id="3",
                version="1.0.0",
                build=1,
            )
        self.assertIs(progress.outcome.receipt, session.receipt)
        self.assertEqual(progress.outcome.classification, "UPLOAD_UNCERTAIN")
        with mock.patch.object(runner, "_cleanup") as cleanup:
            self.assertEqual(
                runner.final_cleanup(candidate).classification, "UNRESOLVED"
            )
        cleanup.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "POSIX dirfd cleanup fixture")
    def test_cleanup_symlink_target_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "task-198-unit"
            root.mkdir(mode=0o700)
            target = base / "outside"
            target.write_bytes(b"fictional")
            (root / "link").symlink_to(target)
            (root / "candidate.ipa").write_bytes(b"ipa")
            info = root.stat()
            prepared = runner.signing.PreparedSigning(
                base, root, "a" * 40, "b" * 64, (info.st_dev, info.st_ino), "c" * 64
            )
            with mock.patch.object(
                runner.signing.feasibility, "os_temp_root", return_value=base
            ):
                runner._cleanup(prepared, keep_candidate=True)
                self.assertEqual(set(p.name for p in root.iterdir()), {"candidate.ipa"})
                self.assertEqual(target.read_bytes(), b"fictional")
                runner._cleanup(prepared, keep_candidate=False)
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
