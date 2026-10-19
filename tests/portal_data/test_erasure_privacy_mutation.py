"""Exact privacy capability tests; opt-in fictional PostgreSQL only."""

import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.portal_data import test_erasure_item_schema as items

ROOT = Path(__file__).resolve().parents[2]


def migration():
    spec = importlib.util.spec_from_file_location(
        "privacy_mutation",
        ROOT / "migrations/versions/0018_erasure_privacy_mutation.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ErasurePrivacyMigrationTests(unittest.TestCase):
    def test_private_fixed_capability_and_no_runtime_grants(self):
        module = migration()
        with patch.object(module.op, "execute") as execute:
            module.upgrade()
        sql = "\n".join(str(call.args[0]) for call in execute.call_args_list)
        self.assertEqual(module.down_revision, "0017_erasure_work_items")
        self.assertIn("REVOKE ALL ON ntubtob.erasure_privacy_permits FROM PUBLIC", sql)
        self.assertIn("SECURITY DEFINER SET search_path=pg_catalog", sql)
        self.assertNotIn("GRANT ", sql)
        self.assertNotIn("DISABLE TRIGGER", sql)
        self.assertNotIn("set_config", sql)
        self.assertIn("pg_advisory_xact_lock(1315198274)", sql)
        self.assertEqual(len(module.IMMUTABLE), 6)
        with patch.object(module.op, "execute") as execute:
            module.downgrade()
        execute.assert_not_called()


@unittest.skipUnless(items.fixture.DATABASE_URL, "isolated erasure URL not configured")
class ErasurePrivacyPostgresTests(unittest.TestCase):
    setUpClass = classmethod(items.ErasureItemPostgresTests.setUpClass.__func__)
    tearDownClass = classmethod(items.ErasureItemPostgresTests.tearDownClass.__func__)
    job = items.ErasureItemPostgresTests.job
    update = items.ErasureItemPostgresTests.update
    rejected = items.ErasureItemPostgresTests.rejected
    item = items.ErasureItemPostgresTests.item
    event = items.ErasureItemPostgresTests.event
    start = items.ErasureItemPostgresTests.start

    def setUp(self):
        items.ErasureItemPostgresTests.setUp(self)
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.upgrade(config, "0018_erasure_privacy_mutation")
        self.generation = str(
            self.connection.scalar(
                text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
                {"id": self.person},
            )
        )
        self.job_id = self.job(expected_generation=self.generation)
        self.update(
            self.job_id,
            status="verified",
            verified_at=items.CREATED,
            updated_at=items.CREATED,
        )
        self.row_id = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.access_audit (action,actor_person_id,target_person_id,reason,request_id,created_at) "
                "VALUES ('person_profile_updated',:person,:person,'Fictional private reason',:request,:now) RETURNING id"
            ),
            {"person": self.person, "request": str(uuid4()), "now": items.CREATED},
        )

    def prepare(
        self,
        changes,
        *,
        stage="manual_redaction",
        action="update",
        digest=None,
        table="access_audit",
        row_id=None,
    ):
        row_id = self.row_id if row_id is None else row_id
        assert table in {
            "access_audit",
            "identity_review_threads",
            "identity_review_messages",
            "activities",
            "games",
        }
        digest = digest or self.connection.scalar(
            text(
                "SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') "
                f"FROM ntubtob.{table} t WHERE id=:id"
            ),
            {"id": row_id},
        )
        args = dict(
            job=self.job_id,
            table=table,
            row=row_id,
            old=digest,
            patch=json.dumps(changes),
            action=action,
        )
        binding = self.connection.scalar(
            text(
                "SELECT encode(sha256(convert_to(jsonb_build_array('privacy_mutation_v1',CAST(:job AS uuid),"
                "CAST(:generation AS uuid),CAST(:table AS text),CAST(:row AS bigint),CAST(:old AS text),"
                "CAST(:patch AS jsonb),CAST(:action AS text))::text,'UTF8')),'hex')"
            ),
            dict(args, generation=self.generation),
        )
        args["item"] = self.item(self.job_id, stage=stage, binding_hash=binding)
        self.start(self.job_id)
        self.event(args["item"])
        return args

    def apply(self, args):
        self.connection.execute(
            text(
                "SELECT ntubtob.apply_erasure_privacy_mutation(CAST(:job AS uuid),CAST(:item AS uuid),"
                ":table,:row,:old,CAST(:patch AS jsonb),:action)"
            ),
            args,
        )

    def other_person(self):
        return self.connection.scalar(
            text(
                "INSERT INTO ntubtob.people (display_name,portal_access_level,portal_status,version,created_at,updated_at) "
                "VALUES ('Fictional other person','basic','active',1,:now,:now) RETURNING id"
            ),
            {"now": items.CREATED},
        )

    def review_thread(self, person):
        identity = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.auth_identities (provider,provider_subject,person_id,status,created_at,updated_at) "
                "VALUES ('apple',:subject,:person,'linked',:now,:now) RETURNING id"
            ),
            {
                "subject": "fictional-privacy-" + uuid4().hex,
                "person": person,
                "now": items.CREATED,
            },
        )
        thread = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.identity_review_threads (auth_identity_id,status,last_activity_at,created_at,updated_at) "
                "VALUES (:identity,'open',:now,:now,:now) RETURNING id"
            ),
            {"identity": identity, "now": items.CREATED},
        )
        return identity, thread

    def review_message(self, thread, sender=None):
        return self.connection.scalar(
            text(
                "INSERT INTO ntubtob.identity_review_messages (thread_id,sender_role,sender_person_id,body,body_redacted,created_at) "
                "VALUES (:thread,:role,:sender,'Fictional private text',false,:now) RETURNING id"
            ),
            {
                "thread": thread,
                "role": "applicant" if sender is None else "admin",
                "sender": sender,
                "now": items.CREATED,
            },
        )

    def test_reviewed_owned_thread_detach_preserves_shared_messages_and_normal_edits(
        self,
    ):
        identity, thread = self.review_thread(self.person)
        message = self.review_message(thread, self.other_person())
        args = self.prepare(
            {"auth_identity_id": None}, table="identity_review_threads", row_id=thread
        )
        self.apply(args)
        self.assertIsNone(
            self.connection.scalar(
                text(
                    "SELECT auth_identity_id FROM ntubtob.identity_review_threads WHERE id=:id"
                ),
                {"id": thread},
            )
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT body FROM ntubtob.identity_review_messages WHERE id=:id"),
                {"id": message},
            ),
            "Fictional private text",
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT person_id FROM ntubtob.auth_identities WHERE id=:id"),
                {"id": identity},
            ),
            self.person,
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.identity_review_threads SET last_activity_at=:now WHERE id=:id"
            ),
            {"now": items.FINISHED, "id": thread},
        )
        self.rejected(lambda: self.apply(args))

    def test_thread_detach_requires_review_current_ownership_and_no_normal_null(self):
        identity, thread = self.review_thread(self.person)
        self.rejected(
            lambda: self.connection.execute(
                text(
                    "INSERT INTO ntubtob.identity_review_threads (auth_identity_id,status,last_activity_at,created_at,updated_at) "
                    "VALUES (NULL,'open',:now,:now,:now)"
                ),
                {"now": items.CREATED},
            )
        )
        self.rejected(
            lambda: self.connection.execute(
                text(
                    "UPDATE ntubtob.identity_review_threads SET auth_identity_id=NULL WHERE id=:id"
                ),
                {"id": thread},
            )
        )
        for stage, remap in (("online_erasure", False), ("manual_redaction", True)):
            with self.subTest(stage=stage, remap=remap):
                savepoint = self.connection.begin_nested()
                try:
                    args = self.prepare(
                        {"auth_identity_id": None},
                        table="identity_review_threads",
                        row_id=thread,
                        stage=stage,
                    )
                    if remap:
                        self.connection.execute(
                            text(
                                "UPDATE ntubtob.auth_identities SET person_id=:person WHERE id=:id"
                            ),
                            {"id": identity, "person": self.other_person()},
                        )
                    self.rejected(lambda: self.apply(args))
                finally:
                    savepoint.rollback()

    def test_exact_own_review_message_delete_never_deletes_other_admin_or_thread(self):
        other = self.other_person()
        for owner, sender, stage, accepted in (
            (self.person, None, "manual_redaction", True),
            (other, self.person, "manual_redaction", True),
            (self.person, other, "manual_redaction", False),
            (other, None, "manual_redaction", False),
            (self.person, None, "online_erasure", False),
        ):
            with self.subTest(owner=owner, sender=sender, stage=stage):
                savepoint = self.connection.begin_nested()
                try:
                    _, thread = self.review_thread(owner)
                    message = self.review_message(thread, sender)
                    preserved = self.review_message(thread, other)
                    args = self.prepare(
                        {},
                        table="identity_review_messages",
                        row_id=message,
                        action="delete",
                        stage=stage,
                    )
                    if accepted:
                        self.apply(args)
                    else:
                        self.rejected(lambda: self.apply(args))
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id"
                            ),
                            {"id": message},
                        ),
                        0 if accepted else 1,
                    )
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT count(*) FROM ntubtob.identity_review_messages WHERE id=:id"
                            ),
                            {"id": preserved},
                        ),
                        1,
                    )
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT count(*) FROM ntubtob.identity_review_threads WHERE id=:id"
                            ),
                            {"id": thread},
                        ),
                        1,
                    )
                finally:
                    savepoint.rollback()

    def test_identity_only_audit_delete_requires_current_ownership_and_null_person_target(
        self,
    ):
        other = self.other_person()
        for owner, target, stage, accepted in (
            (self.person, None, "manual_redaction", True),
            (other, None, "manual_redaction", False),
            (self.person, other, "manual_redaction", False),
            (self.person, None, "online_erasure", False),
        ):
            with self.subTest(owner=owner, target=target, stage=stage):
                savepoint = self.connection.begin_nested()
                try:
                    identity, _ = self.review_thread(owner)
                    row = self.connection.scalar(
                        text(
                            "INSERT INTO ntubtob.access_audit (action,actor_person_id,target_person_id,auth_identity_id,reason,request_id,created_at) "
                            "VALUES ('identity_pending',:actor,:target,:identity,'Fictional reviewed history',:request,:now) RETURNING id"
                        ),
                        {
                            "actor": other,
                            "target": target,
                            "identity": identity,
                            "request": str(uuid4()),
                            "now": items.CREATED,
                        },
                    )
                    args = self.prepare({}, row_id=row, action="delete", stage=stage)
                    if accepted:
                        self.apply(args)
                    else:
                        self.rejected(lambda: self.apply(args))
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT count(*) FROM ntubtob.access_audit WHERE id=:id"
                            ),
                            {"id": row},
                        ),
                        0 if accepted else 1,
                    )
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT count(*) FROM ntubtob.access_audit WHERE id=:id"
                            ),
                            {"id": self.row_id},
                        ),
                        1,
                    )
                finally:
                    savepoint.rollback()

    def test_activity_title_exact_reviewed_patch_preserves_activity_and_event(self):
        event = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.events (title,event_type,status,start_at,created_by_person_id,version,created_at,updated_at) "
                "VALUES ('Fictional shared event','practice','draft',:now,:actor,1,:now,:now) RETURNING id"
            ),
            {"now": items.CREATED, "actor": self.other_person()},
        )
        activity = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.activities (event_id,title,activity_type,position,start_at) "
                "VALUES (:event,'Fictional private activity title','meal',1,:now) RETURNING id"
            ),
            {"event": event, "now": items.CREATED},
        )
        for stage, action, accepted in (
            ("online_erasure", "update", False),
            ("manual_redaction", "delete", False),
            ("manual_redaction", "update", True),
        ):
            with self.subTest(stage=stage, action=action):
                savepoint = self.connection.begin_nested()
                try:
                    args = self.prepare(
                        (
                            {"title": "Reviewed shared activity"}
                            if action == "update"
                            else {}
                        ),
                        table="activities",
                        row_id=activity,
                        stage=stage,
                        action=action,
                    )
                    if accepted:
                        self.apply(args)
                    else:
                        self.rejected(lambda: self.apply(args))
                    result = self.connection.execute(
                        text(
                            "SELECT title,event_id FROM ntubtob.activities WHERE id=:id"
                        ),
                        {"id": activity},
                    ).one()
                    self.assertEqual(
                        tuple(result),
                        (
                            (
                                "Reviewed shared activity"
                                if accepted
                                else "Fictional private activity title"
                            ),
                            event,
                        ),
                    )
                finally:
                    savepoint.rollback()

    def test_game_reviewed_patch_preserves_schedule_and_other_shared_fields(self):
        game = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.games (year,season,start_datetime,duration,location,home_team,away_team) "
                "VALUES (2026,1,:now,120,'Fictional private location','Shared home','Shared away') RETURNING id"
            ),
            {"now": items.CREATED},
        )
        for stage, action, patch_value, accepted in (
            ("online_erasure", "update", {"location": "Reviewed location"}, False),
            ("manual_redaction", "delete", {}, False),
            ("manual_redaction", "update", {"duration": 90}, False),
            ("manual_redaction", "update", {"location": "Reviewed location"}, True),
            (
                "manual_redaction",
                "update",
                {"home_team": "Reviewed home", "away_team": "Reviewed away"},
                True,
            ),
        ):
            with self.subTest(stage=stage, action=action, fields=tuple(patch_value)):
                savepoint = self.connection.begin_nested()
                try:
                    args = self.prepare(
                        patch_value,
                        table="games",
                        row_id=game,
                        stage=stage,
                        action=action,
                    )
                    if accepted:
                        self.apply(args)
                    else:
                        self.rejected(lambda: self.apply(args))
                    result = self.connection.execute(
                        text(
                            "SELECT year,season,start_datetime,duration,location,home_team,away_team FROM ntubtob.games WHERE id=:id"
                        ),
                        {"id": game},
                    ).one()
                    self.assertEqual(tuple(result[:4]), (2026, 1, items.CREATED, 120))
                    self.assertEqual(
                        tuple(result[4:]),
                        tuple(
                            patch_value.get(field, original) if accepted else original
                            for field, original in (
                                ("location", "Fictional private location"),
                                ("home_team", "Shared home"),
                                ("away_team", "Shared away"),
                            )
                        ),
                    )
                finally:
                    savepoint.rollback()

    def test_update_changes_stored_text_and_removes_only_own_actor(self):
        args = self.prepare(
            {"reason": "Redacted shared reason", "actor_person_id": None}
        )
        self.apply(args)
        result = self.connection.execute(
            text(
                "SELECT reason,actor_person_id,target_person_id FROM ntubtob.access_audit WHERE id=:id"
            ),
            {"id": self.row_id},
        ).one()
        self.assertEqual(tuple(result), ("Redacted shared reason", None, self.person))
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.erasure_privacy_permits")
            ),
            0,
        )
        # Caller owns completion evidence; capability must not report full erasure.
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT max(event_sequence) FROM ntubtob.account_erasure_item_events"
                )
            ),
            1,
        )
        self.rejected(lambda: self.apply(args))

    def test_changed_old_digest_rejects_before_mutation(self):
        args = self.prepare({"reason": "Redacted"}, digest="0" * 64)
        self.rejected(lambda: self.apply(args))

    def test_unknown_column_rejected_even_with_matching_binding(self):
        args = self.prepare({"request_id": "rewritten"})
        self.rejected(lambda: self.apply(args))

    def test_text_requires_manual_review_stage(self):
        args = self.prepare({"reason": "Redacted"}, stage="online_erasure")
        self.rejected(lambda: self.apply(args))

    def test_actor_may_only_be_removed_not_reassigned(self):
        args = self.prepare({"actor_person_id": self.person})
        self.rejected(lambda: self.apply(args))

    def test_target_generation_mismatch_rejected(self):
        self.connection.execute(
            text(
                "UPDATE ntubtob.account_erasure_jobs SET expected_generation=expected_generation WHERE id=:id"
            ),
            {"id": self.job_id},
        )
        # Bind a new job to a wrong generation; lifecycle prevents rewriting the Person.
        other = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.people (display_name,portal_access_level,portal_status,version,created_at,updated_at) "
                "VALUES ('Fictional other','basic','active',1,:now,:now) RETURNING id"
            ),
            {"now": items.fixture.NOW},
        )
        self.job_id = self.job(person_id=other, expected_generation=self.generation)
        self.update(
            self.job_id,
            status="verified",
            verified_at=items.CREATED,
            updated_at=items.CREATED,
        )
        args = self.prepare({"actor_person_id": None})
        self.rejected(lambda: self.apply(args))

    def test_own_target_delete_and_rollback(self):
        args = self.prepare({}, action="delete")
        savepoint = self.connection.begin_nested()
        self.apply(args)
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.access_audit WHERE id=:id"),
                {"id": self.row_id},
            ),
            0,
        )
        savepoint.rollback()
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.access_audit WHERE id=:id"),
                {"id": self.row_id},
            ),
            1,
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT count(*) FROM ntubtob.erasure_privacy_permits")
            ),
            0,
        )

    def test_direct_update_and_forged_guc_cannot_bypass(self):
        self.connection.execute(
            text("SELECT set_config('ntubtob.erasure_job',:job,true)"),
            {"job": self.job_id},
        )
        self.rejected(
            lambda: self.connection.execute(
                text("UPDATE ntubtob.access_audit SET reason='forged' WHERE id=:id"),
                {"id": self.row_id},
            )
        )

    def test_normal_event_insert_still_requires_creator_and_edit_still_works(self):
        sql = text(
            "INSERT INTO ntubtob.events (title,event_type,status,start_at,created_by_person_id,version,created_at,updated_at) "
            "VALUES ('Fictional team event','practice','draft',:now,:actor,1,:now,:now) RETURNING id"
        )
        self.rejected(
            lambda: self.connection.execute(sql, {"now": items.CREATED, "actor": None})
        )
        event_id = self.connection.scalar(
            sql, {"now": items.CREATED, "actor": self.person}
        )
        self.connection.execute(
            text("UPDATE ntubtob.events SET title='Edited team event' WHERE id=:id"),
            {"id": event_id},
        )
        self.rejected(
            lambda: self.connection.execute(
                text(
                    "UPDATE ntubtob.events SET created_by_person_id=NULL WHERE id=:id"
                ),
                {"id": event_id},
            )
        )

    def test_noop_patch_cannot_be_reused_as_success(self):
        args = self.prepare({"reason": "Fictional private reason"})
        self.rejected(lambda: self.apply(args))

    def test_changed_source_cannot_create_manual_invitee_without_actor(self):
        event = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.events (title,event_type,status,start_at,created_by_person_id,version,created_at,updated_at) "
                "VALUES ('Fictional event','practice','draft',:now,:person,1,:now,:now) RETURNING id"
            ),
            {"now": items.CREATED, "person": self.person},
        )
        invitee = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.event_invitees (event_id,person_id,included,source,source_qualification,participation_category,snapshotted_at) "
                "VALUES (:event,:person,true,'qualification','team_player','team_player',:now) RETURNING id"
            ),
            {"event": event, "person": self.person, "now": items.CREATED},
        )
        self.rejected(
            lambda: self.connection.execute(
                text(
                    "UPDATE ntubtob.event_invitees SET source='manual_include',reason='Fictional reason' WHERE id=:id"
                ),
                {"id": invitee},
            )
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.event_invitees SET source='manual_include',reason='Fictional reason',actor_person_id=:person WHERE id=:id"
            ),
            {"id": invitee, "person": self.person},
        )
        self.clear_actor_fixture("event_invitees", invitee, "actor_person_id")
        self.connection.execute(
            text(
                "UPDATE ntubtob.event_invitees SET reason='Edited shared reason' WHERE id=:id"
            ),
            {"id": invitee},
        )

    def test_changed_sender_role_cannot_create_admin_message_without_actor(self):
        identity = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.auth_identities (provider,provider_subject,status,created_at,updated_at) "
                "VALUES ('apple',:subject,'pending',:now,:now) RETURNING id"
            ),
            {"subject": "fictional-privacy-" + uuid4().hex, "now": items.CREATED},
        )
        thread = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.identity_review_threads (auth_identity_id,status,last_activity_at,created_at,updated_at) "
                "VALUES (:identity,'open',:now,:now,:now) RETURNING id"
            ),
            {"identity": identity, "now": items.CREATED},
        )
        message = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.identity_review_messages (thread_id,sender_role,body,body_redacted,created_at) "
                "VALUES (:thread,'applicant','Fictional applicant text',false,:now) RETURNING id"
            ),
            {"thread": thread, "now": items.CREATED},
        )
        self.rejected(
            lambda: self.connection.execute(
                text(
                    "UPDATE ntubtob.identity_review_messages SET sender_role='admin' WHERE id=:id"
                ),
                {"id": message},
            )
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.identity_review_messages SET sender_role='admin',sender_person_id=:person WHERE id=:id"
            ),
            {"id": message, "person": self.person},
        )
        self.clear_actor_fixture(
            "identity_review_messages", message, "sender_person_id"
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.identity_review_messages SET body='Edited shared text' WHERE id=:id"
            ),
            {"id": message},
        )

    def clear_actor_fixture(self, table, row_id, field):
        # Owner-only fixture seeding of the historical redacted state. The
        # unprivileged permit/entrypoint boundaries are separate negative tests.
        self.connection.execute(
            text(
                f"INSERT INTO ntubtob.erasure_privacy_permits SELECT pg_backend_pid(),txid_current(),:table,id,'UPDATE',"
                "encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),"
                "encode(sha256(convert_to((to_jsonb(t)||CAST(:patch AS jsonb))::text,'UTF8')),'hex') "
                f"FROM ntubtob.{table} t WHERE id=:id"
            ),
            {"table": table, "patch": json.dumps({field: None}), "id": row_id},
        )
        self.connection.execute(
            text(f"UPDATE ntubtob.{table} SET {field}=NULL WHERE id=:id"),
            {"id": row_id},
        )

    def test_later_trigger_skip_or_rewrite_rolls_back_mutation(self):
        for action, trigger_body in (
            ("update", "RETURN NULL;"),
            ("update", "NEW.reason := 'Fictional unwanted rewrite'; RETURN NEW;"),
            ("delete", "RETURN NULL;"),
        ):
            with self.subTest(action=action, behavior=trigger_body):
                savepoint = self.connection.begin_nested()
                try:
                    args = self.prepare(
                        {"reason": "Reviewed reason"} if action == "update" else {},
                        action=action,
                    )
                    self.connection.execute(
                        text(
                            "CREATE FUNCTION ntubtob.fictional_later_privacy_trigger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                            + trigger_body
                            + " END; $$"
                        )
                    )
                    self.connection.execute(
                        text(
                            "CREATE TRIGGER zz_fictional_later_privacy BEFORE UPDATE OR DELETE ON ntubtob.access_audit "
                            "FOR EACH ROW EXECUTE FUNCTION ntubtob.fictional_later_privacy_trigger()"
                        )
                    )
                    self.rejected(lambda: self.apply(args))
                    self.assertEqual(
                        self.connection.scalar(
                            text(
                                "SELECT reason FROM ntubtob.access_audit WHERE id=:id"
                            ),
                            {"id": self.row_id},
                        ),
                        "Fictional private reason",
                    )
                finally:
                    savepoint.rollback()

    def test_unprivileged_role_cannot_invoke_or_forge_permit(self):
        role = "fictional_privacy_" + uuid4().hex
        self.connection.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        self.connection.execute(text(f"GRANT USAGE ON SCHEMA ntubtob TO {role}"))
        self.connection.execute(text(f"SET LOCAL ROLE {role}"))
        self.rejected(
            lambda: self.connection.execute(
                text(
                    "INSERT INTO ntubtob.erasure_privacy_permits VALUES (1,1,'access_audit',1,'DELETE','fake',NULL)"
                )
            )
        )
        self.rejected(
            lambda: self.connection.execute(
                text(
                    "SELECT ntubtob.apply_erasure_privacy_mutation(NULL,NULL,'access_audit',1,repeat('a',64),'{}')"
                )
            )
        )
        self.connection.execute(text("RESET ROLE"))
        self.connection.execute(text(f"REVOKE USAGE ON SCHEMA ntubtob FROM {role}"))
        self.connection.execute(text(f"DROP ROLE {role}"))


