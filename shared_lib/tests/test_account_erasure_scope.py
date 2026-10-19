import unittest

from shared_lib.shared_module.account_erasure_scope import (
    AttendanceReference,
    ErasureScopeRejected,
    LegacyIdentityReference,
    MemberReference,
    plan_legacy_attendance_erasure,
)


class LegacyErasureScopeTests(unittest.TestCase):
    def plan(self, replies, members=None, identities=None):
        return plan_legacy_attendance_erasure(
            10,
            (
                members
                if members is not None
                else [MemberReference(20, 10), MemberReference(21, 11)]
            ),
            (
                identities
                if identities is not None
                else [LegacyIdentityReference(30, 20), LegacyIdentityReference(31, 21)]
            ),
            replies,
        )

    def test_selects_only_same_person_and_preserves_other_reply(self):
        result = self.plan(
            [
                AttendanceReference(40, 10, 20, 30),
                AttendanceReference(41, 11, 21, 31),
            ]
        )
        self.assertEqual(result.reply_ids, (40,))
        self.assertEqual(result.member_ids, (20,))
        self.assertEqual(result.line_user_ids, (30,))

    def test_each_legacy_reference_can_prove_ownership(self):
        result = self.plan(
            [
                AttendanceReference(42, None, None, 30),
                AttendanceReference(40, 10, None, None),
                AttendanceReference(41, None, 20, None),
            ]
        )
        self.assertEqual(result.reply_ids, (40, 41, 42))

    def test_conflicting_person_member_or_user_stops(self):
        for row in (
            AttendanceReference(40, 10, 21, None),
            AttendanceReference(40, 10, None, 31),
            AttendanceReference(40, None, 20, 31),
        ):
            with (
                self.subTest(row=row),
                self.assertRaises(ErasureScopeRejected) as error,
            ):
                self.plan([row])
            self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_dangling_references_stop_even_with_matching_person(self):
        for row in (
            AttendanceReference(40, 10, 999, None),
            AttendanceReference(40, 10, None, 999),
        ):
            with self.subTest(row=row), self.assertRaises(ErasureScopeRejected):
                self.plan([row])

    def test_unbound_user_must_not_be_inferred_from_reply(self):
        with self.assertRaises(ErasureScopeRejected):
            self.plan(
                [AttendanceReference(40, 10, None, 30)],
                identities=[LegacyIdentityReference(30, None)],
            )

    def test_unbound_rows_require_attention_not_silent_omission(self):
        with self.assertRaises(ErasureScopeRejected):
            self.plan([AttendanceReference(40, None, None, None)])

    def test_duplicate_input_rejected_not_last_write_wins(self):
        with self.assertRaises(ErasureScopeRejected):
            self.plan([], members=[MemberReference(20, 10), MemberReference(20, 11)])
        with self.assertRaises(ErasureScopeRejected):
            self.plan([AttendanceReference(40, 10, None, None)] * 2)

    def test_rejects_boolean_and_nonpositive_ids(self):
        for person_id in (True, 0, -1, "10"):
            with (
                self.subTest(person_id=person_id),
                self.assertRaises(ErasureScopeRejected),
            ):
                plan_legacy_attendance_erasure(person_id, [], [], [])

    def test_no_rows_still_selects_owned_legacy_links(self):
        self.assertEqual(self.plan([]).line_user_ids, (30,))

    def test_unlinked_identity_not_selected(self):
        result = self.plan([], identities=[LegacyIdentityReference(30, None)])
        self.assertEqual(result.line_user_ids, ())

    def test_direct_person_link_selects_user_and_reply_without_member(self):
        result = self.plan(
            [AttendanceReference(40, None, None, 30)],
            members=[],
            identities=[LegacyIdentityReference(30, None, 10)],
        )
        self.assertEqual(result.member_ids, ())
        self.assertEqual(result.line_user_ids, (30,))
        self.assertEqual(result.reply_ids, (40,))

    def test_direct_person_link_selects_user_without_any_reply(self):
        result = self.plan(
            [], members=[], identities=[LegacyIdentityReference(30, None, 10)]
        )
        self.assertEqual(result.line_user_ids, (30,))

    def test_matching_direct_and_member_ownership_is_not_a_duplicate(self):
        result = self.plan([], identities=[LegacyIdentityReference(30, 20, 10)])
        self.assertEqual(result.line_user_ids, (30,))

    def test_conflicting_direct_and_member_ownership_rejected_without_replies(self):
        for user in (
            LegacyIdentityReference(30, 20, 11),
            LegacyIdentityReference(30, 21, 10),
        ):
            with self.subTest(user=user):
                with self.assertRaises(ErasureScopeRejected) as error:
                    self.plan([], identities=[user])
                self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_foreign_direct_link_conflicts_with_reply_person(self):
        with self.assertRaises(ErasureScopeRejected) as error:
            self.plan(
                [AttendanceReference(40, 10, None, 30)],
                identities=[LegacyIdentityReference(30, None, 11)],
            )
        self.assertEqual(error.exception.reason, "OWNERSHIP_CONFLICT")

    def test_direct_link_does_not_mask_unresolved_member(self):
        for members in ([], [MemberReference(20, None)]):
            with self.subTest(members=members), self.assertRaises(ErasureScopeRejected):
                self.plan(
                    [],
                    members=members,
                    identities=[LegacyIdentityReference(30, 20, 10)],
                )

    def test_direct_owner_requires_valid_identifier(self):
        for direct_owner in (True, 0, -1, "10"):
            with (
                self.subTest(owner=direct_owner),
                self.assertRaises(ErasureScopeRejected),
            ):
                self.plan(
                    [], identities=[LegacyIdentityReference(30, None, direct_owner)]
                )

    def test_foreign_direct_owner_not_selected(self):
        result = self.plan(
            [AttendanceReference(40, None, None, 30)],
            members=[],
            identities=[LegacyIdentityReference(30, None, 11)],
        )
        self.assertEqual(result.line_user_ids, ())
        self.assertEqual(result.reply_ids, ())

    def test_error_does_not_reveal_row_ids_or_input(self):
        with self.assertRaises(ErasureScopeRejected) as error:
            self.plan([AttendanceReference(987654321, 10, 21, None)])
        self.assertNotIn("987654321", str(error.exception))

    def test_plan_is_immutable(self):
        from dataclasses import FrozenInstanceError

        result = self.plan([])
        with self.assertRaises(FrozenInstanceError):
            result.reply_ids = (1,)
