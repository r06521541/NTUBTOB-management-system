"""Fictional internal review import; no operator, database or file access."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shared_module.portal_data import erasure_review_input as subject

GENERATION = "00000000-0000-4000-8000-000000000001"


class ErasureReviewInputTests(unittest.TestCase):
    def packet(self):
        return {
            "version": 1,
            "person_id": 7,
            "generation": GENERATION,
            "dispositions": [
                {
                    "table": "games",
                    "row_id": 9,
                    "old_digest": "a" * 64,
                    "action": "update",
                    "patch": {"location": "Fictional reviewed shared location"},
                    "reviewed_fields": ["location", "home_team", "away_team"],
                    "decision": "no_target_content_after_disposition",
                }
            ],
        }

    def run_import(self, packet, *, observed="a" * 64):
        raw = packet if type(packet) is bytes else json.dumps(packet).encode()
        session = Mock()
        connection = Mock()
        sealed = SimpleNamespace(old_digest=observed)
        with (
            patch.object(subject, "_connection", return_value=connection) as conn,
            patch.object(subject, "_lock") as lock,
            patch.object(
                subject, "_capture_roots", return_value=((GENERATION, "b" * 64), ())
            ),
            patch.object(
                subject, "seal_reviewed_person_disposition", return_value=sealed
            ) as seal,
        ):
            result = subject.import_person_review(
                session, payload=raw, person_id=7, generation=GENERATION
            )
            conn.assert_called_once_with(session)
            lock.assert_called_once_with(connection)
            connection.execute.assert_not_called()
            session.commit.assert_not_called()
            return result, seal.call_args

    def test_exact_review_uses_current_digest_without_rewriting_decision(self):
        result, args = self.run_import(self.packet())
        self.assertEqual(len(result), 1)
        self.assertEqual(
            args.kwargs["patch"], self.packet()["dispositions"][0]["patch"]
        )
        self.assertEqual(
            args.kwargs["reviewed_fields"], ("location", "home_team", "away_team")
        )

    def test_stale_review_never_rebinds_current_row(self):
        with self.assertRaisesRegex(
            subject.ReviewInputRejected, "review_input_rejected"
        ):
            self.run_import(self.packet(), observed="b" * 64)

    def test_malformed_or_out_of_scope_input_rejects_before_storage(self):
        variants = []
        for key, value in (
            ("version", True),
            ("person_id", 8),
            ("generation", "invalid"),
            ("unknown", 1),
        ):
            packet = self.packet()
            packet[key] = value
            variants.append(json.dumps(packet).encode())
        variants.extend(
            (
                b'{"version":1,"version":1}',
                b'{"x":NaN}',
                b"\xff",
                b"[]",
                b" " * (subject.MAX_BYTES + 1),
            )
        )
        for payload in variants:
            with self.subTest(size=len(payload)):
                with patch.object(subject, "_connection") as conn:
                    with self.assertRaises(subject.ReviewInputRejected):
                        subject.import_person_review(
                            Mock(), payload=payload, person_id=7, generation=GENERATION
                        )
                    conn.assert_not_called()

    def test_duplicate_rows_or_unknown_patch_and_incomplete_review_reject(self):
        for mutation in (
            "duplicate",
            "patch",
            "fields",
            "unknown",
            "boolean_id",
            "delete_game",
        ):
            packet = self.packet()
            row = packet["dispositions"][0]
            if mutation == "duplicate":
                packet["dispositions"].append(dict(row))
            elif mutation == "patch":
                row["patch"] = {"duration": 10}
            elif mutation == "fields":
                row["reviewed_fields"] = ["location"]
            elif mutation == "unknown":
                row["subject"] = "Fictional private text"
            elif mutation == "boolean_id":
                row["row_id"] = True
            else:
                row.update(action="delete", patch={}, decision="own_content_delete")
            with self.subTest(mutation=mutation):
                with patch.object(subject, "_connection") as conn:
                    with self.assertRaises(subject.ReviewInputRejected) as raised:
                        subject.import_person_review(
                            Mock(),
                            payload=json.dumps(packet).encode(),
                            person_id=7,
                            generation=GENERATION,
                        )
                    conn.assert_not_called()
                    self.assertNotIn("Fictional", str(raised.exception))

    def test_storage_failure_is_fixed_and_does_not_echo_private_input(self):
        with patch.object(
            subject,
            "_connection",
            side_effect=RuntimeError("Fictional secret-bearing driver error"),
        ):
            with self.assertRaises(subject.ReviewInputUnavailable) as raised:
                subject.import_person_review(
                    Mock(),
                    payload=json.dumps(self.packet()).encode(),
                    person_id=7,
                    generation=GENERATION,
                )
            self.assertEqual(str(raised.exception), "review_input_unavailable")


if __name__ == "__main__":
    unittest.main()
