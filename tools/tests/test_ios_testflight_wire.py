"""Fictional transfer only; no environment secrets or hosted requests."""

import json
import unittest

from tools import ios_testflight_wire as wire


class WireTests(unittest.TestCase):
    def binding(self):
        return wire.Binding("a" * 40, "b" * 64, "123")

    def environment(self):
        binding = self.binding()
        return {
            "GITHUB_REPOSITORY": wire.REPO,
            "GITHUB_WORKFLOW_REF": wire.REPO
            + "/.github/workflows/"
            + wire.WORKFLOW
            + "@refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_RUN_ID": binding.run_id,
            "GITHUB_SHA": binding.sha,
            "INPUT_APPROVED_SHA": binding.sha,
            "INPUT_NONCE": binding.nonce,
            "RUNNER_OS": "macOS",
        }

    def test_roundtrip_chunking_and_purpose_separation(self):
        private = b"fictional-signing-sentinel" * 4000
        envelope = wire.pack(
            private, b"fictional-asc-sentinel", self.binding(), now=1000
        )
        self.assertEqual(set(envelope), set(wire.SECRETS))
        self.assertTrue(all(len(v.encode("ascii")) <= 49152 for v in envelope.values()))
        self.assertTrue(
            sum(len(v.encode("ascii")) for v in envelope.values())
            <= wire.MAX_ENVIRONMENT
        )
        self.assertNotIn(
            "fictional-asc-sentinel", "".join(envelope[n] for n in wire.SIGN_NAMES)
        )
        values = dict(envelope)
        result = wire.consume(values, self.binding(), now=1100)
        self.assertEqual(result.signing_frame, private)
        self.assertEqual(result.asc_frame, b"fictional-asc-sentinel")
        self.assertFalse(values)
        self.assertNotIn("sentinel", repr(result))
        with self.assertRaises(wire.Rejected):
            wire.consume(values, self.binding(), now=1100)

    def test_context_is_exact_first_attempt_main_workflow(self):
        self.assertEqual(wire.context(self.environment()), self.binding())
        for key in self.environment():
            with self.subTest(key=key), self.assertRaises(wire.Rejected):
                wire.context(self.environment() | {key: "wrong"})

    def test_missing_reordered_modified_and_duplicate_chunks(self):
        original = wire.pack(b"s" * 70000, b"a", self.binding(), now=1000)
        for scenario in (
            "missing",
            "reorder",
            "modified",
            "duplicate_json",
            "extra_slot",
        ):
            with self.subTest(scenario=scenario):
                env = dict(original)
                if scenario == "missing":
                    env.pop(wire.SIGN_NAMES[0])
                elif scenario == "reorder":
                    env[wire.SIGN_NAMES[0]], env[wire.SIGN_NAMES[1]] = (
                        env[wire.SIGN_NAMES[1]],
                        env[wire.SIGN_NAMES[0]],
                    )
                elif scenario == "modified":
                    data = json.loads(env[wire.SIGN_NAMES[0]])
                    data["data"] = "foreign"
                    env[wire.SIGN_NAMES[0]] = json.dumps(data)
                elif scenario == "extra_slot":
                    env["IOS_TF_SIGN_4"] = "private-sentinel"
                else:
                    env[wire.SIGN_NAMES[0]] = '{"index":0,"index":0,"data":"s"}'
                with self.assertRaises(wire.Rejected):
                    wire.consume(env, self.binding(), now=1001)
                self.assertFalse(any(n in env for n in wire.SECRETS))

    def test_expiry_wrong_run_and_hash_are_rejected(self):
        original = wire.pack(b"s", b"a", self.binding(), now=1000)
        for field, value in (
            ("run_id", "999"),
            ("sha", "c" * 40),
            ("nonce", "d" * 64),
            ("sign_sha256", "e" * 64),
            ("asc_sha256", "e" * 64),
            ("expires_at", 1001),
            ("issued_at", True),
            ("format", 2),
        ):
            with self.subTest(field=field):
                env = dict(original)
                manifest = json.loads(env[wire.MANIFEST])
                manifest[field] = value
                env[wire.MANIFEST] = json.dumps(manifest)
                with self.assertRaises(wire.Rejected):
                    wire.consume(env, self.binding(), now=1100)
        for now in (999, 1000 + wire.TTL):
            with self.assertRaises(wire.Rejected):
                wire.consume(dict(original), self.binding(), now=now)

    def test_bounds_reject_before_any_dispatch(self):
        for sign, asc in (
            (b"", b"a"),
            (b"s", b""),
            (b"s" * (wire.MAX_SIGN + 1), b"a"),
            (b"s", b"a" * (wire.MAX_ASC + 1)),
            (b"\xff", b"a"),
            (b"\x00", b"a"),
        ):
            with self.assertRaises(wire.Rejected):
                wire.pack(sign, asc, self.binding(), now=1000)
        for binding in (
            wire.Binding("bad", "b" * 64, "123"),
            wire.Binding("a" * 40, "b" * 64, "0"),
        ):
            with self.assertRaises(wire.Rejected):
                wire.pack(b"s", b"a", binding, now=1000)


if __name__ == "__main__":
    unittest.main()
