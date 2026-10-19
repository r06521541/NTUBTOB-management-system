"""Durable source-row generations; no proof, erasure gate or permissions change.

Existing rows receive one random UUID during the transactional column addition.
Old ORM mappings intentionally exclude these columns. INSERT always generates a
fresh value, even if the caller supplies one; UPDATE cannot rewrite generations.
Downgrade retains columns and guards. Re-upgrade after downgrade requires explicit
reconciliation, not a destructive reset or a silent IF NOT EXISTS shortcut.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0015_account_generations"
down_revision: Union[str, None] = "0014_account_erasure_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ntubtob.people ADD COLUMN account_generation uuid
          NOT NULL DEFAULT pg_catalog.gen_random_uuid();
        ALTER TABLE ntubtob.auth_identities ADD COLUMN account_generation uuid
          NOT NULL DEFAULT pg_catalog.gen_random_uuid();

        CREATE FUNCTION ntubtob.guard_person_account_generation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            NEW.account_generation := pg_catalog.gen_random_uuid();
          ELSIF NEW.account_generation IS DISTINCT FROM OLD.account_generation THEN
            RAISE EXCEPTION 'person generation rewrite rejected' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER person_account_generation_guard
          BEFORE INSERT OR UPDATE ON ntubtob.people
          FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_person_account_generation();

        CREATE FUNCTION ntubtob.guard_identity_account_generation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            NEW.account_generation := pg_catalog.gen_random_uuid();
          ELSE
            IF NEW.account_generation IS DISTINCT FROM OLD.account_generation THEN
              RAISE EXCEPTION 'identity generation rewrite rejected' USING ERRCODE = '23514';
            END IF;
            IF NEW.provider IS DISTINCT FROM OLD.provider OR
               NEW.provider_subject IS DISTINCT FROM OLD.provider_subject OR
               NEW.person_id IS DISTINCT FROM OLD.person_id THEN
              NEW.account_generation := pg_catalog.gen_random_uuid();
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER identity_account_generation_guard
          BEFORE INSERT OR UPDATE ON ntubtob.auth_identities
          FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_identity_account_generation();
        """
    )


def downgrade() -> None:
    # Application rollback must not erase generations or weaken their guards.
    pass
