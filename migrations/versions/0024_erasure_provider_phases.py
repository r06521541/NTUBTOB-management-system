"""Separate local completion from proven provider and backup completion.

No new target tombstone, credential custody, dispatch, grants or success backfill.
Function replacement preserves existing owner/ACL/security attributes. Native
downgrade refuses used phase histories rather than hiding retained evidence.
"""

from alembic import op

revision = "0024_erasure_provider_phases"
down_revision = "0023_erasure_minimal_retention"
branch_labels = None
depends_on = None

EVENT = "ntubtob.guard_erasure_item_event()"
PLAN = "ntubtob.purge_erasure_sealed_plan(uuid,uuid,text,uuid)"
CONTEXT = "ntubtob.require_erasure_retention_context(uuid,uuid,uuid,boolean)"
MARKERS = (
    "ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid)",
    "ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz)",
    "ntubtob.record_erasure_backup_check(uuid,uuid,uuid,text,boolean,timestamptz,timestamptz,boolean,boolean)",
    "ntubtob.guard_erasure_retention_start()",
    PLAN,
    CONTEXT,
)

# Exact single-occurrence edits: schema drift fails, never best-effort rewriting.
EDITS = (
    (
        EVENT,
        "          item_created timestamptz;",
        "          item_created timestamptz;\n          item_stage text;\n          previous_result text;",
    ),
    (
        EVENT,
        "target_status NOT IN ('processing', 'needs_attention')",
        "target_status NOT IN ('processing', 'needs_attention', 'online_completed')",
    ),
    (
        EVENT,
        "SELECT job_id,expected_generation,created_at\n            INTO item_job,item_generation,item_created",
        "SELECT job_id,expected_generation,created_at,stage\n            INTO item_job,item_generation,item_created,item_stage",
    ),
    (
        EVENT,
        "          SELECT event_sequence,event_kind,occurred_at\n            INTO previous_sequence,previous_kind,previous_time",
        "          IF target_status='online_completed' AND (item_stage<>'provider_revocation' OR NEW.event_kind='started') THEN\n            RAISE EXCEPTION 'erasure online outcome rejected' USING ERRCODE='23514';\n          END IF;\n          SELECT event_sequence,event_kind,occurred_at,result_code\n            INTO previous_sequence,previous_kind,previous_time,previous_result",
    ),
    (
        EVENT,
        "               NEW.event_sequence = 3 AND NEW.event_kind IN ('confirmed', 'failed'))",
        "               NEW.event_sequence = 3 AND NEW.event_kind IN ('confirmed', 'failed')) OR\n              (item_stage='provider_revocation' AND previous_sequence=2 AND previous_kind='confirmed'\n               AND previous_result IN ('credential_missing','manual_action_needed','not_applicable')\n               AND NEW.event_sequence=3 AND NEW.event_kind='confirmed' AND NEW.result_code='succeeded')",
    ),
    (
        PLAN,
        "WHERE i.job_id=p_job AND (e.event_kind IS DISTINCT FROM 'confirmed'\n              OR e.result_code NOT IN ('succeeded','credential_missing','not_applicable'))",
        "WHERE i.job_id=p_job AND i.stage<>'provider_revocation' AND (e.event_kind IS DISTINCT FROM 'confirmed'\n              OR e.result_code IS DISTINCT FROM 'succeeded')",
    ),
    (
        PLAN,
        "'account_erasure_sealed_plans','account_erasure_backup_checks','account_erasure_plan_purges','erasure_plan_delete_permits']",
        "'account_erasure_sealed_plans','account_erasure_backup_checks','account_erasure_plan_purges','erasure_plan_delete_permits','account_erasure_steps']",
    ),
    (
        PLAN,
        "          SELECT * INTO plan FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_job FOR UPDATE;",
        "          IF EXISTS(SELECT 1 FROM (SELECT DISTINCT ON(stage,attempt) event_kind,result_code\n"
        "            FROM ntubtob.account_erasure_steps WHERE job_id=p_job AND stage<>'provider_revocation'\n"
        "            ORDER BY stage,attempt,event_sequence DESC) s\n"
        "            WHERE s.event_kind IS DISTINCT FROM 'confirmed' OR s.result_code IS DISTINCT FROM 'succeeded') THEN\n"
        "            RAISE EXCEPTION 'plan_purge_work_unfinished' USING ERRCODE='23514';\n"
        "          END IF;\n"
        "          SELECT * INTO plan FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_job FOR UPDATE;",
    ),
    (
        CONTEXT,
        "WHERE i.job_id=p_request AND (e.event_kind IS DISTINCT FROM 'confirmed' OR e.result_code NOT IN ('succeeded','credential_missing','not_applicable'))",
        "WHERE i.job_id=p_request AND (e.event_kind IS DISTINCT FROM 'confirmed' OR\n            (i.stage='provider_revocation' AND e.result_code IS DISTINCT FROM 'succeeded') OR\n            (i.stage<>'provider_revocation' AND e.result_code NOT IN ('succeeded','credential_missing','not_applicable')))",
    ),
    (
        CONTEXT,
        "SELECT DISTINCT ON(stage,attempt) event_kind,result_code",
        "SELECT DISTINCT ON(stage,attempt) stage,event_kind,result_code",
    ),
    (
        CONTEXT,
        "WHERE s.event_kind<>'confirmed' OR s.result_code NOT IN ('succeeded','credential_missing','not_applicable')) THEN",
        "WHERE s.event_kind<>'confirmed' OR s.result_code NOT IN ('succeeded','credential_missing','not_applicable')\n              OR (s.stage='provider_revocation' AND s.result_code IS DISTINCT FROM 'succeeded'))\n          OR (root.status<>'cancelled' AND NOT EXISTS(SELECT 1 FROM ntubtob.account_erasure_items WHERE job_id=p_request AND stage='provider_revocation')) THEN",
    ),
)


