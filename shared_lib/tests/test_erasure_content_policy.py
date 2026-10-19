import unittest

from shared_module.erasure_content_policy import (
    ContentDisposition,
    ContentEvidence,
    ContentOrigin,
    ContentPolicyRejected,
    disposition_for,
)


class ContentPolicyTests(unittest.TestCase):
    def evidence(self, **overrides):
        values = dict(
            origin=ContentOrigin.USER_CONTENT,
            author_person_id=10,
            subject_person_ids=frozenset(),
            attribution_complete=False,
        )
        values.update(overrides)
        return ContentEvidence(**values)

    def test_own_user_content_is_deleted_even_if_shared_or_unattributed(self):
        self.assertEqual(
            disposition_for(10, self.evidence(subject_person_ids=frozenset({20}))),
            ContentDisposition.DELETE_OWN_CONTENT,
        )

    def test_other_authors_mention_requires_review_not_whole_content_deletion(self):
        self.assertEqual(
            disposition_for(
                10,
                self.evidence(
                    author_person_id=20, subject_person_ids=frozenset({10, 20})
                ),
            ),
            ContentDisposition.REVIEW_SHARED_CONTENT,
        )

    def test_absent_subject_does_not_prove_absent_personal_information(self):
        self.assertEqual(
            disposition_for(10, self.evidence(author_person_id=20)),
            ContentDisposition.REVIEW_SHARED_CONTENT,
        )

    def test_only_complete_attribution_can_classify_unrelated_content(self):
        self.assertEqual(
            disposition_for(
                10, self.evidence(author_person_id=20, attribution_complete=True)
            ),
            ContentDisposition.KEEP_UNRELATED,
        )

    def test_official_record_actor_is_not_automatically_personal_content_owner(self):
        for origin in (ContentOrigin.SHARED_TEAM_RECORD, ContentOrigin.SYSTEM_TEMPLATE):
            with self.subTest(origin=origin):
                self.assertEqual(
                    disposition_for(
                        10, self.evidence(origin=origin, attribution_complete=True)
                    ),
                    ContentDisposition.REMOVE_ACTOR_REFERENCE,
                )

    def test_shared_record_with_personal_text_requires_review_even_for_its_actor(self):
        self.assertEqual(
            disposition_for(10, self.evidence(origin=ContentOrigin.SHARED_TEAM_RECORD)),
            ContentDisposition.REVIEW_SHARED_CONTENT,
        )

    def test_unknown_origin_or_author_is_not_a_keep_or_delete_permit(self):
        for change in (dict(origin=ContentOrigin.UNKNOWN), dict(author_person_id=None)):
            with self.subTest(change=change):
                self.assertEqual(
                    disposition_for(
                        10, self.evidence(attribution_complete=True, **change)
                    ),
                    ContentDisposition.REVIEW_SHARED_CONTENT,
                )

    def test_invalid_inputs_rejected_with_fixed_nonpersonal_diagnostics(self):
        for target in (True, 0, -1, "private-name"):
            with (
                self.subTest(target=target),
                self.assertRaises(ContentPolicyRejected) as error,
            ):
                disposition_for(target, self.evidence())
            self.assertEqual(str(error.exception), "invalid_content_evidence")
        for change in (
            dict(origin="user_content"),
            dict(author_person_id=True),
            dict(subject_person_ids=[10]),
            dict(subject_person_ids=frozenset({False})),
            dict(attribution_complete=1),
        ):
            with self.subTest(change=change), self.assertRaises(ContentPolicyRejected):
                disposition_for(10, self.evidence(**change))
