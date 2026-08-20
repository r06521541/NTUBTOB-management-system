from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools import mobile_staging_data
from tools.tests.test_mobile_staging_operator import database_approval

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL")
SUBJECT = "fake-private-tester-subject"


class MobileStagingBrokerSeamTest(unittest.TestCase):
    def test_broker_wrapper_enables_0006_mode_only_for_bounded_call(self):
        observed = []

        def inventory(*_args):
            observed.append(mobile_staging_data._BROKER_SCHEMA_MODE.get())
            return {"state": "ready_basic"}

        arguments = ({"owner_approved": True}, "fake-dsn", "fake-subject")
        with patch.object(
            mobile_staging_data, "fixture_lifecycle_inventory", inventory
        ):
            result = mobile_staging_data.broker_fixture_lifecycle_inventory(*arguments)
        self.assertEqual(result, {"state": "ready_basic"})
        self.assertEqual(observed, [True])
        self.assertFalse(mobile_staging_data._BROKER_SCHEMA_MODE.get())

    def test_broker_mode_is_reset_after_operator_failure(self):
        def fail(*_args):
            self.assertTrue(mobile_staging_data._BROKER_SCHEMA_MODE.get())
            raise RuntimeError("bounded fake failure")

        with patch.object(mobile_staging_data, "grant_officer", fail):
            with self.assertRaisesRegex(RuntimeError, "bounded fake failure"):
                mobile_staging_data.broker_grant_officer({}, "fake-dsn", "subject")
        self.assertFalse(mobile_staging_data._BROKER_SCHEMA_MODE.get())


@unittest.skipUnless(DATABASE_URL, "isolated PostgreSQL URL is required")
class MobileStagingBrokerSeamIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_local_database_url(DATABASE_URL)
        cls.engine = create_engine(cls.database_url)
        cls.approval = database_approval(cls.database_url)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))
        mobile_staging_data.execute(
            self.approval, self.database_url, SUBJECT, Path.cwd()
        )
        with self.engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def tearDown(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ntubtob CASCADE"))

    def test_0006_wrappers_preserve_inspect_grant_restore_and_reset(self):
        self.assertEqual(
            mobile_staging_data.broker_fixture_lifecycle_inventory(
                self.approval, self.database_url, SUBJECT
            )["state"],
            "ready_basic",
        )
        self.assertTrue(
            mobile_staging_data.broker_grant_officer(
                self.approval, self.database_url, SUBJECT
            )["changed"]
        )
        self.assertTrue(
            mobile_staging_data.broker_restore_basic(
                self.approval, self.database_url, SUBJECT
            )["changed"]
        )
        mobile_staging_data.broker_grant_officer(
            self.approval, self.database_url, SUBJECT
        )
        reset = mobile_staging_data.broker_reset_fixture_lifecycle(
            self.approval, self.database_url, SUBJECT
        )
        self.assertEqual((reset["state"], reset["changed"]), ("ready_basic", True))


if __name__ == "__main__":
    unittest.main()
