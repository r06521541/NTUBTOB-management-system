"""Transaction-entry erasure fences; entirely fictional, no DB or provider."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared_module.mobile_api import AccountUnavailable
from shared_module.portal_data.mobile_repository import MobileRepository
from shared_module.portal_data.models import MobileNotificationRecord
from sqlalchemy.orm import Session, make_transient_to_detached


class NotificationErasureGateTests(unittest.TestCase):
    def test_nonempty_projection_survives_real_session_expiration_without_database(
        self,
    ):
        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        for enabled in (False, True):
            for name, args in (
                ("notification_page", (7, now, None, 10, False)),
                ("notification_detail", (7, 3, now)),
            ):
                with self.subTest(entry=name, enabled=enabled):
                    row = MobileNotificationRecord(
                        id=3,
                        notification_type="officer_personal",
                        title="Fictional title",
                        body="Fictional body",
                        destination_type="notification",
                        destination_game_id=None,
                        destination_event_id=None,
                        created_at=now,
                        visible_until=now + timedelta(days=90),
                    )
                    make_transient_to_detached(row)
                    session = Session()
                    repository = MobileRepository(None, erasure_checks_enabled=enabled)

                    def execute(*args, **kwargs):
                        self.assertTrue(session.in_transaction())
                        session.add(row)
                        item = (row, None, now, None, None)
                        return SimpleNamespace(
                            all=lambda: [item], one_or_none=lambda: item
                        )

                    def guard(actual, **values):
                        self.assertIs(actual, session)
                        self.assertTrue(session.in_transaction())
                        self.assertFalse(
                            session.new or session.dirty or session.deleted
                        )

                    with (
                        patch(
                            "shared_module.portal_data.mobile_repository.Session",
                            return_value=session,
                        ),
                        patch.object(
                            repository,
                            "_event_notification_columns_ready",
                            return_value=True,
                        ),
                        patch(
                            "shared_module.portal_data.mobile_repository.require_account_not_erasing",
                            side_effect=guard,
                        ) as gate,
                        patch.object(session, "execute", side_effect=execute),
                        patch.object(
                            session,
                            "connection",
                            side_effect=AssertionError("NO DATABASE"),
                        ),
                    ):
                        result = getattr(repository, name)(*args)
                    item = result[0] if name == "notification_page" else result
                    self.assertEqual(item["title"], "Fictional title")
                    self.assertEqual(gate.call_count, int(enabled))

    def test_notification_projection_runs_before_transaction_closes(self):
        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        for name, args in (
            ("notification_page", (7, now, None, 10, False)),
            ("notification_detail", (7, 3, now)),
        ):
            with self.subTest(entry=name):
                repository = MobileRepository(MagicMock())
                session = MagicMock()
                session.__enter__.return_value = session
                transaction = session.begin.return_value
                active = []
                transaction.__enter__.side_effect = lambda: active.append(True)
                transaction.__exit__.side_effect = lambda *args: active.clear()
                session.execute.return_value.all.return_value = [(object(), None, now)]
                session.execute.return_value.one_or_none.return_value = (
                    object(),
                    None,
                    now,
                )

                def project(*values):
                    self.assertEqual(active, [True])
                    return {"id": 3}

                with (
                    patch(
                        "shared_module.portal_data.mobile_repository.Session",
                        return_value=session,
                    ),
                    patch.object(
                        repository,
                        "_event_notification_columns_ready",
                        return_value=False,
                    ),
                    patch.object(repository, "_notification_row", side_effect=project),
                ):
                    result = getattr(repository, name)(*args)
                self.assertEqual(
                    result, [{"id": 3}] if name.endswith("page") else {"id": 3}
                )
                self.assertEqual(active, [])

    def test_pending_apple_completion_checks_identity_before_consumed_code_rows(self):
        repository = MobileRepository(MagicMock(), erasure_checks_enabled=True)
        session = MagicMock()
        session.__enter__.return_value = session
        with (
            patch(
                "shared_module.portal_data.mobile_repository.Session",
                return_value=session,
            ),
            patch.object(
                repository,
                "_require_account_available",
                side_effect=AccountUnavailable("account access unavailable"),
            ) as guard,
        ):
            with self.assertRaises(AccountUnavailable):
                repository.complete_apple_code_for_pending(identity_id=9)
        guard.assert_called_once_with(session, identity_id=9)
        session.scalar.assert_not_called()
        session.add.assert_not_called()

    def test_blocked_account_cannot_read_write_or_register_before_guard(self):
        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        calls = (
            ("notification_page", (7, now, None, 10, False), {}),
            ("notification_detail", (7, 3, now), {}),
            ("notification_unread_count", (7, now), {}),
            ("mark_notification_read", (7, 3, now), {}),
            ("mark_all_notifications_read", (7, now), {}),
            ("register_fake_device", (), {"person_id": 7}),
        )
        for name, args, kwargs in calls:
            with self.subTest(entry=name):
                repository = MobileRepository(MagicMock(), erasure_checks_enabled=True)
                session = MagicMock()
                session.__enter__.return_value = session
                with (
                    patch(
                        "shared_module.portal_data.mobile_repository.Session",
                        return_value=session,
                    ),
                    patch.object(
                        repository,
                        "_require_account_available",
                        side_effect=AccountUnavailable("account access unavailable"),
                    ) as guard,
                ):
                    with self.assertRaises(AccountUnavailable):
                        getattr(repository, name)(*args, **kwargs)
                guard.assert_called_once_with(session, person_id=7)
                session.begin.assert_called_once_with()
                for operation in ("scalar", "scalars", "execute", "add", "flush"):
                    getattr(session, operation).assert_not_called()


if __name__ == "__main__":
    unittest.main()
