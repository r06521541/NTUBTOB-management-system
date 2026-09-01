from __future__ import annotations

import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tools.persistent_admin_inventory import (
    EXPECTED_REVISION,
    InventoryError,
    collect_inventory,
    main,
    parse_private_allowlist,
    render_snapshot,
)


class PersistentAdminInventoryTests(unittest.TestCase):
    def test_default_is_offline_preflight(self):
        output = io.StringIO()
        with (
            patch("sys.stdout", output),
            patch("tools.persistent_admin_inventory.create_engine") as create_engine,
        ):
            self.assertEqual(main([]), 0)
        create_engine.assert_not_called()
        self.assertEqual(
            output.getvalue(),
            "persistent_admin_inventory=v1\nstatus=preflight_only\n",
        )

    def test_private_allowlist_is_strict_and_never_rendered(self):
        self.assertEqual(parse_private_allowlist("7, 12"), (7, 12))
        for value in ("0", "7,7", "7,", "member", "７"):
            with self.subTest(value=value), self.assertRaises(InventoryError):
                parse_private_allowlist(value)

    def test_collect_is_read_only_and_output_is_deidentified(self):
        session = MagicMock()
        session.scalars.return_value = [EXPECTED_REVISION]
        state_result = MagicMock()
        state_result.one_or_none.return_value = SimpleNamespace(
            mode="legacy_allowlist", epoch=1
        )
        count_result = MagicMock()
        count_result.one.return_value = (2, 3, 1, 1, 2)
        session.execute.side_effect = [
            MagicMock(),
            MagicMock(),
            MagicMock(),
            state_result,
            count_result,
        ]
        snapshot = collect_inventory(session, (7, 12))
        output = render_snapshot(snapshot)
        statements = "\n".join(
            str(call.args[0]) for call in session.execute.call_args_list
        )
        self.assertIn("SET TRANSACTION READ ONLY", statements)
        self.assertNotRegex(
            statements.upper(), r"\b(INSERT|UPDATE|DELETE|DROP|ALTER)\b"
        )
        self.assertTrue(output.isascii())
        for forbidden in (
            "person_id",
            "member_id",
            "provider_subject",
            "display_name",
            "digest",
        ):
            self.assertNotIn(forbidden, output)
        self.assertIn("mapping_both=1", output)
        self.assertIn("allowlist_parse=valid", output)
        self.assertIn("COALESCE", statements)

    def test_revision_and_state_drift_fail_closed(self):
        session = MagicMock()
        session.scalars.return_value = ["future"]
        with self.assertRaisesRegex(InventoryError, "revision_mismatch"):
            collect_inventory(session, ())

        session.scalars.return_value = [EXPECTED_REVISION, "future"]
        with self.assertRaisesRegex(InventoryError, "revision_mismatch"):
            collect_inventory(session, ())

    def test_execute_failure_discloses_no_private_input(self):
        output = io.StringIO()
        with (
            patch.dict(
                "os.environ",
                {
                    "PRIVATE_DATABASE_URL": "postgresql://user:secret@example.invalid/private",
                    "PRIVATE_ALLOWLIST": "99",
                    "PERSISTENT_ADMIN_EXPECTED_HOST": "wrong.invalid",
                    "PERSISTENT_ADMIN_EXPECTED_PORT": "5432",
                    "PERSISTENT_ADMIN_EXPECTED_DATABASE": "private",
                },
            ),
            patch("sys.stdout", output),
        ):
            result = main(
                [
                    "--execute",
                    "--database-url-env",
                    "PRIVATE_DATABASE_URL",
                    "--allowlist-env",
                    "PRIVATE_ALLOWLIST",
                ]
            )
        self.assertEqual(result, 2)
        self.assertEqual(
            output.getvalue(),
            "persistent_admin_inventory=v1\nstatus=inventory_unavailable\n",
        )
        self.assertNotIn("secret", output.getvalue())
        self.assertNotIn("99", output.getvalue())


if __name__ == "__main__":
    unittest.main()
