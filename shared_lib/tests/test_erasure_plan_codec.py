"""Fictional-only sealed snapshot roundtrips; no actual storage or key reads."""

import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from shared_module.account_erasure_scope import LegacyErasureScope
from shared_module.erasure_restore_binding import RestoreBinding
from shared_module.portal_data.erasure_fulfillment import PendingIdentitySnapshot
from shared_module.portal_data.erasure_person_fulfillment import (
    PersonIdentitySnapshot,
    PersonSnapshot,
    ReviewedPersonDisposition,
    SessionVerificationBaseline,
)
from shared_module.portal_data.erasure_plan_codec import (
    ErasurePlanCodec,
    PlanCodecRejected,
)
from shared_module.portal_data.erasure_structured_execution import StructuredInventory

JOB = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"
NS = "00000000-0000-4000-8000-000000000003"


class PlanCodecTests(unittest.TestCase):
    def codec(self, key=b"F" * 32):
        return ErasurePlanCodec(namespace=NS, key=key)

    def pending(self):
        return PendingIdentitySnapshot(
            1,
            GEN,
            "a" * 64,
            (("access_audit", ((4, "b" * 64),)),),
            RestoreBinding(1, "fictional", "c" * 64),
        )

    def person(self):
        return PersonSnapshot(
            3,
            GEN,
            "a" * 64,
            (
                PersonIdentitySnapshot(
                    1, "apple", GEN, "b" * 64, RestoreBinding(1, "fictional", "c" * 64)
                ),
            ),
            (("events", ((5, "d" * 64),)),),
            (
                SessionVerificationBaseline(
                    JOB, "active", None, datetime(2026, 1, 1, tzinfo=timezone.utc), 1
                ),
            ),
            LegacyErasureScope((1,), (2,), (3,)),
            StructuredInventory(
                3, ((1, GEN),), (("mobile_sessions", ((JOB, 3, 1),)),), ()
            ),
            (("event_invitees", ()),),
            (
                ReviewedPersonDisposition(
                    "events",
                    5,
                    "d" * 64,
                    "update",
                    '{"title":"Fictional shared text"}',
                    "e" * 64,
                    ("title",),
                    "no_target_content_after_disposition",
                ),
            ),
        )

    def decode(self, codec, blob, snapshot, **overrides):
        args = dict(
            job_id=JOB,
            target_kind=(
                "person" if type(snapshot) is PersonSnapshot else "pending_identity"
            ),
            generation=GEN,
            scope_hash=snapshot.scope_hash,
        )
        args.update(overrides)
        return codec.decode(blob, **args)

    def test_both_types_roundtrip_after_new_codec_instance(self):
        for snapshot in (self.pending(), self.person()):
            with self.subTest(kind=type(snapshot).__name__):
                blob = self.codec().encode(snapshot, job_id=JOB)
                restored = self.decode(self.codec(), blob, snapshot)
                self.assertEqual(restored, snapshot)
                self.assertEqual(restored.scope_hash, snapshot.scope_hash)
                self.assertNotIn(b"Fictional shared text", blob)
                self.assertNotIn(GEN.encode(), blob)
                self.assertNotEqual(blob, self.codec().encode(snapshot, job_id=JOB))

    def test_wrong_binding_key_and_tampering_never_return_snapshot(self):
        snapshot = self.person()
        blob = self.codec().encode(snapshot, job_id=JOB)
        for changes in (
            {"job_id": GEN},
            {"generation": JOB},
            {"scope_hash": "f" * 64},
            {"target_kind": "pending_identity"},
        ):
            with self.subTest(changes=tuple(changes)):
                with self.assertRaises(PlanCodecRejected):
                    self.decode(self.codec(), blob, snapshot, **changes)
        for invalid in (
            blob[:-1],
            blob[:-1] + bytes([blob[-1] ^ 1]),
            b"",
            b"x" * (ErasurePlanCodec.MAX_BYTES + 100),
        ):
            with self.assertRaises(PlanCodecRejected):
                self.decode(self.codec(), invalid, snapshot)
        with self.assertRaises(PlanCodecRejected):
            self.decode(self.codec(b"X" * 32), blob, snapshot)

    def test_only_fixed_snapshot_types_and_bounded_values(self):
        for value in (object(), {"type": "PersonSnapshot"}, (1,), None):
            with self.assertRaises(PlanCodecRejected):
                self.codec().encode(value, job_id=JOB)
        for value in (
            replace(self.pending(), identity_id=True),
            replace(self.pending(), generation="bad"),
            replace(self.pending(), rows=(("x", (object(),)),)),
        ):
            with self.assertRaises(PlanCodecRejected):
                self.codec().encode(value, job_id=JOB)

    def test_authenticated_but_unknown_or_duplicate_shape_is_rejected(self):
        from shared_module.portal_data import erasure_plan_codec as module

        snapshot = self.pending()
        codec = self.codec()
        aad = codec._aad(JOB, "pending_identity", GEN, snapshot.scope_hash)
        nonce = b"fictional123"
        shapes = (
            b'{"type":"os.system","value":[]}',
            b'{"type":"tuple","type":"tuple","value":[]}',
            b'{"type":"PendingIdentitySnapshot","value":[true]}',
            b'{"type":"datetime","value":"2026-01-01"}',
            b'{"type":"tuple","value":[NaN]}',
            json.dumps({"type": "tuple", "value": ["x" * 65537]}).encode(),
        )
        for plain in shapes:
            blob = module._PREFIX + nonce + AESGCM(b"F" * 32).encrypt(nonce, plain, aad)
            with self.subTest(size=len(plain)):
                with self.assertRaises(PlanCodecRejected) as raised:
                    self.decode(codec, blob, snapshot)
                self.assertTrue(raised.exception.__suppress_context__)

    def test_namespace_is_part_of_binding(self):
        snapshot = self.pending()
        blob = self.codec().encode(snapshot, job_id=JOB)
        with self.assertRaises(PlanCodecRejected):
            self.decode(ErasurePlanCodec(namespace=JOB, key=b"F" * 32), blob, snapshot)

    def test_depth_and_node_budgets_reject_on_encode_and_decode(self):
        from shared_module.portal_data import erasure_plan_codec as module

        nested = ()
        for _ in range(module._MAX_DEPTH + 1):
            nested = (nested,)
        with self.assertRaises(PlanCodecRejected):
            self.codec().encode(replace(self.pending(), rows=nested), job_id=JOB)
        with self.assertRaises(PlanCodecRejected):
            self.codec().encode(
                replace(self.pending(), rows=(0,) * module._MAX_NODES), job_id=JOB
            )
        tree = {"type": "tuple", "value": []}
        for _ in range(module._MAX_DEPTH + 1):
            tree = {"type": "tuple", "value": [tree]}
        codec = self.codec()
        snapshot = self.pending()
        aad = codec._aad(JOB, "pending_identity", GEN, snapshot.scope_hash)
        for shape in (tree, {"type": "tuple", "value": [0] * module._MAX_NODES}):
            nonce = b"fictional123"
            blob = (
                module._PREFIX
                + nonce
                + AESGCM(b"F" * 32).encrypt(nonce, json.dumps(shape).encode(), aad)
            )
            with self.assertRaises(PlanCodecRejected):
                self.decode(codec, blob, snapshot)


if __name__ == "__main__":
    unittest.main()