@unittest.skipUnless(items.fixture.DATABASE_URL, "isolated erasure URL not configured")
class ErasurePrivacyDefaultAclPostgresTests(unittest.TestCase):
    setUpClass = classmethod(items.ErasureItemPostgresTests.setUpClass.__func__)
    tearDownClass = classmethod(items.ErasureItemPostgresTests.tearDownClass.__func__)

    def setUp(self):
        items.ErasureItemPostgresTests.setUp(self)

    def test_named_default_grants_do_not_leak_new_capability(self):
        role = "fictional_default_" + uuid4().hex
        self.connection.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        self.connection.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA ntubtob GRANT ALL ON TABLES TO {role}"
            )
        )
        self.connection.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA ntubtob GRANT ALL ON FUNCTIONS TO {role}"
            )
        )
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.upgrade(config, "0018_erasure_privacy_mutation")
        self.assertFalse(
            self.connection.scalar(
                text(
                    "SELECT has_table_privilege(:role,'ntubtob.erasure_privacy_permits','INSERT')"
                ),
                {"role": role},
            )
        )
        for signature in (
            "ntubtob.guard_erasure_privacy_mutation()",
            "ntubtob.apply_erasure_privacy_mutation(uuid,uuid,text,bigint,text,jsonb,text)",
        ):
            self.assertFalse(
                self.connection.scalar(
                    text("SELECT has_function_privilege(:role,:signature,'EXECUTE')"),
                    {"role": role, "signature": signature},
                )
            )
        self.connection.execute(
            text("CREATE TABLE ntubtob.fictional_default_control (id integer)")
        )
        self.assertTrue(
            self.connection.scalar(
                text(
                    "SELECT has_table_privilege(:role,'ntubtob.fictional_default_control','INSERT')"
                ),
                {"role": role},
            )
        )
