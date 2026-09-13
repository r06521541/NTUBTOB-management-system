import unittest

from tools import ios_testflight_unsent as unsent

SHA = "a" * 40


class Journal:
    writable = True

    def __init__(self):
        self.snapshot = dict(
            sha="b" * 40,
            nonce="c" * 64,
            digest="d" * 64,
            issued=1,
            version="1.0.0",
            build=2,
            previous_build=1,
        )

    def unsent_snapshot(self):
        return dict(self.snapshot)


class Probe:
    def __init__(self):
        self.calls = []
        self.runs = {"total_count": 0, "workflow_runs": []}
        self.names = set()
        self.response = (404, {})
        self.error = None

    def policy(self):
        self.calls.append("policy")
        if self.error:
            raise self.error

    def context(self, *args):
        pass

    def get(self, path):
        self.calls.append(("GET", path))
        return self.runs

    def listing(self):
        self.calls.append("listing")
        return self.names

    def call(self, method, path):
        self.calls.append((method, path))
        return self.response


class UnsentTests(unittest.TestCase):
    def setUp(self):
        self.journal = Journal()
        self.probe = Probe()
        self.now = 100

    def verify(self):
        def factory(*args, **kwargs):
            self.assertEqual(args, (b"{}", b"{}"))
            self.assertEqual(kwargs, {"sha": SHA})
            return self.probe

        return unsent.verify(
            self.journal, SHA, session_factory=factory, clock=lambda: self.now
        )

    def consume(self, proof):
        return proof.consume(self.journal, SHA, clock=lambda: self.now)

    def test_invalid_source_before_remote(self):
        with self.assertRaises(unsent.Rejected):
            unsent.verify(
                None,
                "private-sentinel",
                session_factory=lambda *a, **k: self.fail("network"),
            )

    def test_exact_get_only_success_and_once(self):
        proof = self.verify()
        self.assertTrue(self.probe.recovery_only)
        self.assertEqual(
            self.probe.calls,
            [
                "policy",
                (
                    "GET",
                    unsent.dispatch.WORKFLOW
                    + "/runs?head_sha="
                    + "b" * 40
                    + "&event=workflow_dispatch&per_page=100&page=1",
                ),
                "listing",
            ]
            + [
                ("GET", unsent.dispatch.SECRET + n)
                for n in unsent.dispatch.wire.SECRETS
            ],
        )
        self.assertEqual(self.consume(proof), "d" * 64)
        with self.assertRaisesRegex(unsent.Rejected, "UNSENT_PROOF_CONSUMED"):
            self.consume(proof)

    def test_run_collection_strict(self):
        for value in [
            None,
            {},
            {"total_count": False, "workflow_runs": []},
            {"total_count": 1, "workflow_runs": []},
            {"total_count": 0, "workflow_runs": ()},
            {"total_count": 0, "workflow_runs": [{}]},
        ]:
            with self.subTest(value=value):
                self.probe.runs = value
                self.probe.calls.clear()
                with self.assertRaises(unsent.Rejected):
                    self.verify()
                self.assertEqual(len(self.probe.calls), 2)

    def test_secret_listing_and_each_status(self):
        for names in [None, [], {next(iter(unsent.dispatch.wire.SECRETS))}, {1}]:
            self.probe.names = names
            with self.assertRaises(unsent.Rejected):
                self.verify()
        self.probe.names = set()
        for status in [200, 401, 403, 429, 500, True, "404"]:
            self.probe.response = (status, {"private-sentinel": True})
            with self.assertRaises(unsent.Rejected) as caught:
                self.verify()
            self.assertNotIn("private-sentinel", repr(caught.exception))

    def test_transport_and_safe_failure(self):
        detail = unsent.diagnostics.failure("recovery", "run_listing", "HTTP_FORBIDDEN")
        for error in [
            RuntimeError("private-sentinel"),
            KeyboardInterrupt("private-sentinel"),
            unsent.dispatch.Rejected(detail),
        ]:
            self.probe.error = error
            with self.assertRaises(unsent.Rejected) as caught:
                self.verify()
            self.assertNotIn("private-sentinel", repr(caught.exception))
            self.assertEqual(
                caught.exception.failure,
                detail if isinstance(error, unsent.dispatch.Rejected) else None,
            )

    def test_partial_absence_stops_without_extra_requests(self):
        calls = []

        def call(method, path):
            calls.append((method, path))
            return (503, {}) if len(calls) == 3 else (404, {})

        self.probe.call = call
        with self.assertRaises(unsent.Rejected):
            self.verify()
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(method == "GET" for method, _ in calls))

    def test_different_journal_object_rejected(self):
        proof = self.verify()
        with self.assertRaisesRegex(unsent.Rejected, "UNSENT_PROOF_MISMATCH"):
            proof.consume(Journal(), SHA, clock=lambda: self.now)

    def test_snapshot_changes_during_remote(self):
        def listing():
            self.journal.snapshot["digest"] = "e" * 64
            return set()

        self.probe.listing = listing
        with self.assertRaisesRegex(unsent.Rejected, "UNSENT_PROOF_MISMATCH"):
            self.verify()

    def test_snapshot_rejected_before_remote(self):
        self.journal.snapshot["extra"] = "private-sentinel"
        with self.assertRaisesRegex(unsent.Rejected, "UNSENT_JOURNAL_REJECTED"):
            self.verify()
        self.assertEqual(self.probe.calls, [])

    def test_verification_timeout_and_clock_backwards(self):
        for instant in [161, 99, float("nan"), True]:

            def policy():
                self.now = instant

            self.now = 100
            self.probe.policy = policy
            with self.assertRaisesRegex(unsent.Rejected, "UNSENT_PROOF_EXPIRED"):
                self.verify()

    def test_failed_consume_is_consumed(self):
        for mutation in ["time", "backwards", "digest", "readonly", "source"]:
            self.setUp()
            proof = self.verify()
            if mutation == "time":
                self.now = 161
            if mutation == "backwards":
                self.now = 99
            if mutation == "digest":
                self.journal.snapshot["digest"] = "e" * 64
            if mutation == "readonly":
                self.journal.writable = False
            with self.assertRaises(unsent.Rejected):
                proof.consume(
                    self.journal,
                    "f" * 40 if mutation == "source" else SHA,
                    clock=lambda: self.now,
                )
            with self.assertRaisesRegex(unsent.Rejected, "UNSENT_PROOF_CONSUMED"):
                self.consume(proof)

    def test_boundary_and_repr(self):
        proof = self.verify()
        self.now = 160
        self.assertEqual(self.consume(proof), self.journal.snapshot["digest"])
        for value in self.journal.snapshot.values():
            self.assertNotIn(str(value), repr(proof))
        error = unsent.Rejected("private-sentinel", {"reason": "private-sentinel"})
        self.assertIsNone(error.failure)
        self.assertNotIn("private-sentinel", repr(error))


if __name__ == "__main__":
    unittest.main()