def _replace(signature, before, after):
    absence = (
        ""
        if after in before
        else f" OR position('{after.replace(chr(39), chr(39) * 2)}' in source)>0"
    )
    signature, before, after = (
        value.replace("'", "''") for value in (signature, before, after)
    )
    op.execute(
        f"""DO $$ DECLARE source text; BEGIN
      SELECT pg_get_functiondef('{signature}'::regprocedure) INTO source;
      IF source IS NULL OR length(source)-length(replace(source,'{before}',''))<>length('{before}')
        {absence} THEN RAISE EXCEPTION 'provider_phases_definition_changed'; END IF;
      EXECUTE replace(source,'{before}','{after}'); END $$;"""
    )


def _lock():
    op.execute(
        """DO $$ DECLARE name text; BEGIN
      IF current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'provider_phases_transaction_rejected'; END IF;
      PERFORM pg_advisory_xact_lock(70070); PERFORM pg_advisory_xact_lock(1315198274);
      LOCK TABLE ntubtob.account_erasure_jobs,ntubtob.account_erasure_items,
        ntubtob.account_erasure_item_events,ntubtob.account_erasure_steps,
        ntubtob.account_erasure_plan_purges,ntubtob.erasure_retention_state IN SHARE ROW EXCLUSIVE MODE;
      FOREACH name IN ARRAY ARRAY['account_erasure_jobs','account_erasure_items',
        'account_erasure_item_events','account_erasure_steps','account_erasure_plan_purges','erasure_retention_state'] LOOP
        IF row_security_active(('ntubtob.'||name)::regclass) IS DISTINCT FROM FALSE THEN
          RAISE EXCEPTION 'provider_phases_unfiltered_state_required'; END IF;
      END LOOP;
    END $$;"""
    )


def upgrade():
    _lock()
    op.execute(
        """DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_jobs j WHERE j.status='completed' AND (
        NOT EXISTS(SELECT 1 FROM ntubtob.account_erasure_items i WHERE i.job_id=j.id AND i.stage='provider_revocation')
        OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_items i LEFT JOIN LATERAL (
          SELECT event_kind,result_code FROM ntubtob.account_erasure_item_events WHERE item_id=i.id ORDER BY event_sequence DESC LIMIT 1
        ) e ON true WHERE i.job_id=j.id AND i.stage='provider_revocation'
          AND (e.event_kind IS DISTINCT FROM 'confirmed' OR e.result_code IS DISTINCT FROM 'succeeded'))
        OR EXISTS(SELECT 1 FROM (SELECT DISTINCT ON(attempt) event_kind,result_code FROM ntubtob.account_erasure_steps
          WHERE job_id=j.id AND stage='provider_revocation' ORDER BY attempt,event_sequence DESC) s
          WHERE s.event_kind IS DISTINCT FROM 'confirmed' OR s.result_code IS DISTINCT FROM 'succeeded')
      )) THEN RAISE EXCEPTION 'provider_phases_historical_completion_unproven'; END IF;
    END $$;"""
    )
    for signature, before, after in EDITS:
        _replace(signature, before, after)
    for signature in MARKERS:
        _replace(
            signature,
            f"ARRAY['{down_revision}']::text[]",
            f"ARRAY['{revision}']::text[]",
        )


def downgrade():
    _lock()
    op.execute(
        """DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM ntubtob.erasure_retention_state WHERE cleanup_performed)
        OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_jobs j JOIN ntubtob.account_erasure_items i ON i.job_id=j.id
          LEFT JOIN LATERAL (SELECT event_kind,result_code FROM ntubtob.account_erasure_item_events
            WHERE item_id=i.id ORDER BY event_sequence DESC LIMIT 1) e ON true
          WHERE j.status IN ('online_completed','completed') AND i.stage='provider_revocation'
            AND (e.event_kind IS DISTINCT FROM 'confirmed' OR e.result_code IS DISTINCT FROM 'succeeded'))
        OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_item_events e
          JOIN ntubtob.account_erasure_items i ON i.id=e.item_id JOIN ntubtob.account_erasure_jobs j ON j.id=i.job_id
          WHERE i.stage='provider_revocation' AND j.online_completed_at IS NOT NULL AND e.occurred_at>=j.online_completed_at)
        OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_item_events e
          JOIN ntubtob.account_erasure_item_events prior ON prior.item_id=e.item_id AND prior.event_sequence=2
          WHERE e.event_sequence=3 AND prior.event_kind='confirmed')
        OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_plan_purges p JOIN ntubtob.account_erasure_items i ON i.job_id=p.job_id
          LEFT JOIN LATERAL (SELECT event_kind,result_code FROM ntubtob.account_erasure_item_events
            WHERE item_id=i.id AND occurred_at<=p.occurred_at ORDER BY event_sequence DESC LIMIT 1) e ON true
          WHERE i.stage='provider_revocation' AND (e.event_kind IS DISTINCT FROM 'confirmed'
            OR e.result_code NOT IN ('succeeded','credential_missing','not_applicable')))
      THEN RAISE EXCEPTION 'provider_phases_downgrade_requires_review'; END IF;
    END $$;"""
    )
    for signature in MARKERS:
        _replace(
            signature,
            f"ARRAY['{revision}']::text[]",
            f"ARRAY['{down_revision}']::text[]",
        )
    for signature, before, after in reversed(EDITS):
        _replace(signature, after, before)
