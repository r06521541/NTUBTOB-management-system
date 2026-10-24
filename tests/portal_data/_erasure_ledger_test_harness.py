"""Remove retained 0014/0015/0016 only in an exact disposable test database.

Never import this helper into application, migration or operator code. A retaining
0014 downgrade legitimately leaves its objects at revision 0013; retained 0015
may accompany markers 0013/0014. Validate both inventories before any mutation.
Retained 0016 requires both nullable timestamp columns and the 0015 inventory.
Partial inventory, older marker with retained objects, or unknown revision fails
closed. This destructive fixture rewind is never a production downgrade.
Exact 0019/0020 first use their native empty-only downgrade, in this same
transaction. Retained intake, attempt or suspension evidence must prevent cleanup.
"""

import importlib.util
import re
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from shared_lib.shared_module.portal_data.local_database import (
    LOCAL_DATABASE_NAME,
    LOCAL_HOSTS,
)

LEDGER_REVISION = "0014_account_erasure_ledger"
GENERATION_REVISION = "0015_account_generations"
CANCELLATION_REVISION = "0016_erasure_cancellation"
ITEM_REVISION = "0017_erasure_work_items"
PRIVACY_REVISION = "0018_erasure_privacy_mutation"
NATIVE_EMPTY_ONLY_REVISIONS = frozenset(
    {"0019_erasure_admin_recovery", "0020_erasure_intake", "0021_erasure_continuity"}
)
ITEM_OBJECTS = frozenset(
    {
        ("table", "account_erasure_items", "r"),
        ("table", "account_erasure_item_events", "r"),
        ("function", "guard_erasure_item", "trigger"),
        ("function", "guard_erasure_item_event", "trigger"),
        ("trigger", "erasure_item_insert_guard", "7"),
        ("trigger", "erasure_item_immutable", "58"),
        ("trigger", "erasure_item_event_insert_guard", "7"),
        ("trigger", "erasure_item_event_append_only", "58"),
    }
)
CANCELLATION_OBJECTS = (
    ("cancelled_at", "nullable_timestamptz"),
    ("irreversible_started_at", "nullable_timestamptz"),
)
ATTEMPT_OBJECTS = frozenset(
    {
        ("table", "account_erasure_request_attempts", "r"),
        ("function", "guard_erasure_request_attempt", "trigger"),
        ("trigger", "erasure_request_attempt_binding", "7"),
        ("trigger", "erasure_request_attempt_immutable", "58"),
    }
)
GENERATION_OBJECTS = (
    ("column", "people", "uuid_not_null"),
    ("column", "auth_identities", "uuid_not_null"),
    ("function", "guard_person_account_generation", "trigger"),
    ("function", "guard_identity_account_generation", "trigger"),
    ("trigger", "people", "person_account_generation_guard"),
    ("trigger", "auth_identities", "identity_account_generation_guard"),
)
PRE_LEDGER_REVISION = "0013_account_deletion_requests"
KNOWN_PRE_LEDGER_REVISIONS = frozenset(
    {
        "0001_legacy_baseline",
        "0002_portal_data_foundation",
        "0003_legacy_bigint_activity_game",
        "0004_phase_c_identity_lifecycle",
        "0005_mobile_auth_api_foundation",
        "0006_staging_broker_operation_journal",
        "0007_mobile_notifications",
        "0008_mobile_notification_delivery",
        "0009_event_management_writes",
        "0010_apple_provider_lifecycle",
        "0011_event_notification_guest_lifecycle",
        "0012_persistent_admin_authority",
        PRE_LEDGER_REVISION,
    }
)
EXPECTED_OBJECTS = frozenset(
    {
        ("table", "account_erasure_jobs", "r"),
        ("table", "account_erasure_steps", "r"),
        ("function", "guard_erasure_job", "trigger"),
        ("function", "reject_erasure_evidence_mutation", "trigger"),
    }
)


