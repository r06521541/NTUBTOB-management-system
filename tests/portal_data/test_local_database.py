import unittest

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)


class LocalDatabaseSafetyTests(unittest.TestCase):
    def test_accepts_only_named_local_database(self):
        value = "postgresql+psycopg2://portal_local:fake@127.0.0.1:55432/ntubtob_portal_local"
        self.assertEqual(require_local_database_url(value), value)

    def test_rejects_missing_remote_and_supabase_urls(self):
        rejected = (
            None,
            "postgresql://fake:fake@example.com/ntubtob_portal_local",
            "postgresql://fake:fake@localhost/production",
            "postgresql://fake:fake@db.fake.supabase.co/ntubtob_portal_local",
            "sqlite:///ntubtob_portal_local",
        )
        for value in rejected:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                require_local_database_url(value)


if __name__ == "__main__":
    unittest.main()
