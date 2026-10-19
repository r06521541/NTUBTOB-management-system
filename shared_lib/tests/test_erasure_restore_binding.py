import unittest

from shared_lib.shared_module.erasure_restore_binding import (
    RestoreBinding,
    RestoreBindingCodec,
    RestoreBindingUnavailable,
)

NAMESPACE = "11111111-1111-4111-8111-111111111111"
GENERATION = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
TARGET = dict(
    provider="apple",
    audience="fictional-client",
    subject="fictional-subject",
    generation=GENERATION,
)


class RestoreBindingTests(unittest.TestCase):
    def test_surrogates_rejected_without_collapsing_valid_astral_subjects(self):
        codec = self.codec()
        for field in ("audience", "subject"):
            scalar = TARGET | {field: "\U0001f600"}
            self.assertTrue(codec.matches(codec.bind(**scalar), **scalar))
            for invalid in ("\ud83d\ude00", "\ud83d", "\ude00"):
                with self.subTest(field=field, size=len(invalid)):
                    with self.assertRaises(RestoreBindingUnavailable):
                        codec.bind(**(TARGET | {field: invalid}))

    def codec(self, **changes):
        return RestoreBindingCodec(
            **dict(namespace=NAMESPACE, active_key="v1", keys={"v1": b"f" * 32})
            | changes
        )

    def test_exact_match_and_private_representation(self):
        codec = self.codec()
        binding = codec.bind(**TARGET)
        self.assertEqual(binding, codec.bind(**TARGET))
        self.assertTrue(codec.matches(binding, **TARGET))
        for private in (
            TARGET["subject"],
            TARGET["audience"],
            GENERATION,
            binding.digest,
        ):
            self.assertNotIn(private, repr(binding))
            self.assertNotIn(private, repr(codec))

    def test_each_identity_dimension_and_environment_is_bound(self):
        codec = self.codec()
        binding = codec.bind(**TARGET)
        for key, value in (
            ("provider", "google"),
            ("audience", "other-client"),
            ("subject", "Fictional-subject"),
            ("generation", OTHER),
        ):
            with self.subTest(key=key):
                self.assertFalse(codec.matches(binding, **(TARGET | {key: value})))
        self.assertFalse(self.codec(namespace=OTHER).matches(binding, **TARGET))

    def test_rotation_verifies_old_key_but_missing_key_is_not_no_match(self):
        binding = self.codec().bind(**TARGET)
        rotated = self.codec(active_key="v2", keys={"v1": b"f" * 32, "v2": b"g" * 32})
        self.assertTrue(rotated.matches(binding, **TARGET))
        self.assertNotEqual(binding.digest, rotated.bind(**TARGET).digest)
        with self.assertRaisesRegex(
            RestoreBindingUnavailable, "^restore_binding_unavailable$"
        ):
            self.codec(active_key="v2", keys={"v2": b"g" * 32}).matches(
                binding, **TARGET
            )
        # Labels are bound even if misconfigured to use the same key bytes.
        same_bytes = self.codec(
            active_key="v2", keys={"v1": b"f" * 32, "v2": b"f" * 32}
        )
        self.assertNotEqual(binding.digest, same_bytes.bind(**TARGET).digest)

    def test_delimiters_cannot_confuse_subject_and_audience(self):
        codec = self.codec()
        binding = codec.bind(**(TARGET | {"audience": "one:two", "subject": "three"}))
        self.assertFalse(
            codec.matches(
                binding, **(TARGET | {"audience": "one", "subject": "two:three"})
            )
        )

    def test_malformed_record_never_means_absent(self):
        codec = self.codec()
        for binding in (
            None,
            {},
            RestoreBinding(True, "v1", "f" * 64),
            RestoreBinding(2, "v1", "f" * 64),
            RestoreBinding(1, "v1", "F" * 64),
            RestoreBinding(1, "private\nvalue", "f" * 64),
        ):
            with self.subTest(binding_type=type(binding).__name__):
                with self.assertRaisesRegex(
                    RestoreBindingUnavailable, "^restore_binding_unavailable$"
                ):
                    codec.matches(binding, **TARGET)

    def test_invalid_inputs_have_fixed_error_and_copy_keyring(self):
        for changes in (
            {"namespace": "bad"},
            {"keys": {}},
            {"active_key": "absent"},
            {"keys": {"v1": b"short"}},
            {"keys": {"v1": "private"}},
        ):
            with self.assertRaises(RestoreBindingUnavailable):
                self.codec(**changes)
        codec = self.codec()
        for key, value in (
            ("provider", "other"),
            ("subject", "private\nvalue"),
            ("audience", ""),
            ("generation", "bad"),
        ):
            with self.assertRaisesRegex(
                RestoreBindingUnavailable, "^restore_binding_unavailable$"
            ):
                codec.bind(**(TARGET | {key: value}))
        keys = {"v1": b"f" * 32}
        copied = self.codec(keys=keys)
        keys.clear()
        self.assertEqual(copied.bind(**TARGET), codec.bind(**TARGET))


if __name__ == "__main__":
    unittest.main()