def _privacy_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/0018_erasure_privacy_mutation.py"
    )
    spec = importlib.util.spec_from_file_location("isolated_privacy_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _constraint_shape(value):
    # Preserve parentheses, operators and casts: a weaker logical grouping must
    # never compare equal merely because all identifiers still appear.
    return re.sub(r"\s", "", value)


PLAN_OBJECTS = frozenset(
    {
        ("table", "account_erasure_sealed_plans", "r"),
        ("function", "guard_erasure_sealed_plan", "0"),
        ("function", "guard_erasure_sealed_plan_job_binding", "0"),
        ("trigger", "erasure_sealed_plan_insert_guard", "7"),
        ("trigger", "erasure_sealed_plan_immutable", "58"),
        ("trigger", "erasure_sealed_plan_job_binding", "19"),
    }
)


def _sealed_plan_inventory(connection, revision):
    rows = connection.execute(
        text(
            """
      /* sealed_plan_inventory */
      SELECT 'table',c.relname,c.relkind::text FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='ntubtob' AND c.relname='account_erasure_sealed_plans'
      UNION ALL SELECT 'function',p.proname,p.pronargs::text FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='ntubtob'
      AND p.proname IN ('guard_erasure_sealed_plan','guard_erasure_sealed_plan_job_binding')
      UNION ALL SELECT 'trigger',t.tgname,t.tgtype::text FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='ntubtob' AND t.tgname IN ('erasure_sealed_plan_insert_guard','erasure_sealed_plan_immutable','erasure_sealed_plan_job_binding')
    """
        )
    ).all()
    if not rows and revision != PRIVACY_REVISION:
        return False
    if (
        len(rows) != len(PLAN_OBJECTS)
        or set(map(tuple, rows)) != PLAN_OBJECTS
        or revision
        not in {
            PRIVACY_REVISION,
            ITEM_REVISION,
            CANCELLATION_REVISION,
            GENERATION_REVISION,
            LEDGER_REVISION,
            PRE_LEDGER_REVISION,
        }
    ):
        raise RuntimeError(
            "Sealed plan cleanup requires complete exact retained schema"
        )
    columns = connection.execute(
        text(
            """
      SELECT a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.attnotnull,a.atthasdef,a.attgenerated,a.attacl IS NULL
      FROM pg_catalog.pg_attribute a WHERE a.attrelid='ntubtob.account_erasure_sealed_plans'::regclass
      AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum
    """
        )
    ).all()
    if list(map(tuple, columns)) != [
        (n, t, True, False, "", True)
        for n, t in (
            ("job_id", "uuid"),
            ("key_id", "character varying(64)"),
            ("ciphertext", "bytea"),
        )
    ]:
        raise RuntimeError("Sealed plan cleanup column drift")
    expected_constraints = {
        "PRIMARY KEY (job_id)",
        "FOREIGN KEY (job_id) REFERENCES ntubtob.account_erasure_jobs(id) ON DELETE RESTRICT",
        "CHECK (((key_id)::text ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'::text))",
        "CHECK (((octet_length(ciphertext) >= 52) AND (octet_length(ciphertext) <= 4194355)))",
    }
    constraints = connection.execute(
        text(
            """
      SELECT pg_catalog.pg_get_constraintdef(k.oid),k.convalidated,k.condeferrable,k.condeferred
      FROM pg_catalog.pg_constraint k WHERE k.conrelid='ntubtob.account_erasure_sealed_plans'::regclass
    """
        )
    ).all()
    if (
        len(constraints) != 4
        or any(tuple(r[1:]) != (True, False, False) for r in constraints)
        or {_constraint_shape(r[0]) for r in constraints}
        != {_constraint_shape(v) for v in expected_constraints}
    ):
        raise RuntimeError("Sealed plan cleanup constraint drift")
    contract = connection.execute(
        text(
            """
      SELECT c.relrowsecurity,c.relforcerowsecurity,
        (SELECT count(*) FROM pg_catalog.pg_policy p WHERE p.polrelid=c.oid),
        (SELECT count(*) FROM pg_catalog.pg_trigger t WHERE t.tgrelid=c.oid AND NOT t.tgisinternal),
        (SELECT count(*) FROM pg_catalog.aclexplode(COALESCE(c.relacl,pg_catalog.acldefault('r',c.relowner))) a WHERE a.grantee<>c.relowner)
      FROM pg_catalog.pg_class c WHERE c.oid='ntubtob.account_erasure_sealed_plans'::regclass
    """
        )
    ).one()
    if tuple(contract) != (True, False, 0, 2, 0):
        raise RuntimeError("Sealed plan cleanup RLS or ACL drift")
    module = _privacy_migration()
    with patch.object(module.op, "execute") as execute:
        module.upgrade()
    sql = "\n".join(str(c.args[0]) for c in execute.call_args_list)
    for name in ("guard_erasure_sealed_plan", "guard_erasure_sealed_plan_job_binding"):
        body = (
            re.search(
                rf"CREATE FUNCTION ntubtob\.{name}\(.*?AS \$\$(.*?)\$\$;", sql, re.S
            )
            .group(1)
            .strip()
        )
        stored = connection.execute(
            text(
                """
          SELECT p.prosrc,p.prosecdef,p.proconfig,p.prokind,pg_catalog.oidvectortypes(p.proargtypes),
            pg_catalog.format_type(p.prorettype,NULL),
            (SELECT count(*) FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a WHERE a.grantee<>p.proowner)
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
          WHERE n.nspname='ntubtob' AND p.proname=:name
        """
            ),
            {"name": name},
        ).one()
        if stored[0].strip() != body or tuple(stored[1:]) != (
            False,
            ["search_path=pg_catalog"],
            "f",
            "",
            "trigger",
            0,
        ):
            raise RuntimeError("Sealed plan cleanup function drift")
    for name, table, function in (
        (
            "erasure_sealed_plan_insert_guard",
            "account_erasure_sealed_plans",
            "guard_erasure_sealed_plan",
        ),
        (
            "erasure_sealed_plan_immutable",
            "account_erasure_sealed_plans",
            "reject_erasure_evidence_mutation",
        ),
        (
            "erasure_sealed_plan_job_binding",
            "account_erasure_jobs",
            "guard_erasure_sealed_plan_job_binding",
        ),
    ):
        trigger = connection.execute(
            text(
                """
          SELECT c.relname,t.tgenabled,t.tgisinternal,t.tgnargs,t.tgqual IS NULL,pn.nspname,p.proname,t.tgargs
          FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
          JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace WHERE n.nspname='ntubtob' AND t.tgname=:name
        """
            ),
            {"name": name},
        ).one()
        if (
            tuple(trigger[:7]) != (table, "O", False, 0, True, "ntubtob", function)
            or bytes(trigger[7]) != b""
        ):
            raise RuntimeError("Sealed plan cleanup trigger drift")
    return True


def _privacy_inventory(connection, revision):
    """Read all candidate objects before any fixture DDL; no generic cleanup."""
    rows = connection.execute(
        text(
            """
      /* privacy_inventory */
      SELECT 'table',c.relname,c.relkind::text FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='ntubtob' AND c.relname='erasure_privacy_permits'
      UNION ALL
      SELECT 'function',p.proname,p.pronargs::text FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname='ntubtob' AND p.proname IN
        ('guard_erasure_privacy_mutation','apply_erasure_privacy_mutation')
      UNION ALL
      SELECT 'trigger',c.relname,t.tgtype::text FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
      JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='ntubtob' AND t.tgname='erasure_privacy_guard'
    """
        )
    ).all()
    if not rows and revision != PRIVACY_REVISION:
        return False
    module = _privacy_migration()
    expected = {
        ("table", "erasure_privacy_permits", "r"),
        ("function", "guard_erasure_privacy_mutation", "0"),
        ("function", "apply_erasure_privacy_mutation", "7"),
    }
    # Include every candidate guard, including review threads and activities;
    # retained old/partial inventories must never be treated as a complete head.
    expected.update(("trigger", table, "31") for table in module.FIELDS)
    if (
        len(rows) != len(expected)
        or set(map(tuple, rows)) != expected
        or revision
        not in {
            PRIVACY_REVISION,
            ITEM_REVISION,
            CANCELLATION_REVISION,
            GENERATION_REVISION,
            LEDGER_REVISION,
            PRE_LEDGER_REVISION,
        }
    ):
        raise RuntimeError("Privacy cleanup requires complete exact retained schema")
    # Function body and signature must match the local candidate, not just names.
    with patch.object(module.op, "execute") as execute:
        module.upgrade()
    sql = "\n".join(str(call.args[0]) for call in execute.call_args_list)
    for name, arguments, result in (
        ("guard_erasure_privacy_mutation", "", "trigger"),
        (
            "apply_erasure_privacy_mutation",
            "uuid, uuid, text, bigint, text, jsonb, text",
            "void",
        ),
    ):
        expected_body = (
            re.search(
                rf"CREATE FUNCTION ntubtob\.{name}\(.*?AS \$\$(.*?)\$\$;", sql, re.S
            )
            .group(1)
            .strip()
        )
        stored = connection.execute(
            text(
                """
          SELECT p.prosrc,p.prosecdef,p.proconfig,p.prokind,
            pg_catalog.oidvectortypes(p.proargtypes),pg_catalog.format_type(p.prorettype,NULL)
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
          WHERE n.nspname='ntubtob' AND p.proname=:name
        """
            ),
            {"name": name},
        ).one()
        if (
            tuple(stored[1:])
            != (True, ["search_path=pg_catalog"], "f", arguments, result)
            or stored[0].strip() != expected_body
        ):
            raise RuntimeError("Privacy cleanup function drift")
    for table in module.FIELDS:
        trigger = connection.execute(
            text(
                """
          SELECT t.tgenabled,t.tgisinternal,t.tgnargs,t.tgqual IS NULL,
            pn.nspname,p.proname,t.tgargs
          FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
          JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
          WHERE n.nspname='ntubtob' AND c.relname=:table AND t.tgname='erasure_privacy_guard'
        """
            ),
            {"table": table},
        ).one()
        mode = "immutable" if table in module.IMMUTABLE else "attribution"
        expected_args = (mode + "\0" + module.NULLABLE.get(table, "") + "\0").encode()
        if (
            tuple(trigger[:6])
            != ("O", False, 2, True, "ntubtob", "guard_erasure_privacy_mutation")
            or bytes(trigger[6]) != expected_args
        ):
            raise RuntimeError("Privacy cleanup trigger drift")
    columns = connection.execute(
        text(
            """
      SELECT a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.attnotnull,
        a.atthasdef,a.attgenerated
      FROM pg_catalog.pg_attribute a WHERE a.attrelid='ntubtob.erasure_privacy_permits'::regclass
        AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum
    """
        )
    ).all()
    expected_columns = [
        (name, kind, name != "new_hash", False, "")
        for name, kind in (
            ("backend", "integer"),
            ("transaction_id", "bigint"),
            ("table_name", "text"),
            ("row_id", "bigint"),
            ("operation", "text"),
            ("old_hash", "text"),
            ("new_hash", "text"),
        )
    ]
    if list(map(tuple, columns)) != expected_columns:
        raise RuntimeError("Privacy cleanup permit schema drift")
    permit_contract = connection.execute(
        text(
            """
      SELECT c.relrowsecurity, c.relforcerowsecurity,
        (SELECT count(*) FROM pg_catalog.pg_policy p WHERE p.polrelid=c.oid),
        (SELECT count(*) FROM pg_catalog.pg_trigger t WHERE t.tgrelid=c.oid AND NOT t.tgisinternal),
        (SELECT array_agg(pg_catalog.pg_get_constraintdef(k.oid) ORDER BY k.oid)
         FROM pg_catalog.pg_constraint k WHERE k.conrelid=c.oid)
      FROM pg_catalog.pg_class c WHERE c.oid='ntubtob.erasure_privacy_permits'::regclass
    """
        )
    ).one()
    if tuple(permit_contract) != (
        True,
        False,
        0,
        0,
        ["PRIMARY KEY (backend, transaction_id, table_name, row_id)"],
    ):
        raise RuntimeError("Privacy cleanup permit policy drift")
    if (
        connection.scalar(text("SELECT count(*) FROM ntubtob.erasure_privacy_permits"))
        != 0
    ):
        raise RuntimeError("Privacy cleanup requires no active permits")
    # A detached historical thread is evidence just like a redacted actor. Do
    # not restore NOT NULL (or remove guards) while any such row remains.
    for table, column in module.NULLABLE.items():
        nullable = connection.scalar(
            text(
                """
          SELECT NOT a.attnotnull FROM pg_catalog.pg_attribute a
          JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='ntubtob' AND c.relname=:table AND a.attname=:column AND NOT a.attisdropped
        """
            ),
            {"table": table, "column": column},
        )
        if nullable is not True or connection.scalar(
            text(
                f"SELECT EXISTS (SELECT 1 FROM ntubtob.{table} WHERE {column} IS NULL)"
            )
        ):
            raise RuntimeError("Privacy cleanup cannot restore attribution")
    for table, name, shape in (
        (
            "event_invitees",
            "ck_event_invitee_source_fields",
            "CHECK (((((source)::text = 'qualification'::text) AND (source_qualification IS NOT NULL) AND (actor_person_id IS NULL)) OR (((source)::text = ANY ((ARRAY['manual_include'::character varying, 'manual_exclude'::character varying])::text[])) AND ((length((reason)::text) >= 3) AND (length((reason)::text) <= 300)))))",
        ),
        (
            "identity_review_messages",
            "ck_identity_review_sender",
            "CHECK (((((sender_role)::text = 'applicant'::text) AND (sender_person_id IS NULL)) OR ((sender_role)::text = 'admin'::text)))",
        ),
    ):
        constraint = connection.execute(
            text(
                """
          SELECT pg_catalog.pg_get_constraintdef(k.oid),k.convalidated FROM pg_catalog.pg_constraint k
          JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='ntubtob' AND c.relname=:table AND k.conname=:name AND k.contype='c'
        """
            ),
            {"table": table, "name": name},
        ).one()
        if constraint[1] is not True or _constraint_shape(
            constraint[0]
        ) != _constraint_shape(shape):
            raise RuntimeError("Privacy cleanup check constraint drift")
    if connection.scalar(
        text(
            """
      SELECT EXISTS (SELECT 1 FROM ntubtob.event_invitees
        WHERE source IN ('manual_include','manual_exclude') AND actor_person_id IS NULL)
      OR EXISTS (SELECT 1 FROM ntubtob.identity_review_messages WHERE sender_role='admin' AND sender_person_id IS NULL)
    """
        )
    ):
        raise RuntimeError("Privacy cleanup cannot restore attribution")
    return True


def _remove_privacy_schema(connection):
    module = _privacy_migration()
    # All preflight checks above succeeded. Any unexpected dependency/constraint
    # failure aborts the enclosing transaction, including every preceding DDL.
    for table in module.FIELDS:
        connection.execute(
            text(f"DROP TRIGGER erasure_privacy_guard ON ntubtob.{table}")
        )
    for table, column in module.NULLABLE.items():
        connection.execute(
            text(f"ALTER TABLE ntubtob.{table} ALTER COLUMN {column} SET NOT NULL")
        )
    connection.execute(
        text(
            """
      ALTER TABLE ntubtob.event_invitees DROP CONSTRAINT ck_event_invitee_source_fields;
      ALTER TABLE ntubtob.event_invitees ADD CONSTRAINT ck_event_invitee_source_fields CHECK (
        (source='qualification' AND source_qualification IS NOT NULL AND actor_person_id IS NULL) OR
        (source IN ('manual_include','manual_exclude') AND actor_person_id IS NOT NULL AND length(reason) BETWEEN 3 AND 300));
      ALTER TABLE ntubtob.identity_review_messages DROP CONSTRAINT ck_identity_review_sender;
      ALTER TABLE ntubtob.identity_review_messages ADD CONSTRAINT ck_identity_review_sender CHECK (
        (sender_role='applicant' AND sender_person_id IS NULL) OR (sender_role='admin' AND sender_person_id IS NOT NULL));
    """
        )
    )
    for table, trigger in module.OLD_TRIGGERS.items():
        function = {
            "mobile_notifications": "reject_mobile_notification_mutation",
            "mobile_notification_publish_audits": "reject_mobile_notification_audit_mutation",
        }.get(table, "reject_audit_mutation")
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON ntubtob.{table} FOR EACH ROW EXECUTE FUNCTION ntubtob.{function}()"
            )
        )
    for statement in (
        "DROP FUNCTION ntubtob.apply_erasure_privacy_mutation(uuid,uuid,text,bigint,text,jsonb,text)",
        "DROP FUNCTION ntubtob.guard_erasure_privacy_mutation()",
        "DROP TABLE ntubtob.erasure_privacy_permits",
    ):
        connection.execute(text(statement))


