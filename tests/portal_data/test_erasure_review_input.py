"""Actual locked review import, using only the opt-in fictional PG fixture."""

import json
import unittest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.erasure_review_input import (
    ReviewInputRejected,
    import_person_review,
)
from tests.portal_data import test_erasure_privacy_mutation as fixture


@unittest.skipUnless(
    fixture.items.fixture.DATABASE_URL, "isolated erasure URL not configured"
)
class ReviewedInputPostgresTests(unittest.TestCase):
    setUpClass = classmethod(fixture.ErasurePrivacyPostgresTests.setUpClass.__func__)
    tearDownClass = classmethod(
        fixture.ErasurePrivacyPostgresTests.tearDownClass.__func__
    )
    job = fixture.ErasurePrivacyPostgresTests.job
    update = fixture.ErasurePrivacyPostgresTests.update
    setUp = fixture.ErasurePrivacyPostgresTests.setUp
    tearDown = fixture.ErasurePrivacyPostgresTests.tearDown

    def packet(self):
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.auth_identities (provider,provider_subject,person_id,status,created_at,updated_at) VALUES ('apple',:subject,:person,'linked',:now,:now)"
            ),
            {
                "subject": "fictional-import-" + uuid4().hex,
                "person": self.person,
                "now": fixture.items.CREATED,
            },
        )
        digest = self.connection.scalar(
            text(
                "SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') FROM ntubtob.access_audit t WHERE id=:id"
            ),
            {"id": self.row_id},
        )
        return {
            "version": 1,
            "person_id": self.person,
            "generation": self.generation,
            "dispositions": [
                {
                    "table": "access_audit",
                    "row_id": self.row_id,
                    "old_digest": digest,
                    "action": "update",
                    "patch": {"reason": "Reviewed shared context"},
                    "reviewed_fields": ["reason", "before_state", "after_state"],
                    "decision": "no_target_content_after_disposition",
                }
            ],
        }

    def test_actual_import_binds_old_image_and_writes_no_content(self):
        packet = self.packet()
        with (
            Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            result = import_person_review(
                session,
                payload=json.dumps(packet).encode(),
                person_id=self.person,
                generation=self.generation,
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(
                result[0].old_digest, packet["dispositions"][0]["old_digest"]
            )
            self.assertEqual(
                json.loads(result[0].patch_json), {"reason": "Reviewed shared context"}
            )
        digest = self.connection.scalar(
            text(
                "SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') FROM ntubtob.access_audit t WHERE id=:id"
            ),
            {"id": self.row_id},
        )
        self.assertEqual(digest, packet["dispositions"][0]["old_digest"])

    def test_stale_hash_and_different_generation_are_rejected(self):
        packet = self.packet()
        for mode in ("hash", "generation"):
            candidate = json.loads(json.dumps(packet))
            generation = self.generation
            if mode == "hash":
                candidate["dispositions"][0]["old_digest"] = "0" * 64
            else:
                generation = str(uuid4())
                candidate["generation"] = generation
            with self.subTest(mode=mode):
                with (
                    Session(
                        bind=self.connection, join_transaction_mode="create_savepoint"
                    ) as session,
                    session.begin(),
                ):
                    with self.assertRaises(ReviewInputRejected):
                        import_person_review(
                            session,
                            payload=json.dumps(candidate).encode(),
                            person_id=self.person,
                            generation=generation,
                        )


if __name__ == "__main__":
    unittest.main()
