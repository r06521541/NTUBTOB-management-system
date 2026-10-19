"""Candidate metadata must not silently broaden historical ORM queries."""

import unittest

from shared_module.portal_data import erasure_models, erasure_recovery_models
from shared_module.portal_data.models import PortalAuthorityStateRecord, PortalDataBase
from sqlalchemy import inspect, select


class RecoveryMetadataTests(unittest.TestCase):
    def test_private_operation_is_core_only_and_has_no_person_binding(self):
        table = erasure_recovery_models.account_erasure_admin_recovery_operations
        self.assertEqual(len(table.c), 8)
        self.assertFalse(any(column.nullable for column in table.c))
        self.assertEqual(
            {fk.target_fullname for fk in table.foreign_keys},
            {"ntubtob.account_erasure_jobs.id"},
        )
        self.assertFalse(
            any(m.local_table is table for m in PortalDataBase.registry.mappers)
        )
        self.assertEqual(next(iter(table.foreign_keys)).ondelete, "RESTRICT")

    def test_pointer_is_nullable_core_only_not_added_to_orm_select(self):
        name = "management_suspension_operation_id"
        column = PortalAuthorityStateRecord.__table__.c[name]
        self.assertTrue(column.nullable)
        self.assertNotIn(name, inspect(PortalAuthorityStateRecord).column_attrs)
        self.assertNotIn(name, str(select(PortalAuthorityStateRecord)))
        self.assertEqual(next(iter(column.foreign_keys)).ondelete, "RESTRICT")

    def test_job_fk_resolves_to_registered_ledger(self):
        table = erasure_recovery_models.account_erasure_admin_recovery_operations
        self.assertIs(
            next(iter(table.foreign_keys)).column.table,
            erasure_models.AccountErasureJobRecord.__table__,
        )