def remove_retained_erasure_ledger_from_isolated_test_database(engine) -> None:
    if (
        engine.url.drivername not in {"postgresql", "postgresql+psycopg2"}
        or (engine.url.host or "").lower() not in LOCAL_HOSTS
        or engine.url.database != LOCAL_DATABASE_NAME
        or getattr(engine.url, "query", None)
    ):
        raise RuntimeError("Erasure ledger cleanup requires the isolated test database")

    with engine.connect() as connection, connection.begin():
        driver = connection.connection.dbapi_connection
        if getattr(driver, "autocommit", None) is not False:
            raise RuntimeError(
                "Erasure ledger cleanup requires a transactional connection"
            )
        has_marker = connection.scalar(
            text("SELECT pg_catalog.to_regclass('ntubtob.alembic_version') IS NOT NULL")
        )
        revision = None
        if has_marker:
            revisions = tuple(
                connection.scalars(
                    text("SELECT version_num FROM ntubtob.alembic_version FOR UPDATE")
                ).all()
            )
            if len(revisions) != 1 or revisions[0] not in (
                KNOWN_PRE_LEDGER_REVISIONS
                | NATIVE_EMPTY_ONLY_REVISIONS
                | {
                    LEDGER_REVISION,
                    GENERATION_REVISION,
                    CANCELLATION_REVISION,
                    ITEM_REVISION,
                    PRIVACY_REVISION,
                }
            ):
                raise RuntimeError(
                    "Erasure ledger cleanup requires one exact known revision"
                )
            revision = revisions[0]
            if revision in NATIVE_EMPTY_ONLY_REVISIONS:
                config = Config(
                    str(Path(__file__).resolve().parents[2] / "alembic.ini")
                )
                config.attributes["connection"] = connection
                # Native0021/0020/0019 own empty/history/RLS checks. Do not replace
                # them with fixture DROP statements or manually rewrite markers.
                command.downgrade(config, PRIVACY_REVISION)
                revisions = tuple(
                    connection.scalars(
                        text(
                            "SELECT version_num FROM ntubtob.alembic_version FOR UPDATE"
                        )
                    ).all()
                )
                if revisions != (PRIVACY_REVISION,):
                    raise RuntimeError(
                        "Erasure cleanup native downgrade revision mismatch"
                    )
                revision = PRIVACY_REVISION

        objects = tuple(
            tuple(row)
            for row in connection.execute(
                text(
                    """
                    SELECT 'table', c.relname, c.relkind::text
                      FROM pg_catalog.pg_class c
                      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'ntubtob'
                       AND c.relname IN ('account_erasure_jobs', 'account_erasure_steps')
                    UNION ALL
                    SELECT 'function', p.proname,
                           CASE WHEN p.pronargs = 0 AND p.prokind = 'f'
                             AND p.prorettype = 'pg_catalog.trigger'::pg_catalog.regtype
                           THEN 'trigger' ELSE 'unexpected' END
                      FROM pg_catalog.pg_proc p
                      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname = 'ntubtob'
                       AND p.proname IN ('guard_erasure_job', 'reject_erasure_evidence_mutation')
                    """
                )
            ).all()
        )
        generations = tuple(
            tuple(row)
            for row in connection.execute(
                text(
                    """
            /* generation_inventory */
            SELECT 'column', c.relname,
                   CASE WHEN a.atttypid = 'pg_catalog.uuid'::pg_catalog.regtype
                     AND a.attnotnull AND c.relkind = 'r' AND a.attgenerated = ''
                     AND pg_catalog.pg_get_expr(d.adbin,d.adrelid) IN
                       ('gen_random_uuid()', 'pg_catalog.gen_random_uuid()')
                     THEN 'uuid_not_null' ELSE 'unexpected' END
              FROM pg_catalog.pg_attribute a
              JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
             WHERE n.nspname = 'ntubtob' AND c.relname IN ('people','auth_identities')
               AND a.attname = 'account_generation' AND NOT a.attisdropped
            UNION ALL
            SELECT 'function', p.proname,
                   CASE WHEN p.pronargs = 0 AND p.prokind = 'f'
                     AND p.prorettype = 'pg_catalog.trigger'::pg_catalog.regtype
                     THEN 'trigger' ELSE 'unexpected' END
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'ntubtob' AND p.proname IN
               ('guard_person_account_generation','guard_identity_account_generation')
            UNION ALL
            SELECT 'trigger', c.relname,
                   CASE WHEN t.tgtype = 23 AND t.tgenabled = 'O' AND NOT t.tgisinternal
                     AND t.tgnargs = 0 AND t.tgqual IS NULL
                     AND pn.nspname = 'ntubtob' AND
                     ((c.relname = 'people' AND p.proname = 'guard_person_account_generation') OR
                      (c.relname = 'auth_identities' AND p.proname = 'guard_identity_account_generation'))
                     THEN t.tgname ELSE 'unexpected' END
              FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
              JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
              JOIN pg_catalog.pg_namespace pn ON pn.oid = p.pronamespace
             WHERE n.nspname = 'ntubtob' AND t.tgname IN
               ('person_account_generation_guard','identity_account_generation_guard')
        """
                )
            ).all()
        )
        cancellations = tuple(
            tuple(row)
            for row in connection.execute(
                text(
                    """
            /* cancellation_inventory */
            SELECT a.attname, CASE WHEN c.relkind = 'r'
              AND a.atttypid = 'pg_catalog.timestamptz'::pg_catalog.regtype
              AND NOT a.attnotnull AND a.attgenerated = '' AND NOT a.atthasdef
              THEN 'nullable_timestamptz' ELSE 'unexpected' END
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'ntubtob' AND c.relname = 'account_erasure_jobs'
              AND a.attname IN ('cancelled_at','irreversible_started_at')
              AND NOT a.attisdropped
        """
                )
            ).all()
        )
        attempts = tuple(
            tuple(row)
            for row in connection.execute(
                text(
                    """
            /* attempt_inventory */
            SELECT 'table', c.relname, c.relkind::text
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='ntubtob' AND c.relname='account_erasure_request_attempts'
            UNION ALL
            SELECT 'function', p.proname,
              CASE WHEN p.pronargs=0 AND p.prokind='f'
                AND p.prorettype='pg_catalog.trigger'::pg_catalog.regtype
                THEN 'trigger' ELSE 'unexpected' END
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
             WHERE n.nspname='ntubtob' AND p.proname='guard_erasure_request_attempt'
            UNION ALL
            SELECT 'trigger', t.tgname,
              CASE WHEN c.relname='account_erasure_request_attempts'
                AND t.tgenabled='O' AND NOT t.tgisinternal AND t.tgnargs=0 AND t.tgqual IS NULL
                AND pn.nspname='ntubtob' AND
                ((t.tgname='erasure_request_attempt_binding' AND p.proname='guard_erasure_request_attempt') OR
                 (t.tgname='erasure_request_attempt_immutable' AND p.proname='reject_erasure_evidence_mutation'))
                THEN t.tgtype::text ELSE 'unexpected' END
              FROM pg_catalog.pg_trigger t
              JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
              JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
             WHERE n.nspname='ntubtob' AND t.tgname IN
               ('erasure_request_attempt_binding','erasure_request_attempt_immutable')
        """
                )
            ).all()
        )
        items = tuple(
            tuple(row)
            for row in connection.execute(
                text(
                    """
            /* item_inventory */
            SELECT 'table',c.relname,c.relkind::text
              FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='ntubtob' AND c.relname IN ('account_erasure_items','account_erasure_item_events')
            UNION ALL
            SELECT 'function',p.proname,
              CASE WHEN p.pronargs=0 AND p.prokind='f' AND p.prorettype='pg_catalog.trigger'::regtype
                THEN 'trigger' ELSE 'unexpected' END
              FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
             WHERE n.nspname='ntubtob' AND p.proname IN ('guard_erasure_item','guard_erasure_item_event')
            UNION ALL
            SELECT 'trigger',t.tgname,
              CASE WHEN t.tgenabled='O' AND NOT t.tgisinternal AND t.tgnargs=0 AND t.tgqual IS NULL
                AND pn.nspname='ntubtob' AND
                ((t.tgname='erasure_item_insert_guard' AND c.relname='account_erasure_items' AND p.proname='guard_erasure_item') OR
                 (t.tgname='erasure_item_immutable' AND c.relname='account_erasure_items' AND p.proname='reject_erasure_evidence_mutation') OR
                 (t.tgname='erasure_item_event_insert_guard' AND c.relname='account_erasure_item_events' AND p.proname='guard_erasure_item_event') OR
                 (t.tgname='erasure_item_event_append_only' AND c.relname='account_erasure_item_events' AND p.proname='reject_erasure_evidence_mutation'))
                THEN t.tgtype::text ELSE 'unexpected' END
              FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
              JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
             WHERE n.nspname='ntubtob' AND t.tgname IN ('erasure_item_insert_guard','erasure_item_immutable','erasure_item_event_insert_guard','erasure_item_event_append_only')
        """
                )
            ).all()
        )
        plans = _sealed_plan_inventory(connection, revision)
        privacy = _privacy_inventory(connection, revision)
        if bool(plans) != bool(privacy):
            raise RuntimeError("Privacy cleanup requires complete sealed plan schema")
        if privacy and not items:
            raise RuntimeError("Privacy cleanup requires retained item schema")
        if items or revision in {ITEM_REVISION, PRIVACY_REVISION}:
            if (
                len(items) != len(ITEM_OBJECTS)
                or frozenset(items) != ITEM_OBJECTS
                or not cancellations
                or not attempts
                or revision
                not in {
                    ITEM_REVISION,
                    PRIVACY_REVISION,
                    CANCELLATION_REVISION,
                    GENERATION_REVISION,
                    LEDGER_REVISION,
                    PRE_LEDGER_REVISION,
                }
            ):
                raise RuntimeError(
                    "Item cleanup requires complete exact retained schema"
                )
        if attempts and (
            not cancellations
            or len(attempts) != len(ATTEMPT_OBJECTS)
            or frozenset(attempts) != ATTEMPT_OBJECTS
        ):
            raise RuntimeError(
                "Attempt cleanup requires complete exact retained schema"
            )
        # The earlier unpublished 0016 candidate legitimately had only the two
        # cancellation columns. Absence is accepted for that isolated fixture,
        # but a partial or unexpected new inventory must never be dropped.
        if cancellations or revision in {
            CANCELLATION_REVISION,
            ITEM_REVISION,
            PRIVACY_REVISION,
        }:
            if (
                revision
                not in {
                    ITEM_REVISION,
                    PRIVACY_REVISION,
                    CANCELLATION_REVISION,
                    GENERATION_REVISION,
                    LEDGER_REVISION,
                    PRE_LEDGER_REVISION,
                }
                or len(cancellations) != len(CANCELLATION_OBJECTS)
                or frozenset(cancellations) != frozenset(CANCELLATION_OBJECTS)
                or not generations
            ):
                raise RuntimeError(
                    "Cancellation cleanup requires complete exact retained schema"
                )
        if generations or revision in {
            GENERATION_REVISION,
            CANCELLATION_REVISION,
            ITEM_REVISION,
            PRIVACY_REVISION,
        }:
            if (
                revision
                not in {
                    ITEM_REVISION,
                    PRIVACY_REVISION,
                    CANCELLATION_REVISION,
                    GENERATION_REVISION,
                    LEDGER_REVISION,
                    PRE_LEDGER_REVISION,
                }
                or len(generations) != len(GENERATION_OBJECTS)
                or frozenset(generations) != frozenset(GENERATION_OBJECTS)
            ):
                raise RuntimeError(
                    "Generation cleanup requires complete exact retained schema"
                )
        if (
            not objects
            and revision
            not in {
                LEDGER_REVISION,
                GENERATION_REVISION,
                CANCELLATION_REVISION,
                ITEM_REVISION,
                PRIVACY_REVISION,
            }
            and not generations
        ):
            return
        if (
            revision
            not in {
                ITEM_REVISION,
                PRIVACY_REVISION,
                CANCELLATION_REVISION,
                GENERATION_REVISION,
                LEDGER_REVISION,
                PRE_LEDGER_REVISION,
            }
            or len(objects) != len(EXPECTED_OBJECTS)
            or frozenset(objects) != EXPECTED_OBJECTS
        ):
            raise RuntimeError(
                "Erasure ledger cleanup requires the complete exact retained schema"
            )

        if plans:
            for statement in (
                "DROP TRIGGER erasure_sealed_plan_job_binding ON ntubtob.account_erasure_jobs",
                "DROP TABLE ntubtob.account_erasure_sealed_plans",
                "DROP FUNCTION ntubtob.guard_erasure_sealed_plan()",
                "DROP FUNCTION ntubtob.guard_erasure_sealed_plan_job_binding()",
            ):
                connection.execute(text(statement))
        if privacy:
            _remove_privacy_schema(connection)
        if items:
            for statement in (
                "DROP TABLE ntubtob.account_erasure_item_events",
                "DROP TABLE ntubtob.account_erasure_items",
                "DROP FUNCTION ntubtob.guard_erasure_item_event()",
                "DROP FUNCTION ntubtob.guard_erasure_item()",
            ):
                connection.execute(text(statement))
        if attempts:
            connection.execute(
                text("DROP TABLE ntubtob.account_erasure_request_attempts")
            )
            connection.execute(
                text("DROP FUNCTION ntubtob.guard_erasure_request_attempt()")
            )
        if generations:
            for statement in (
                "DROP TRIGGER person_account_generation_guard ON ntubtob.people",
                "DROP TRIGGER identity_account_generation_guard ON ntubtob.auth_identities",
                "DROP FUNCTION ntubtob.guard_person_account_generation()",
                "DROP FUNCTION ntubtob.guard_identity_account_generation()",
                "ALTER TABLE ntubtob.people DROP COLUMN account_generation",
                "ALTER TABLE ntubtob.auth_identities DROP COLUMN account_generation",
            ):
                connection.execute(text(statement))

        # Table-owned triggers/identity sequence disappear with their table. Keep
        # restrictive dependency checks: unexpected dependents abort the transaction.
        for statement in (
            "DROP TABLE ntubtob.account_erasure_steps",
            "DROP TABLE ntubtob.account_erasure_jobs",
            "DROP FUNCTION ntubtob.guard_erasure_job()",
            "DROP FUNCTION ntubtob.reject_erasure_evidence_mutation()",
        ):
            connection.execute(text(statement))
        if revision in {
            LEDGER_REVISION,
            GENERATION_REVISION,
            CANCELLATION_REVISION,
            ITEM_REVISION,
            PRIVACY_REVISION,
        }:
            result = connection.execute(
                text(
                    "UPDATE ntubtob.alembic_version "
                    "SET version_num = '0013_account_deletion_requests' "
                    f"WHERE version_num = '{revision}'"
                )
            )
            if result.rowcount != 1:
                raise RuntimeError("Erasure ledger cleanup revision marker changed")
